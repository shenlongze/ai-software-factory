"""providers/adapters/hermes.py — HermesProviderAdapter: subprocess 调 hermes CLI (智能来源)。

设计依据:
- phase8-plan.md §Q4 兼容性: Hermes 双角色 — HermesRuntimeAdapter (执行,
  runtime/adapters/hermes.py, 零改动) + 本 HermesProviderAdapter (智能,
  providers/adapters/hermes.py, 纯新增) 并存不替换。
- 调用方案 (同 ADR-0009 决策 1): `hermes -z <prompt>` one-shot prompt 模式 —
  generate 用 request.prompt (或 messages 末条正文); chat 用 system 前缀行 +
  messages 逐条拼接; prompt 全空时兜底 "execute provider request <id>"
  (prompt 永不为空, -z 必带参数)。
- 失败处理 (同 ADR-0009 决策 2, 全部转 ProviderResponse(error=...), 不抛异常):
  命令不存在 (FileNotFoundError) / 超时 (TimeoutExpired) / 其他 OS 级错误
  (OSError 基类) / exit code != 0 / stdout 为空 — 统一稳定响应。
- 配置 (同 ADR-0009 决策 3): 命令与超时可经环境变量覆盖
  (FACTORY_PROVIDER_HERMES_CMD / FACTORY_PROVIDER_HERMES_TIMEOUT); 构造函数
  参数优先于环境变量。config_schema (definitions.py) 描述 API 模式预留
  (api_key/endpoint), 本阶段只实现 cli -z。
- Adapter 不写 Event (同 ADR-0006 解耦铁律): 本模块零依赖 events 包 /
  registry / store — 仅 providers.models 契约。
- stream: CLI 子进程无真流式 — 按非空行切块 yield (每块 content 为增量片段),
  末块附 usage; 失败 yield 单块 (error 非空, 不抛异常)。
"""

from __future__ import annotations

import os
import subprocess
from typing import Iterator

from providers.provider import ProviderAdapter
from providers.models import ProviderRequest, ProviderResponse

DEFAULT_COMMAND = "hermes"          # 默认 CLI 命令名 (走 PATH 解析)
DEFAULT_TIMEOUT = 300               # 默认超时 (秒): Hermes 一次 one-shot 调用可达分钟级
ENV_COMMAND = "FACTORY_PROVIDER_HERMES_CMD"  # 环境变量: 覆盖 hermes 命令 (可给绝对路径)
ENV_TIMEOUT = "FACTORY_PROVIDER_HERMES_TIMEOUT"  # 环境变量: 覆盖超时秒数
DEFAULT_MODEL = "hermes-default"    # 默认模型名 (与 definitions.py 默认定义 models[0] 对齐)

# 失败错误消息前缀 (稳定, 供测试/审计断言)
_ERR_CMD_NOT_FOUND = "hermes command not found: {}"
_ERR_TIMEOUT = "hermes command timed out after {:g}s"
_ERR_EXIT = "hermes command exited with code {}: {}"
_ERR_NO_OUTPUT = "hermes command produced no output (stdout empty){}"
_ERR_OS = "hermes command failed: {}: {}"


class HermesProviderAdapter(ProviderAdapter):
    """Hermes Agent Provider: 经 hermes CLI one-shot 调用提供智能 (Factory 默认 Provider)。

    - PROVIDER_ID = "hermes" (与 BUILTIN_PROVIDER_ADAPTERS 键 / 默认定义 id 一致;
      runtime 的 hermes-runtime 身份属执行命名空间, 互不冲突)。
    - generate/chat: 构造 prompt → subprocess hermes -z → ProviderResponse;
      任何被列举失败均返回 error 响应而非抛异常。
    - stream: 按非空行切块 yield; 失败 yield 单 error 块。
    """

    PROVIDER_ID = "hermes"
    PROVIDER_TYPE = "agent"

    def __init__(self, command: str | None = None, timeout: float | None = None):
        """构造适配器; 参数优先于环境变量, 环境变量优先于默认值。"""
        self._command = command or os.environ.get(ENV_COMMAND) or DEFAULT_COMMAND
        raw_timeout = timeout if timeout is not None else os.environ.get(ENV_TIMEOUT)
        self._timeout = float(raw_timeout) if raw_timeout is not None else DEFAULT_TIMEOUT

    @property
    def command(self) -> str:
        """实际使用的 hermes 命令 (可被 FACTORY_PROVIDER_HERMES_CMD 覆盖)。"""
        return self._command

    @property
    def timeout(self) -> float:
        """实际使用的超时秒数 (可被 FACTORY_PROVIDER_HERMES_TIMEOUT 覆盖)。"""
        return self._timeout

    # ------------------------------------------------------------------ 契约

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        """单轮生成: prompt (或 messages 末条正文) → ProviderResponse。"""
        return self._call(self._build_prompt(request), request)

    def chat(self, request: ProviderRequest) -> ProviderResponse:
        """多轮对话: system 前缀行 + messages 逐条拼接 → ProviderResponse。"""
        return self._call(self._build_chat_prompt(request), request)

    def stream(self, request: ProviderRequest) -> Iterator[ProviderResponse]:
        """流式生成: 按非空行切块 yield (末块附 usage); 失败 yield 单 error 块。"""
        prompt = self._build_prompt(request)
        response = self._invoke(prompt, request)
        if not response.ok:
            yield response
            return
        lines = [ln for ln in response.content.splitlines() if ln.strip()]
        if not lines:
            yield ProviderResponse(
                provider_id=self.PROVIDER_ID,
                error=_ERR_NO_OUTPUT.format(""),
                model=response.model,
            )
            return
        total = len(lines)
        for i, line in enumerate(lines):
            yield ProviderResponse(
                provider_id=self.PROVIDER_ID,
                content=line + "\n",
                model=response.model,
                usage=response.usage if i == total - 1 else {},
            )

    # ------------------------------------------------------------------ 调用

    def _call(self, prompt: str, request: ProviderRequest) -> ProviderResponse:
        """同步调用 hermes -z; 失败 → error 响应 (不抛)。"""
        return self._invoke(prompt, request)

    def _invoke(self, prompt: str, request: ProviderRequest) -> ProviderResponse:
        """subprocess hermes -z prompt → ProviderResponse (失败全部映射为 error)。"""
        argv = [self._command, "-z", prompt]
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except FileNotFoundError:
            return self._failed(request, _ERR_CMD_NOT_FOUND.format(self._command))
        except subprocess.TimeoutExpired:
            return self._failed(request, _ERR_TIMEOUT.format(self._timeout))
        except OSError as exc:  # 权限等其他 OS 级错误 → error (防御兜底)
            return self._failed(request, _ERR_OS.format(type(exc).__name__, exc))

        stdout = completed.stdout or ""
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            return self._failed(
                request, _ERR_EXIT.format(completed.returncode, detail)
            )
        if not stdout.strip():
            detail = (completed.stderr or "").strip()
            suffix = f": {detail}" if detail else ""
            return self._failed(request, _ERR_NO_OUTPUT.format(suffix))

        model = request.model or DEFAULT_MODEL
        return ProviderResponse(
            provider_id=self.PROVIDER_ID,
            content=stdout,
            model=model,
            usage={
                "output_chars": len(stdout),
                "output_lines": len(stdout.splitlines()),
            },
            metadata={"command": self._command, "exit_code": completed.returncode},
        )

    def _failed(self, request: ProviderRequest, error: str) -> ProviderResponse:
        """构造 error 响应 (失败处理统一出口: 不抛异常)。"""
        return ProviderResponse(
            provider_id=self.PROVIDER_ID,
            model=request.model or DEFAULT_MODEL,
            error=error,
        )

    # ------------------------------------------------------------------ 输入解析

    @staticmethod
    def _build_prompt(request: ProviderRequest) -> str:
        """generate 输入: prompt → messages 末条正文 → system → 兜底。"""
        if request.prompt and request.prompt.strip():
            return request.prompt
        if request.messages:
            for message in reversed(request.messages):
                content = message.get("content")
                if content:
                    return str(content)
        if request.system and request.system.strip():
            return request.system
        return f"execute provider request {request.provider_id or 'unknown'}"

    @staticmethod
    def _build_chat_prompt(request: ProviderRequest) -> str:
        """chat 输入: system 前缀行 + messages 逐条 (role: content), 兜底 prompt。"""
        parts: list[str] = []
        if request.system and request.system.strip():
            parts.append(f"system: {request.system}")
        for message in request.messages or []:
            role = message.get("role", "user")
            content = message.get("content")
            if content:
                parts.append(f"{role}: {content}")
        if not parts and request.prompt:
            parts.append(request.prompt)
        if not parts:
            parts.append(f"execute provider request {request.provider_id or 'unknown'}")
        return "\n".join(parts)

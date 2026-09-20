"""runtime/adapters/hermes.py — HermesRuntimeAdapter: subprocess 调 hermes CLI (真实 Agent Runtime)。

设计依据:
- phase4c1-status.md: 首个真实 RuntimeAdapter — Hermes CLI 子进程调用 (Factory 只调用
  Hermes, 禁止 Factory 逻辑入 Hermes / LLM API 直连 / 多 Agent 编排 / 自动生成代码流程)。
- 输入输出协议 (phase4c1-status §输入输出协议): 输入 request.input dict —
  {task, step, instruction, agent_id} (均可缺省); 输出 result.output (dict)/error/status。
- 调用方案 (ADR-0009 决策 1): `hermes -z <prompt>` one-shot prompt 模式 — prompt 由
  task/step/agent_id 前缀行 + instruction 正文组合; input 全空时兜底
  "execute execution <id>" (prompt 永不为空, -z 必带参数)。
- 失败处理 (ADR-0009 决策 2, 全部转 FAILED 结果, 不抛未处理异常):
  - 命令不存在: subprocess.run 抛 FileNotFoundError → FAILED
  - 超时: subprocess.TimeoutExpired → FAILED
  - 其他 OS 级错误 (PermissionError 等, OSError 基类) → FAILED (防御兜底)
  - exit code != 0 → FAILED (error 附 stderr, 空则退 stdout)
  - stdout 为空 (exit 0 但无输出) → FAILED
- Adapter 不写 Event (由 Runner 负责, ADR-0006 解耦铁律): 本模块零依赖 events 包 /
  registry / store — 仅 runtime.models 契约 (同 echo.py)。
- 配置 (ADR-0009 决策 3): 命令与超时可经环境变量覆盖
  (FACTORY_HERMES_CMD / FACTORY_HERMES_TIMEOUT), 便于无 hermes 环境验证 FAILED
  路径与测试注入假命令; 构造函数参数优先于环境变量。
- 结果 id 从执行 id 派生 (EXR-<execution_id>, 同 echo), request_id 绑定请求
  (派发层校验依赖)。
"""

from __future__ import annotations

import json
import os
import re
import subprocess

from ai_factory_os.services.execution.runtime.adapter import RuntimeAdapter
from ai_factory_os.services.execution.runtime.types import ExecutionRequest, ExecutionResult, ExecutionStatus

DEFAULT_COMMAND = "hermes"          # 默认 CLI 命令名 (走 PATH 解析)
DEFAULT_TIMEOUT = 900               # 默认超时 (秒): 真实 agent 干完一个叶常要几分钟 —— 300s 实测不够
                                    # （真跑踩到: "hermes command timed out after 300s" ⇒ 叶被判失败重试）
ENV_COMMAND = "FACTORY_HERMES_CMD"  # 环境变量: 覆盖 hermes 命令 (可给绝对路径)
ENV_TIMEOUT = "FACTORY_HERMES_TIMEOUT"  # 环境变量: 覆盖超时秒数

#: ★ 裁定契约（第 3 项）—— 追加到 prompt 末尾, 让执行体**显式**说自己干成了什么。
#: 为什么需要: 原来只有 stdout, 调度器从外面只看到"进程退出 0" ⇒ **"停手"被当成"完成"**
#: （实测事故 EXR-005: 执行体自述"核验+停手、零改动", 叶却被记成 completed ⇒ 进度是假的）。
_VERDICT_CONTRACT = (
    "\n\n★ 结束时必须输出一行机器可读的裁定（供调度器判定, 不要改写格式）:\n"
    "EXEC-VERDICT: {\"verdict\": \"done|needs_decision|blocked\", \"reason\": \"一句话\"}\n"
    "  · done           = 本次验收已达成\n"
    "  · needs_decision = 需要人裁决（例如验收与现状冲突、口径不清）—— reason 必须写清【要裁决什么】\n"
    "  · blocked        = 被外部条件挡住（缺依赖/环境/凭据）\n"
    "  没有这行 ⇒ 调度器按【没表态】处理（保守：不当作完成）"
)

#: 裁定标记（解析用; 取最后一行, 容忍前后文）
_VERDICT_RE = re.compile(r"EXEC-VERDICT:\s*(\{.*?\})", re.S)
_VERDICTS = ("done", "needs_decision", "blocked")

# 失败错误消息前缀 (稳定, 供测试/审计断言)
_ERR_CMD_NOT_FOUND = "hermes command not found: {}"
_ERR_TIMEOUT = "hermes command timed out after {:g}s"
_ERR_EXIT = "hermes command exited with code {}: {}"
_ERR_NO_OUTPUT = "hermes command produced no output (stdout empty){}"
_ERR_OS = "hermes command failed: {}: {}"


def _parse_verdict(stdout: str) -> dict[str, str]:
    """从执行体输出里取【裁定】（第 3 项）—— 取最后一个 `EXEC-VERDICT: {...}`。

    返回 {"verdict": "done|needs_decision|blocked|", "verdict_reason": "..."}。
    ★ 解析不出/非法值 ⇒ verdict=""（**没表态**）—— 由调度器保守处理, 绝不当作"完成"。
      真跑踩过: 执行体没表态却被记成完成。
    """
    out = {"verdict": "", "verdict_reason": ""}
    for m in _VERDICT_RE.finditer(stdout or ""):
        try:
            data = json.loads(m.group(1))
        except Exception:  # noqa: BLE001 — 坏 JSON 不算表态
            continue
        if not isinstance(data, dict):
            continue
        v = str(data.get("verdict") or "").strip().lower()
        if v in _VERDICTS:
            out = {"verdict": v, "verdict_reason": str(data.get("reason") or "")[:300]}
    return out


class HermesRuntimeAdapter(RuntimeAdapter):
    """Hermes Agent Runtime: 经 hermes CLI one-shot 调用执行 (Factory 唯一执行出口)。

    - RUNTIME_ID = "hermes-runtime" / TYPE = "agent": 内置 runtime 身份常量
      (RuntimeInfo 注册时建议使用, 与 BUILTIN_ADAPTERS 键一致)。
    - execute(request): 解析 input → 构造 prompt → subprocess 调 hermes -z →
      按失败规则转 ExecutionResult; 任何被列举失败均返回 FAILED 结果而非抛异常。
    """

    RUNTIME_ID = "hermes-runtime"
    TYPE = "agent"

    def __init__(self, command: str | None = None, timeout: float | None = None):
        """构造适配器; 参数优先于环境变量, 环境变量优先于默认值。"""
        self._command = command or os.environ.get(ENV_COMMAND) or DEFAULT_COMMAND
        raw_timeout = timeout if timeout is not None else os.environ.get(ENV_TIMEOUT)
        self._timeout = float(raw_timeout) if raw_timeout is not None else DEFAULT_TIMEOUT

    @property
    def command(self) -> str:
        """实际使用的 hermes 命令 (可被 FACTORY_HERMES_CMD 覆盖)。"""
        return self._command

    @property
    def timeout(self) -> float:
        """实际使用的超时秒数 (可被 FACTORY_HERMES_TIMEOUT 覆盖)。"""
        return self._timeout

    # ------------------------------------------------------------------ 执行

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """同步执行一次请求: 构造 hermes CLI 调用 → subprocess → ExecutionResult。

        失败处理 (全部转 FAILED, 不抛): 命令不存在 / 超时 / OS 级错误 /
        exit code != 0 / stdout 为空。未列举的意外异常交由上层防御
        (Runner 兜底转 FAILED, ADR-0007 决策 4)。
        """
        prompt = self._build_prompt(request)
        argv = [self._command, "-z", prompt]
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except FileNotFoundError:
            return self._failed(
                request, _ERR_CMD_NOT_FOUND.format(self._command),
            )
        except subprocess.TimeoutExpired:
            return self._failed(
                request, _ERR_TIMEOUT.format(self._timeout),
            )
        except OSError as exc:  # 权限等其他 OS 级错误 → FAILED (防御兜底)
            return self._failed(
                request, _ERR_OS.format(type(exc).__name__, exc),
            )

        stdout = completed.stdout or ""
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            return self._failed(
                request, _ERR_EXIT.format(completed.returncode, detail),
            )
        if not stdout.strip():
            detail = (completed.stderr or "").strip()
            suffix = f": {detail}" if detail else ""
            return self._failed(request, _ERR_NO_OUTPUT.format(suffix))

        return ExecutionResult(
            id=self._result_id(request.id),
            request_id=request.id,
            status=ExecutionStatus.SUCCESS,
            output={
                "stdout": stdout,
                "instruction": prompt,
                "runtime_id": self.RUNTIME_ID,
                "exit_code": completed.returncode,
                # ★ 裁定（第 3 项）: 执行体显式说自己干成了什么; 没这行 ⇒ verdict="" （没表态）
                **_parse_verdict(stdout),
            },
        )

    # ------------------------------------------------------------------ 输入解析

    @staticmethod
    def _build_prompt(request: ExecutionRequest) -> str:
        """从 request.input 解析 task/step/instruction/agent_id, 组合为 one-shot prompt。

        协议 (phase4c1-status §输入输出协议): input dict — {task, step, instruction,
        agent_id} 均可缺省; task/step/agent_id 作为前缀上下文行, instruction 为正文;
        全空时兜底 "execute execution <id>" (prompt 永不为空)。
        """
        data = request.input or {}
        parts: list[str] = []
        for key in ("task", "step", "agent_id"):
            value = data.get(key)
            if value:
                parts.append(f"{key}: {value}")
        instruction = data.get("instruction")
        if instruction:
            parts.append(str(instruction))
        if not parts:
            parts.append(f"execute execution {request.id}")
        parts.append(_VERDICT_CONTRACT)          # ★ 每次都要求显式裁定（第 3 项）
        return "\n".join(parts)

    # ------------------------------------------------------------------ 结果

    def _failed(self, request: ExecutionRequest, error: str) -> ExecutionResult:
        """构造 FAILED 结果 (失败处理统一出口: 不抛异常)。"""
        return ExecutionResult(
            id=self._result_id(request.id),
            request_id=request.id,
            status=ExecutionStatus.FAILED,
            error=error,
        )

    @staticmethod
    def _result_id(execution_id: str) -> str:
        """结果 id 从执行 id 派生 (1:1 确定性, 便于测试断言与审计追踪, 同 echo)。"""
        return f"EXR-{execution_id}"

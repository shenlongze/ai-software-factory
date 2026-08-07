"""factory-exec/exec/developer.py — Developer Agent MVP (第一个 AI Employee)。

设计依据 (docs/architecture/phase-a-execution-mvp-design.md §4 +
docs/architecture/developer-agent-reliability-model.md §2/§5):
```
能力: 读取项目 / 理解任务 / 修改代码 / 运行测试 / 生成 Patch
允许范围: ✅ 读取项目文件 (沙箱副本内) ✅ 修改代码 (沙箱内)
          ✅ 运行简单测试 (沙箱内) ✅ 生成 patch (git diff 格式)
          ✅ 输出执行报告 (做了什么/为什么/结果)
禁止范围: ❌ 修改沙箱外任何文件 ❌ 直接应用补丁 (需 Approval)
```

Phase A++++++-1 可靠性强化 (真实 Benchmark 22.2% 归因驱动):
1. max_tokens 8192 → 16384 (推理模型 reasoning 耗尽 → 空内容 ×4 修复)。
2. 空内容检测: Provider 层 (openai.py empty response → ProviderError) +
   Agent 层 (content 空 → DeveloperError, failure_reason=empty_content)。
3. 内建重试: 空内容/无解析 patch 重试 1 次, 重试时提示
   「上次输出为空, 请直接输出结果」(模型随机性兜底, 非 verifier 放水)。
4. 行号内联: source_files 每行加 N| 行号前缀 (模型精确定位 → diff 可应用
   ×2 修复); 超长文件只给 symbol 索引 + 前段预览。
5. 操作优先: 模型输出结构化操作列表 (<operations> JSON) → 系统确定性
   生成 patch (File Operation API, operations.py); 直接 diff 保留为
   fallback (保持兼容)。
6. 失败必记录: DeveloperError 携带结构化 failure_reason → 调用方
   (AgentRuntime/Runner) 落 ExperienceRecord/BenchmarkResult (不静默失败)。

职责 (MVP):
1. build_prompt(): 任务 + 项目上下文 + 内联源文件 (带行号) + 规范 + 反馈
   → Provider 输入 (Agent 不知道 Provider 细节 — 只调 generate())。
2. work(): 调 Provider (内建重试) → 解析 (操作优先, diff fallback) →
   生成报告 (DeveloperOutput; 失败 → DeveloperError 携带 failure_reason)。
3. parse_patch(): 从模型回复提取统一 diff (```diff 围栏 / <patch> 标签 /
   裸 diff 自动识别; 无 diff → DeveloperError 响亮, 不静默假成功)。
4. parse_operations(): 从模型回复提取结构化操作列表 (<operations> JSON);
   操作优先 — 系统执行操作生成 patch (确定性, 非模型手写 diff)。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .operations import OperationEngine, OperationError, StructuredCodeOperation
from .provider import ProviderError, ProviderInterface, ProviderRequest
from .validation import ValidationResult

#: 默认工程规范 (Developer 提示词; 可构造参数覆盖 — 不绑死项目约定)
DEFAULT_CONVENTIONS = (
    "1. 最小改动: 只修改任务要求的文件, 不重构无关代码\n"
    "2. 保持现有代码风格 (命名/缩进/注释语言)\n"
    "3. 优先输出结构化操作 (见 Output format); 无法用操作表达时才输出 unified diff\n"
    "4. 不引入新外部依赖 (除非任务明确要求)\n"
    "5. 修改后语法必须正确 (系统会做语法检查与验证循环)\n"
    "6. 你没有任何 shell / 文件系统访问能力 — 只能基于提示词中内联的源文件 "
    "(Relevant source files, 每行带行号) 编写操作/补丁\n"
    "7. 行号前缀 (如 `12|`) 仅用于定位参考 — 输出的代码内容绝不能包含行号前缀\n"
)

#: 单文件内联上限 (行数; 超出 → 只给 symbol 索引 + 前段预览, 防撑爆上下文)
_SOURCE_FILE_LINE_CAP = 3000
#: 超长文件的前段预览行数 (symbol 索引 + 预览, 上下文预算控制)
_LONG_FILE_PREVIEW_LINES = 200

#: 重试提示 (空内容/无解析 patch 后附加 — 强化: 直接输出结果)
_RETRY_HINT = (
    "上次输出为空或未产生有效修改 (empty content / no parseable operations or patch)。\n"
    "请直接输出结果: <operations> JSON 列表或 <patch> 统一 diff, 不要解释原因、"
    "不要空转推理。"
)


class FailureReason(str, Enum):
    """结构化失败原因 (ExperienceRecord/报告/复盘循环使用, 不静默失败)。

    取值与 docs/architecture/developer-agent-reliability-model.md §7
    「Cause: 结构化根因」对齐: max_tokens 不足 / hunk 不匹配 / 功能缺失 /
    verifier 失败 → empty_content / patch_apply_failed / validation_failed /
    verifier_failed。
    """

    EMPTY_CONTENT = "empty_content"          # 推理耗尽 max_tokens / 模型空输出
    NO_PATCH = "no_patch"                    # 回复无解析操作也无补丁
    PROVIDER_ERROR = "provider_error"        # HTTP/网络/key 等 Provider 层错误
    OPERATION_ERROR = "operation_error"      # 操作 JSON 非法/锚点定位失败/语法错误
    PATCH_APPLY_FAILED = "patch_apply_failed"  # diff 上下文不匹配 (rc 128)
    VALIDATION_FAILED = "validation_failed"  # 语法/测试命令验证失败 (验证循环内)
    VERIFIER_FAILED = "verifier_failed"      # 验收标准未达 (patch 可应用但功能缺失)
    SANDBOX_ERROR = "sandbox_error"          # 沙箱/文件系统错误
    OTHER = "other"


def classify_failure(error: str) -> str:
    """error 文本 → 结构化 FailureReason (稳定前缀匹配; 兜底 other)。

    供 AgentRuntime/_fail 与 Benchmark runner 在无显式 reason 时归类 —
    保证失败必记录结构化原因 (不静默)。
    """
    if not error:
        return FailureReason.OTHER.value
    if "empty content" in error or "empty response" in error:
        return FailureReason.EMPTY_CONTENT.value
    if "no parseable patch" in error or "empty patch" in error or "no parseable operations" in error:
        return FailureReason.NO_PATCH.value
    if "operation" in error and ("validation" in error or "error" in error):
        return FailureReason.OPERATION_ERROR.value
    if "patch apply failed" in error:
        return FailureReason.PATCH_APPLY_FAILED.value
    if "sandbox error" in error:
        return FailureReason.SANDBOX_ERROR.value
    # Provider 层错误 (HTTP/网络/key/超时): 消息可能带 "provider error:" 前缀
    # (AgentRuntime) 或裸 Provider 消息 ("openai http 429", "anthropic api key
    # missing") — 两者都要归类 provider_error (Benchmark runner 用裸消息)。
    if (
        "provider" in error
        or "api key" in error
        or "request failed" in error
        or "http " in error
        or "http:" in error
        or "rate limited" in error
        or "timed out" in error
    ):
        return FailureReason.PROVIDER_ERROR.value
    # verifier 失败 (验收标准未达, patch 可应用但功能缺失) 与验证循环失败
    # (语法/测试命令) 是两类 — 设计 FailureReason 区分, 分类须对应。
    if "verifier failed" in error:
        return FailureReason.VERIFIER_FAILED.value
    if "validation" in error:
        return FailureReason.VALIDATION_FAILED.value
    return FailureReason.OTHER.value


class DeveloperError(Exception):
    """Developer Agent 失败 (Provider 错误/无 patch 产出/补丁不可用)。

    failure_reason: 结构化分类 (FailureReason 值; 默认 other) — 调用方
    记录 Experience/报告必用, 失败不允许静默。
    """

    def __init__(self, message: str, *, failure_reason: str = FailureReason.OTHER.value) -> None:
        super().__init__(message)
        self.failure_reason = failure_reason


@dataclass
class DeveloperOutput:
    """Developer Agent 工作产物: patch + 报告 + usage + 原始回复 + 元数据。

    patch_text: 待应用补丁 (操作由系统确定性生成; diff fallback 为模型输出)。
    operations: 模型输出的结构化操作列表 (系统已据此生成 patch; 记录/报告用)。
    failure_reason: 空 = 成功; 非空 = 失败分类 (成功路径恒空)。
    retries: work() 内建重试次数 (0/1; 报告与复盘用)。
    """

    patch_text: str
    report: str
    usage: dict[str, Any] = field(default_factory=dict)
    raw_content: str = ""
    operations: list[StructuredCodeOperation] | None = None
    failure_reason: str = ""
    retries: int = 0


class DeveloperAgent:
    """Developer Agent MVP: prompt 组装 → Provider (重试) → 操作/diff 解析 → 报告。

    构造: provider (ProviderInterface), conventions (规范文本), max_tokens
    (缺省 16384 — Phase A++++++-1: 推理模型 reasoning 余量, 空内容修复)。
    零存储/零事件 (纯执行身份; 审计/持久化归 AgentRuntime/CLI)。
    """

    def __init__(
        self,
        provider: ProviderInterface,
        *,
        conventions: str = DEFAULT_CONVENTIONS,
        max_tokens: int = 16384,
    ) -> None:
        self._provider = provider
        self._conventions = conventions
        self._max_tokens = max_tokens

    @property
    def provider(self) -> ProviderInterface:
        return self._provider

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    # ------------------------------------------------------------------ prompt

    def build_prompt(
        self,
        *,
        objective: str,
        project_context: str = "",
        requirement: str = "",
        sandbox_path: str = "",
        source_files: list[tuple[str, str]] | None = None,
        extra_instruction: str = "",
        repo_context: str = "",
    ) -> str:
        """任务 + 项目上下文 + 内联源文件 (带行号) + 规范 + 反馈 → Provider 提示词。

        source_files: [(相对路径, 文件内容)] — 模型无文件访问能力, 修复目标
        代码必须内联进提示词; 空列表 → 不渲染该节 (Greenfield 从零构建场景)。
        每行加 `N|` 行号前缀 (定位参考; 输出代码内容不含前缀)。
        extra_instruction: 附加指令 (验证反馈/重试提示 — 验证循环输入)。
        repo_context: Repository Index 文本 (文件树 + symbol 索引; 探索步骤产物)。
        """
        lines = [
            "You are a Developer Agent working inside an AI Software Factory.",
            "You make minimal, correct code changes and return them as structured operations.",
            "",
            "## Task",
            objective.strip(),
        ]
        if requirement.strip():
            lines += ["", "## Requirement / Acceptance criteria", requirement.strip()]
        if project_context.strip():
            lines += ["", "## Project context", project_context.strip()]
        if repo_context.strip():
            lines += ["", "## Repository index", repo_context.strip()]
        if extra_instruction.strip():
            lines += ["", "## Previous attempt feedback", extra_instruction.strip()]
        if source_files:
            lines += ["", "## Relevant source files"]
            lines += [
                "(每行前缀 `N|` 为行号, 仅用于精确定位 location (symbol 或 "
                "line_range); 输出的代码内容绝不能包含行号前缀)"
            ]
            for rel, content in source_files:
                line_count = len(content.splitlines())
                lines += ["", f"### {rel} ({line_count} 行)"]
                lines += ["```dart", self._render_lines(content), "```"]
        if sandbox_path.strip():
            lines += [
                "",
                "## Sandbox",
                f"The project working copy is at: {sandbox_path}",
            ]
        lines += [
            "",
            "## Conventions",
            self._conventions,
            "",
            "## Output format",
            "PREFERRED — structured operations: a JSON list between <operations> "
            "and </operations> tags (one object per change):",
            '[{"operation": "replace_block", "target": "<relative path>", '
            '"location": {"symbol": "<function/class name>"}, "change": "<complete new block content>"}]',
            "Supported operations:",
            '- replace_block: replace the code block located by location {"symbol": name} '
            "or {\"line_range\": [start, end]} (1-based inclusive); change = complete new block content",
            "- modify_file: replace the whole file (change = complete new file content)",
            "- create_file: create a new file (change = complete content)",
            "- delete_file: delete the file",
            "Location by symbol is preferred (line numbers may drift). 'change' must be ",
            "the exact new code WITHOUT line-number prefixes. The system executes these ",
            "operations and generates the git patch deterministically — you do not need ",
            "to write diff hunks yourself.",
            "FALLBACK — if operations cannot express the change, output a unified diff ",
            "between <patch> and </patch> tags (git apply compatible). Patch file paths ",
            "are relative to the repo root (e.g. --- a/lib/editor/services/search_service.dart",
            "+++ b/lib/editor/services/search_service.dart).",
            "You have NO shell or file access: the code in 'Relevant source files'",
            "above is the only code you can see — write the complete fix based on it.",
            "If you cannot produce any change, put the literal text NO_CHANGE between ",
            "the tags (do NOT leave the tags empty).",
        ]
        return "\n".join(lines)

    @staticmethod
    def _render_lines(content: str) -> str:
        """文件内容 → 每行带 `N|` 行号前缀 (定位参考; 截断/空内容安全)。"""
        src_lines = content.splitlines()
        if not src_lines:
            return ""
        width = len(str(len(src_lines)))
        return "\n".join(f"{i + 1:>{width}}| {ln}" for i, ln in enumerate(src_lines))

    # ------------------------------------------------------------------ patch

    @staticmethod
    def parse_patch(content: str) -> str:
        """从模型回复提取统一 diff (围栏/标签/裸 diff 三级识别)。

        - ```diff ... ``` 围栏 (markdown 常见格式)
        - <patch> ... </patch> 标签 (输出格式约定, 首选)
        - 裸 diff (含 --- a/ 与 +++ b/ 行即视为 diff 全文)
        提取不到 → DeveloperError (响亮, 不静默假成功 — 无 patch 无法交付)。
        标签内容为 NO_CHANGE → 返回 "" (Agent 判断无需修改, 合法状态)。
        """
        if not content or not content.strip():
            raise DeveloperError("provider returned empty content (no patch)")
        # 1) <patch> 标签 (最可靠; NO_CHANGE 字面量 → 空补丁)
        m = re.search(r"<patch>(.*?)</patch>", content, re.DOTALL)
        if m:
            body = m.group(1)
            if body.strip().upper() == "NO_CHANGE":
                return ""
            return DeveloperAgent._strip_fence(body)
        # 2) ```diff 围栏
        m = re.search(r"```(?:diff)?\s*(.*?)```", content, re.DOTALL)
        if m:
            return DeveloperAgent._strip_fence(m.group(1))
        # 3) 裸 diff (含 --- a/ 与 +++ b/ 即视为 diff)
        lines = content.splitlines()
        has_old = any(line.startswith("--- ") for line in lines)
        has_new = any(line.startswith("+++ ") for line in lines)
        if has_old and has_new:
            return DeveloperAgent._strip_fence(content)
        raise DeveloperError(
            "provider response contains no parseable patch "
            "(expected <patch>...</patch> or ```diff ... ``` block)"
        )

    @staticmethod
    def _strip_fence(text: str) -> str:
        """规范化 patch 文本: 去首尾空行, 保证以单个换行结尾 (git apply 容错)。

        strip("\\n") 会剥掉 EOF 换行 → git apply 报 "corrupt patch at line N"
        (实测); 规范化后统一以 \\n 结尾。

        尾行只剥**纯空行** ("") 不剥空白行 (" "): diff 末尾的 " " 是合法
        context 行 (文件以空行结尾时 git diff 产出), 剥掉 → hunk 计数错 →
        "corrupt patch at line N" (实测)。首行空白 (围栏/标签后填充) 可全剥。
        """
        lines = text.splitlines()
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and lines[-1] == "":
            lines.pop()
        if not lines:
            return ""
        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------- operations

    @staticmethod
    def parse_operations(content: str) -> list[StructuredCodeOperation] | None:
        """从模型回复提取结构化操作列表 (<operations> JSON; 操作优先)。

        - <operations> ... </operations> 标签 (输出格式约定, 首选);
        - ```operations / ```json 围栏内为操作数组 (兼容 markdown 形态)。
        解析结果:
        - None: 没有操作节 (调用方走 diff fallback);
        - []: 显式空操作列表 (= NO_CHANGE, 合法状态);
        - 非空列表: 操作模型实例列表。
        JSON 解析失败 → None (截断常见; 走 fallback/重试); 结构非法
        (非 list / 元素非 dict / 字段校验失败) → DeveloperError
        (operation_error — 响亮, 不静默吞模型格式错误)。
        """
        if not content or not content.strip():
            return None
        body: str | None = None
        m = re.search(r"<operations>(.*?)</operations>", content, re.DOTALL)
        if m:
            body = m.group(1)
        else:
            m = re.search(r"```(?:operations|json)\s*(.*?)```", content, re.DOTALL)
            if m and m.group(1).strip().startswith("["):
                body = m.group(1)
        if body is None:
            return None
        body = body.strip()
        if not body:
            return []  # 显式空操作列表 → 无修改意图
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return None  # JSON 截断/非法 → fallback diff 或重试
        if not isinstance(data, list):
            raise DeveloperError(
                "operations JSON 结构非法: 顶层须为列表 "
                f"(收到 {type(data).__name__})",
                failure_reason=FailureReason.OPERATION_ERROR.value,
            )
        ops: list[StructuredCodeOperation] = []
        for i, item in enumerate(data):
            if not isinstance(item, dict):
                raise DeveloperError(
                    f"operations JSON 结构非法: 第 {i} 个元素须为对象 (收到 {type(item).__name__})",
                    failure_reason=FailureReason.OPERATION_ERROR.value,
                )
            try:
                ops.append(StructuredCodeOperation.model_validate(item))
            except Exception as exc:  # pydantic ValidationError 等
                raise DeveloperError(
                    f"operations 字段校验失败 (第 {i} 个): {exc}",
                    failure_reason=FailureReason.OPERATION_ERROR.value,
                ) from exc
        return ops

    def _parse_output(
        self, content: str, sandbox_path: str
    ) -> tuple[str, list[StructuredCodeOperation] | None] | None:
        """模型回复 → (patch_text, operations) — 操作优先, diff fallback。

        返回 None = 无有效产出 (空内容/无解析操作也无解析补丁) → 重试信号;
        抛 DeveloperError = 操作解析/锚点/语法失败 (operation_error, 不重试 —
        能力判定, 重试是放水)。
        """
        if not content or not content.strip():
            return None
        ops = self.parse_operations(content)
        if ops is not None:
            if not ops:
                return ("", [])  # 显式空操作列表 = NO_CHANGE
            engine = OperationEngine(sandbox_path)
            try:
                plan = engine.plan(ops)
            except OperationError as exc:
                raise DeveloperError(
                    f"operation error: {exc}",
                    failure_reason=FailureReason.OPERATION_ERROR.value,
                ) from exc
            validation = engine.validate(ops)
            if not validation.passed:
                raise DeveloperError(
                    "operation validation failed: " + "; ".join(validation.errors),
                    failure_reason=FailureReason.OPERATION_ERROR.value,
                )
            return (plan.to_diff(), ops)
        try:
            patch_text = self.parse_patch(content)
        except DeveloperError:
            return None  # 无解析补丁 → 重试信号
        return (patch_text, None)

    @staticmethod
    def _accumulate_usage(acc: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
        """跨重试累计 usage (token/成本真实总花费; 非数值字段取末次)。"""
        out = dict(usage)
        for k, v in acc.items():
            if isinstance(v, (int, float)) and isinstance(out.get(k), (int, float)):
                out[k] = v + out[k]
        return out

    @staticmethod
    def _read_source_files(
        sandbox_path: str, source_files: list[str]
    ) -> list[tuple[str, str]]:
        """从沙箱副本读取源文件内容 → [(相对路径, 内容)] (供 prompt 内联)。

        - 文件缺失 → DeveloperError 响亮 (样本 source_files 配错立即暴露,
          不静默丢上下文);
        - 超长文件 (>_SOURCE_FILE_LINE_CAP 行) → symbol 索引 + 前段预览
          (symbol 定位供模型锚点; 防撑爆上下文);
        - 读取失败 (权限/编码) → DeveloperError。
        """
        if not source_files:
            return []
        root = Path(sandbox_path)
        embedded: list[tuple[str, str]] = []
        for rel in source_files:
            path = root / rel
            if not path.is_file():
                raise DeveloperError(
                    f"source file not found in sandbox: {rel} (sandbox: {sandbox_path})"
                )
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError as exc:
                raise DeveloperError(f"source file read failed: {rel}: {exc}") from exc
            if len(lines) > _SOURCE_FILE_LINE_CAP:
                lines = DeveloperAgent._long_file_preview(rel, lines)
            embedded.append((rel, "\n".join(lines)))
        return embedded

    @staticmethod
    def _long_file_preview(rel: str, lines: list[str]) -> list[str]:
        """超长文件 → symbol 索引 + 前段预览 (防撑爆上下文; 确定性)。"""
        from .repo_index import RepositoryIndexer

        total = len(lines)
        symbols = RepositoryIndexer.scan_symbols("\n".join(lines))
        sym_text = "\n".join(
            f"// {s.kind.value} {s.name} @ line {s.line}" for s in symbols[:80]
        )
        preview = lines[:_LONG_FILE_PREVIEW_LINES]
        head = [
            f"// (文件 {rel} 共 {total} 行, 超过 {_SOURCE_FILE_LINE_CAP} 行上限 —",
            f"//  以下为 symbol 索引 + 前 {_LONG_FILE_PREVIEW_LINES} 行预览; "
            "完整文件不内联)",
        ]
        return head + [sym_text] + [""] + preview

    # ------------------------------------------------------------------ report

    @staticmethod
    def build_report(
        *,
        request: Any,
        raw_content: str,
        patch_text: str,
        validation: ValidationResult | None = None,
        duration: float = 0.0,
        usage: dict[str, Any] | None = None,
        operations: list[StructuredCodeOperation] | None = None,
        validation_attempts: int = 1,
    ) -> str:
        """执行报告 (做了什么/为什么/结果 + 验证/成本/耗时 — 审批 Review 输入)。

        raw_content 摘要: 取模型回复中 <patch>/<operations> 标签前的说明文本
        (strip 后截断 500 字符), 无标签则全文首 500 字符。
        operations: 结构化操作数 (报告「系统生成 patch」来源);
        validation_attempts: 验证循环尝试次数 (1 = 一次通过; >1 = 自动修复轮)。
        """
        summary = DeveloperAgent._summary_of(raw_content)
        lines = [
            f"# Execution Report — {request.id}",
            f"- task_id: {request.task_id or '-'}",
            f"- objective: {request.objective}",
            "",
            "## What the agent did",
            summary or "(no summary provided)",
        ]
        if patch_text.strip():
            src = (
                f"generated from {len(operations)} structured operations"
                if operations
                else "model-provided unified diff"
            )
            lines += [
                "",
                "## Patch",
                f"diff lines: {len(patch_text.splitlines())} ({src})",
                "human review required before apply (execution.approved gate)",
            ]
        else:
            lines += ["", "## Patch", "(no code change — agent judged none needed)"]
        if validation is not None:
            lines += [
                "",
                "## Validation",
                f"result: {'PASS' if validation.passed else 'FAIL'}",
                validation.output,
            ]
            if validation_attempts > 1:
                lines += [
                    f"validation loop: {validation_attempts} attempts "
                    f"({validation_attempts - 1} automatic fix round(s))"
                ]
        if usage:
            lines += ["", "## Usage", str(usage)]
        lines += ["", "## Cost & duration", f"duration: {duration:.2f}s"]
        return "\n".join(lines)

    @staticmethod
    def _summary_of(content: str) -> str:
        """模型回复摘要: <patch>/<operations> 标签前文本 (说明部分); 无 → 截断。"""
        m = re.search(r"<patch>|<operations>", content)
        head = content[: m.start()] if m else content
        head = head.strip()
        return head[:500] if head else "(no summary)"

    # ------------------------------------------------------------------ work

    def work(
        self,
        *,
        request: Any,
        project_context: str = "",
        sandbox_path: str = "",
        source_files: list[str] | None = None,
        extra_instruction: str = "",
        repo_context: str = "",
        max_retries: int = 1,
    ) -> DeveloperOutput:
        """调 Provider (内建重试) → 解析 (操作优先) → 报告 (失败 → DeveloperError)。

        重试策略 (模型随机性兜底, 非 verifier 放水): 空内容 / 无解析操作也
        无解析补丁 → 重试 1 次, 重试时提示「上次输出为空, 请直接输出结果」;
        Provider 层错误 (HTTP/网络/key) / 操作锚点失败 / 语法失败 → 不重试
        (环境/能力判定, 重试掩盖不了)。usage 跨重试累计 (诚实总花费)。

        source_files: 需要内联进提示词的源文件相对路径 (从 sandbox_path 读取
        内容, 每行带行号; 模型无文件访问能力, 修复目标代码靠此进入上下文)。
        extra_instruction: 附加指令 (验证循环反馈 — 上轮验证失败输出)。
        repo_context: Repository Index 文本 (文件树 + symbol 索引)。
        max_retries: 空内容/无解析的重试次数上限 (缺省 1 — 任务约束)。
        """
        embedded = self._read_source_files(sandbox_path, source_files or [])
        started = time.monotonic()
        usage_acc: dict[str, Any] = {}
        retry_hint = ""
        last_error = ""
        last_reason = FailureReason.OTHER
        for attempt in range(max_retries + 1):
            prompt = self.build_prompt(
                objective=request.objective,
                project_context=project_context,
                requirement=getattr(request, "requirement", "") or "",
                sandbox_path=sandbox_path,
                source_files=embedded,
                repo_context=repo_context,
                extra_instruction=(
                    extra_instruction if attempt == 0 else f"{extra_instruction}\n{retry_hint}"
                ).strip(),
            )
            try:
                response = self._provider.generate(
                    ProviderRequest(
                        task_context=prompt,
                        sandbox_path=sandbox_path,
                        max_tokens=self._max_tokens,
                    )
                )
            except ProviderError as exc:
                msg = str(exc)
                reason = (
                    FailureReason.EMPTY_CONTENT
                    if ("empty" in msg or "no content" in msg)
                    else FailureReason.PROVIDER_ERROR
                )
                if attempt < max_retries and reason is FailureReason.EMPTY_CONTENT:
                    last_error, last_reason = msg, reason
                    retry_hint = _RETRY_HINT
                    continue
                raise DeveloperError(msg, failure_reason=reason.value) from exc
            if not response.ok:
                raise DeveloperError(
                    response.error or "provider returned error",
                    failure_reason=FailureReason.PROVIDER_ERROR.value,
                )
            usage_acc = self._accumulate_usage(usage_acc, response.usage)
            parsed = self._parse_output(response.content, sandbox_path)
            if parsed is not None:
                patch_text, operations = parsed
                duration = time.monotonic() - started
                report = self.build_report(
                    request=request,
                    raw_content=response.content,
                    patch_text=patch_text,
                    duration=duration,
                    usage=usage_acc,
                    operations=operations,
                )
                return DeveloperOutput(
                    patch_text=patch_text,
                    report=report,
                    usage=usage_acc,
                    raw_content=response.content,
                    operations=operations,
                    failure_reason="",
                    retries=attempt,
                )
            # 无有效产出 → 重试 (限 max_retries 次)
            if not response.content.strip():
                last_error = "provider returned empty content (no patch)"
                last_reason = FailureReason.EMPTY_CONTENT
            else:
                last_error = (
                    "provider response contains no parseable patch or operations "
                    "(expected <operations> JSON or <patch> unified diff)"
                )
                last_reason = FailureReason.NO_PATCH
            if attempt < max_retries:
                retry_hint = _RETRY_HINT
                continue
        suffix = f" (after {max_retries} retry)" if max_retries > 0 else ""
        raise DeveloperError(
            f"{last_error}{suffix}", failure_reason=last_reason.value
        )

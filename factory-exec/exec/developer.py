"""factory-exec/exec/developer.py — Developer Agent MVP (第一个 AI Employee)。

设计依据 (docs/architecture/phase-a-execution-mvp-design.md §4):
```
能力: 读取项目 / 理解任务 / 修改代码 / 运行测试 / 生成 Patch
允许范围: ✅ 读取项目文件 (沙箱副本内) ✅ 修改代码 (沙箱内)
          ✅ 运行简单测试 (沙箱内) ✅ 生成 patch (git diff 格式)
          ✅ 输出执行报告 (做了什么/为什么/结果)
禁止范围: ❌ 修改沙箱外任何文件 ❌ 直接应用补丁 (需 Approval)
```

职责 (MVP):
1. build_prompt(): 任务 + 项目上下文 + 规范 → Provider 输入 (Agent 不知道
   Provider 细节 — 只调 generate()).
2. work(): 调 Provider → 解析 patch → 生成报告 (DeveloperOutput 三件套:
   patch_text/report/usage; 失败 → DeveloperError 携带 ProviderError 原因).
3. parse_patch(): 从模型回复提取统一 diff (```diff 围栏 / <patch> 标签 /
   裸 diff 自动识别; 无 diff → DeveloperError 响亮, 不静默假成功).

报告 (做了什么/为什么/结果): 结构化模板 + 验证结果 + 成本/耗时 — 供审批人
Review (Human 看 patch 再决定, 设计 §5.4/§6)。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from .provider import ProviderError, ProviderInterface, ProviderRequest
from .validation import ValidationResult

#: 默认工程规范 (Developer 提示词; 可构造参数覆盖 — 不绑死项目约定)
DEFAULT_CONVENTIONS = (
    "1. 最小改动: 只修改任务要求的文件, 不重构无关代码\n"
    "2. 保持现有代码风格 (命名/缩进/注释语言)\n"
    "3. 补丁必须是 unified diff 格式 (git diff 可应用)\n"
    "4. 不引入新外部依赖 (除非任务明确要求)\n"
    "5. 修改后语法必须正确 (沙箱会做语法检查)\n"
)


class DeveloperError(Exception):
    """Developer Agent 失败 (Provider 错误/无 patch 产出/补丁不可用)。"""


@dataclass
class DeveloperOutput:
    """Developer Agent 工作产物: patch + 报告 + usage + 原始回复。"""

    patch_text: str
    report: str
    usage: dict[str, Any] = field(default_factory=dict)
    raw_content: str = ""


class DeveloperAgent:
    """Developer Agent MVP: prompt 组装 → Provider → patch 解析 → 报告。

    构造: provider (ProviderInterface), conventions (规范文本), max_tokens。
    零存储/零事件 (纯执行身份; 审计/持久化归 AgentRuntime/CLI)。
    """

    def __init__(
        self,
        provider: ProviderInterface,
        *,
        conventions: str = DEFAULT_CONVENTIONS,
        max_tokens: int = 4096,
    ) -> None:
        self._provider = provider
        self._conventions = conventions
        self._max_tokens = max_tokens

    @property
    def provider(self) -> ProviderInterface:
        return self._provider

    # ------------------------------------------------------------------ prompt

    def build_prompt(
        self,
        *,
        objective: str,
        project_context: str = "",
        requirement: str = "",
        sandbox_path: str = "",
    ) -> str:
        """任务 + 项目上下文 + 规范 → Provider 提示词 (Agent 输入组装)。"""
        lines = [
            "You are a Developer Agent working inside an AI Software Factory.",
            "You make minimal, correct code changes and return them as a unified diff.",
            "",
            "## Task",
            objective.strip(),
        ]
        if requirement.strip():
            lines += ["", "## Requirement / Acceptance criteria", requirement.strip()]
        if project_context.strip():
            lines += ["", "## Project context", project_context.strip()]
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
            "Reply with a short summary of what you changed and why (2-4 sentences),",
            "then the patch ONLY between <patch> and </patch> tags in unified diff",
            "format (git apply compatible). If no change is needed, put the literal",
            "text NO_CHANGE between the tags.",
        ]
        return "\n".join(lines)

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
    ) -> str:
        """执行报告 (做了什么/为什么/结果 + 验证/成本/耗时 — 审批 Review 输入)。

        raw_content 摘要: 取模型回复中 <patch> 标签前的说明文本 (strip 后
        截断 500 字符), 无标签则全文首 500 字符。
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
            lines += [
                "",
                "## Patch",
                f"diff lines: {len(patch_text.splitlines())}",
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
        if usage:
            lines += ["", "## Usage", str(usage)]
        lines += ["", "## Cost & duration", f"duration: {duration:.2f}s"]
        return "\n".join(lines)

    @staticmethod
    def _summary_of(content: str) -> str:
        """模型回复摘要: <patch> 标签前文本 (说明部分); 无标签 → 全文截断。"""
        m = re.search(r"<patch>", content)
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
    ) -> DeveloperOutput:
        """调 Provider → 解析 patch → 报告 (失败 → DeveloperError 响亮)。"""
        prompt = self.build_prompt(
            objective=request.objective,
            project_context=project_context,
            requirement=request.requirement,
            sandbox_path=sandbox_path,
        )
        started = time.monotonic()
        try:
            response = self._provider.generate(
                ProviderRequest(
                    task_context=prompt,
                    sandbox_path=sandbox_path,
                    max_tokens=self._max_tokens,
                )
            )
        except ProviderError as exc:
            raise DeveloperError(str(exc)) from exc
        if not response.ok:
            raise DeveloperError(response.error or "provider returned error")
        try:
            patch_text = self.parse_patch(response.content)
        except DeveloperError:
            raise
        except Exception as exc:  # pragma: no cover — 防御兜底
            raise DeveloperError(f"patch parse failed: {exc}") from exc
        duration = time.monotonic() - started
        report = self.build_report(
            request=request,
            raw_content=response.content,
            patch_text=patch_text,
            duration=duration,
            usage=response.usage,
        )
        return DeveloperOutput(
            patch_text=patch_text,
            report=report,
            usage=dict(response.usage),
            raw_content=response.content,
        )

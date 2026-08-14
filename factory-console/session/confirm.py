"""factory-console/session/confirm.py — ConfirmationGate: 敏感 Action 确认流 (S10-048 P4)。

最小治理 (设计 §2.5):
- sensitive_actions: 需要用户确认后才执行的 Action 集合
  (默认 {"create_project", "run_task"} — 创建/执行类副作用操作)
- confirm(action_name, intent, context, *, confirm_fn=None) -> bool:
    - 非敏感 → 直接放行 (True)
    - 敏感   → 打印执行计划 ("将执行: <action> (<intent 摘要>)") + 请求 y/N:
        - confirm_fn 注入 (测试/宿主定制输入源, 避免阻塞 input)
        - 缺省 input() 交互读取; 无 stdin 可用 (EOFError / OSError —
          自动化/测试上下文, 含 pytest 捕获 stdin) → 放行 (保持 P1
          "gate 未激活 = 直接执行" 的非阻塞语义)
    - 回答 y/yes (不区分大小写) → True; 其余 (含空/回车) → False (默认 No)

边界 (设计 §2.7):
- Gate 只做确认决策, 不复制/不执行业务; 执行仍由 Action 负责
- 纯标准库, 零新依赖
"""

from __future__ import annotations

from typing import Callable, Optional

from .action import ExecutionContext
from .intent import IntentObject

#: 默认敏感 Action 集合 (设计 §2.5) — 请求确认后才执行
SENSITIVE_ACTIONS: frozenset[str] = frozenset({"create_project", "run_task"})

#: 确认回答集合 (y/yes 不区分大小写; 其余 → 拒绝, 默认 No)
_APPROVE_ANSWERS: frozenset[str] = frozenset({"y", "yes"})

#: 确认提示 (y/N 约定: 回车/其他 → 拒绝)
_CONFIRM_PROMPT = "确认执行? (y/N) "


class ConfirmationGate:
    """敏感 Action 确认门 (最小治理): 敏感 → 打印计划 + 请求 y/N; 非敏感 → 放行。"""

    sensitive_actions: set[str] = set(SENSITIVE_ACTIONS)

    def confirm(
        self,
        action_name: str,
        intent: IntentObject,
        context: Optional[ExecutionContext] = None,
        *,
        confirm_fn: Optional[Callable[[], str]] = None,
    ) -> bool:
        """确认决策: 非敏感 → True (放行); 敏感 → 计划确认流。

        confirm_fn: 注入的回答输入源 (Callable[[], str], 返回原始回答) —
        测试注入避免阻塞 input(); 缺省用 input() 交互读取。
        """
        if action_name not in self.sensitive_actions:
            return True  # 非敏感 → 放行
        print(f"将执行: {self._render_plan(action_name, intent)}")
        if confirm_fn is not None:
            answer = confirm_fn()
        else:
            try:
                answer = input(_CONFIRM_PROMPT)
            except (EOFError, OSError):
                # 无 stdin 可用 (EOFError: stdin 关闭; OSError: 输出被捕获/
                # 测试环境) — 无法征询用户 → 放行: 保持 P1 "gate 未激活 =
                # 直接执行" 的非阻塞语义; 交互终端 (tty) 才会真正请求 y/N
                return True
        return self._parse_answer(answer)

    def _render_plan(self, action_name: str, intent: Optional[IntentObject]) -> str:
        """执行计划摘要: "<action> (<intent 摘要>)" — intent 摘要 = 类型 + 参数。"""
        summary = "?"
        if intent is not None:
            parts = [intent.intent_type] if intent.intent_type else []
            if intent.parameters:
                parts.append(str(intent.parameters))
            if parts:
                summary = " ".join(parts)
        return f"{action_name} ({summary})"

    @staticmethod
    def _parse_answer(answer: str) -> bool:
        """y/yes (不区分大小写) → 确认; 其余 (含空) → 拒绝 (y/N 默认 No)。"""
        return (answer or "").strip().lower() in _APPROVE_ANSWERS

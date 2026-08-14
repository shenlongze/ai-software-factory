"""factory-console/session/intent.py — Intent Layer 基础 (S10-047 Task 005)。

自然语言入口: 解析为结构化 Intent (绝不生成/执行 shell 命令)。
设计: docs/sprint10/S10-046-intent-layer-design.md (§2 Intent Object / §4 注册表 / §6 边界)

组件:
- IntentObject — 结构化意图 (intent_type/params/constraints/confidence/raw)
- IntentParser (ABC) — 解析接口; 未来 LLMIntentParser 的扩展点
  (LLM 只输出结构化 Intent, 见设计 §3 Q1 — 不生成命令字符串)
- KeywordIntentParser — 当前规则 mock (关键词子串 → intent_type, 不调 LLM),
  供会话联调与测试; LLM 版后续 Task 以同接口替换

边界 (S10-046 §6):
- Intent 只映射到注册 Intent 类型 (create_project/run_task/show_cost/show_status),
  不生成/执行任意命令
- 本 Task 不调 LLM、不引入依赖 (纯标准库); 未识别 → None (请求澄清, 不猜测)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

#: Intent 类型注册表 (S10-046 §4 初始子集 — 本 Task 涉及 4 类 + S10-048 P0 list_projects)
INTENT_CREATE_PROJECT = "create_project"
INTENT_RUN_TASK = "run_task"
INTENT_SHOW_COST = "show_cost"
INTENT_SHOW_STATUS = "show_status"
INTENT_LIST_PROJECTS = "list_projects"

#: KeywordIntentParser 关键词规则表 (顺序 = 优先级, 确定性无歧义):
#: (关键词元组, intent_type, 参数键 — 命中后取关键词后剩余文本作为参数值)
_KEYWORD_RULES: tuple[tuple[tuple[str, ...], str, Optional[str]], ...] = (
    (("花了多少", "成本", "费用"), INTENT_SHOW_COST, None),
    (("创建", "做一个", "开发一个"), INTENT_CREATE_PROJECT, "name"),
    (("加", "修复", "写"), INTENT_RUN_TASK, "objective"),
    (("项目列表", "有哪些项目", "列出项目"), INTENT_LIST_PROJECTS, None),
    (("状态", "看看"), INTENT_SHOW_STATUS, None),
)


@dataclass
class IntentObject:
    """结构化意图 (S10-046 §2): 解析结果, 非 shell 命令。

    intent_type: 注册 Intent 类型 (create_project/run_task/show_cost/show_status)
    params:      参数 (如 {"name": "APP", "objective": "测试", "period": "session"})
    constraints: 约束 (如 provider/agent/budget_usd — 后续 Policy Check 使用)
    confidence:  解析置信度 0-1 (LLM 版为模型置信度; 规则 mock 确定性匹配 = 1.0)
    raw:         原始输入 (审计)
    """

    intent_type: str
    params: dict[str, Any] = field(default_factory=dict)
    constraints: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    raw: str = ""
    source: str = ""  # S10-048 §2.2: "cli" | "chat" | "agent" | "api" | "session" (会话派发时注入)
    metadata: dict[str, Any] = field(default_factory=dict)  # 扩展: user_id/workspace/session_id

    @property
    def type(self) -> str:
        """intent_type 别名 (验收口径: type/confidence/parameters/raw)。"""
        return self.intent_type

    @property
    def parameters(self) -> dict[str, Any]:
        """params 别名 (验收口径: type/confidence/parameters/raw)。"""
        return self.params


class IntentParser(ABC):
    """Intent 解析接口 (未来 LLM 扩展点, S10-046 §3 Q1)。

    唯一契约: parse(text) -> IntentObject | None — 未识别 → None (由上层请求
    澄清, 绝不猜测执行)。LLMIntentParser (后续 Task 实现): LLM 结构化输出
    (JSON mode / function calling, 输出 {"intent_type", "params", "constraints"}),
    结果仍封装为 IntentObject — 不生成 shell 命令字符串。
    """

    @abstractmethod
    def parse(self, text: str) -> Optional[IntentObject]:
        """解析自然语言输入 → 结构化 Intent; 未识别 → None。"""


class KeywordIntentParser(IntentParser):
    """规则 mock 解析器 (不调 LLM): 关键词子串匹配 → 结构化 Intent。

    命中规则 → IntentObject (confidence=1.0 — 确定性规则匹配);
    未命中/空输入 → None (未识别)。规则见 _KEYWORD_RULES (顺序 = 优先级)。
    """

    def __init__(
        self, rules: Optional[tuple[tuple[tuple[str, ...], str, Optional[str]], ...]] = None
    ) -> None:
        self._rules = rules if rules is not None else _KEYWORD_RULES

    def parse(self, text: str) -> Optional[IntentObject]:
        raw = text.strip() if text else ""
        if not raw:
            return None
        for keywords, intent_type, param_key in self._rules:
            for keyword in keywords:
                if keyword not in raw:
                    continue
                params: dict[str, Any] = {}
                if intent_type == INTENT_SHOW_COST:
                    # 设计 §2 示例口径: show_cost {period: "session"}
                    params["period"] = "session"
                elif param_key:
                    hint = raw.split(keyword, 1)[1].strip()
                    if hint:
                        params[param_key] = hint
                return IntentObject(
                    intent_type=intent_type,
                    params=params,
                    constraints={},
                    confidence=1.0,
                    raw=raw,
                )
        return None

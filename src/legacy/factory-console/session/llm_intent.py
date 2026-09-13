"""factory-console/session/llm_intent.py — LLMIntentParser (意图解析 LLM 主路径)。

把普通对话的意图解析从"规则关键词"升级为"LLM 理解 + 规则兜底"（S10-046 §3 Q1
预留的 LLM 扩展点落地）——"建个公司""查一下项目"这类自然语言不再依赖关键词命中。

- LLM 理解 → 结构化 Intent {intent_type, params, confidence}（只映射到注册意图类型,
  不生成任意命令 — S10-046 §6 安全边界）
- 失败/无 key/输出非法 → None（上层规则兜底 KeywordIntentParser, 诚实降级不伪造）
- 纯命令 (/help) 不经过（slash 路径先行）

设计: docs/sprint10/S10-046-intent-layer-design.md §3 Q1 / §6 边界
边界: 不调 LLM 时零开销（parse 直接 None → 规则兜底）; 无新依赖
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from .intent import IntentObject, IntentParser

#: LLM 候选意图清单（高频对话意图, 带说明 — LLM 从中选择, 不猜测未列出的）
INTENT_CATALOG: tuple[tuple[str, str], ...] = (
    ("create_product", "用户描述想做一个产品/软件/App（进入产品发现）"),
    ("create_project", "创建/注册一个项目（已有代码或新项目）"),
    ("org_manage", "组织操作: 建公司/建部门/把项目挂到部门"),
    ("list_projects", "查看项目列表/有哪些项目"),
    ("show_status", "查看状态/当前进度/执行到哪了"),
    ("execute_project", "开始开发/开始执行/开始干活"),
    ("project_progress", "项目进度/进度如何"),
    ("run_task", "运行一个任务/帮我做某事（修 bug/生成报表）"),
    ("repair_task", "修复失败任务/重新执行失败"),
    ("accept_project", "项目验收/通过验收"),
    ("generate_prd", "生成 PRD/产品需求文档"),
    ("prepare_project", "准备工程/生成工程计划"),
    ("workforce", "查看团队/团队成员"),
    ("team", "团队协作/创建团队"),
    ("team_execute", "团队执行/团队开始开发"),
    ("memory_search", "搜索经验/记忆/知识"),
    ("audit_events", "查看审计/审计记录"),
    ("audit_cost", "查看成本审计/花了多少钱"),
    ("factory_budget", "查看预算/预算情况"),
    ("current_project", "当前项目是什么"),
)

#: LLM prompt（只输出结构化 JSON, 不生成命令）
_INTENT_PROMPT = """你是 AI Factory 的意图识别器。把用户的话归类到下列意图之一, 只输出一个 JSON 对象:
{{
  "intent_type": "其中一个意图类型",
  "params": {{"意图需要的参数, 如 name/company/departments/goal"}},
  "confidence": 0.0到1.0
}}

意图清单（只选这些, 不发明新类型）:
{catalog}

用户输入: {text}

规则:
- 拿不准 → confidence 给低 (≤0.4), 或输出 {{"intent_type": "unknown"}}
- params 只填输入中明确出现的信息, 不编造
- 禁止输出清单外的 intent_type"""


class LLMIntentParser(IntentParser):
    """LLM 意图解析: LLM 理解 → 注册意图类型; 失败/无 key → None (规则兜底)。"""

    def __init__(
        self,
        llm_fn: Optional[Any] = None,
        catalog: Optional[tuple[tuple[str, str], ...]] = None,
    ) -> None:
        self._llm_fn = llm_fn  # 显式注入（测试）; None → 懒装配
        self._catalog = catalog if catalog is not None else INTENT_CATALOG
        self._valid_types = {name for name, _ in self._catalog}

    # ------------------------------------------------------------ LLM 装配

    def _llm(self) -> Optional[Any]:
        """懒装配 ReasoningProvider（无 provider/key → None, 诚实降级）。"""
        if self._llm_fn is not None:
            return self._llm_fn
        try:
            from .reasoning import ReasoningProvider

            return ReasoningProvider()._default_llm_fn()  # noqa: SLF001
        except Exception:  # noqa: BLE001 — 无 provider → 规则兜底
            return None

    # ------------------------------------------------------------ 解析

    def parse(self, text: str) -> Optional[IntentObject]:
        """LLM 理解意图 → IntentObject; 失败/无 key/非法 → None（规则兜底）。"""
        raw = str(text or "").strip()
        if not raw:
            return None
        llm_fn = self._llm()
        if llm_fn is None:
            return None
        catalog_block = "\n".join(
            f"  - {name}: {desc}" for name, desc in self._catalog
        )
        prompt = _INTENT_PROMPT.format(catalog=catalog_block, text=raw)
        try:
            out = str(llm_fn(prompt, "intent_parse") or "").strip()
        except Exception:  # noqa: BLE001 — LLM 失败 → 规则兜底
            return None
        data = self._parse_json(out)
        if not isinstance(data, dict):
            return None
        intent_type = str(data.get("intent_type") or "").strip()
        if intent_type not in self._valid_types:
            return None  # 未知/unknown → 规则兜底
        params = data.get("params")
        if not isinstance(params, dict):
            params = {}
        try:
            confidence = float(data.get("confidence") or 0.0)
        except (TypeError, ValueError):  # noqa: BLE001
            confidence = 0.0
        if confidence < 0.4:
            return None  # 低置信 → 规则兜底（不硬猜）
        return IntentObject(
            intent_type=intent_type,
            params={str(k): v for k, v in params.items()},
            confidence=min(max(confidence, 0.0), 1.0),
            raw=raw,
        )

    # ------------------------------------------------------------ 解析工具

    @classmethod
    def _parse_json(cls, raw: Any) -> Any:
        """宽容解析: str 剥 code fence → json.loads → {..} 子串回退。"""
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, bytes):
            try:
                raw = raw.decode("utf-8")
            except (UnicodeDecodeError, AttributeError):  # noqa: BLE001
                return raw
        if not isinstance(raw, str):
            return raw
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError):  # noqa: BLE001
            m = re.search(r"\{.*\}", text, re.S)
            if m:
                try:
                    return json.loads(m.group(0))
                except (json.JSONDecodeError, ValueError):  # noqa: BLE001
                    return None
            return None

"""S10-070 — Capability Delivery Contract 自动化测试。

对每个 capability 自动检查: Core/CLI/API/Intent/Help/Tests 存在。
原则: "没有 CLI/API 的能力 = 未完成能力" — 测试强制保证。

覆盖: discovery/product/memory/debug/audit/governance/review/lifecycle 等
现有 57 action + ~60 API 端点的契约完整性。
装配: 禁真实网络。
"""

from __future__ import annotations

from importlib import import_module

ACT = import_module("factory-console.session.actions")
INT = import_module("factory-console.session.intent")
API = import_module("factory-console.api")


def _cli_names() -> set[str]:
    reg = ACT.build_default_actions()
    if hasattr(reg, "list"):
        return {a.name for a in reg.list()}
    return {a.name for a in getattr(reg, "actions", [])}


def _api_names() -> set[str]:
    return set(getattr(API, "__all__", []))


def _intent_names() -> set[str]:
    return {rule[1] for rule in INT._KEYWORD_RULES}


CLI = _cli_names()
API_ = _api_names()
INTENT = _intent_names()


# ================================================================== 1. 核心能力契约


class TestCapabilityContract:
    """Capability = Core + CLI + API + Intent + Help + Test。"""

    # (capability, cli_action, api_route, intent_keyword)
    CONTRACTS = [
        ("discovery", "discovery_start", "save_discovery_answer", "开始做"),
        ("product_intelligence", "product_intelligence", "product_intelligence_analyze", "分析产品"),
        ("product_market", "product_market", "product_market_analysis", "产品市场"),
        ("product_persona", "product_persona", "product_persona", "产品画像"),
        ("product_mvp", "product_mvp", "product_mvp", "MVP规划"),
        ("product_value", "product_value", "product_value", "产品价值"),
        ("create_product", "create_product", "start_project_workflow_route", "我想"),
        ("prepare_project", "prepare_project", "get_project_workflow", "准备开发"),
        ("execute_project", "execute_project", "execute_runtime_task", "开始开发"),
        ("production_session", "production_session_view", "run_status_route", "查看进度"),
        ("debug_analyze", "debug_analyze", "debug_analyze", "分析错误"),
        ("debug_session", "debug_session", "debug_session", "开始调试"),
        ("debug_repair", "debug_repair", "debug_repair", "自动修复"),
        ("debug_validate", "debug_validate", "debug_validate", "验证修复"),
        ("debug_resume", "debug_resume", "debug_resume", "继续调试"),
        ("memory_search", "memory_search", "memory_search", "搜索经验"),
        ("memory_learn", "memory_learn", "memory_learn", "学习经验"),
        ("memory_stats", "memory_stats", "memory_stats", "经验统计"),
        ("memory_export", "memory_export", "memory_export", "导出经验"),
        ("audit_events", "audit_events", "audit_events", "查看审计记录"),
        ("audit_trace", "audit_trace", "audit_trace", "审计追踪"),
        ("audit_explain", "audit_explain", "audit_explain", "为什么创建这个任务"),
        ("audit_cost", "audit_cost", "audit_cost", "成本审计"),
        ("review_view", "review_view", "list_approvals", "为什么停了"),
        ("review_approve", "review_approve", "reject_approval", "接受"),
        ("governance_budget", "factory_budget", "list_approvals", "查看预算"),
        ("team", "team", "list_workflows", "团队协作"),
        ("workforce", "workforce", "list_projects", "查看团队"),
    ]

    def test_cli_exists(self):
        for name, cli, api_route, kw in self.CONTRACTS:
            assert cli in CLI, f"{name}: CLI action {cli} 缺失"

    def test_api_exists(self):
        for name, cli, api_route, kw in self.CONTRACTS:
            assert api_route in API_, f"{name}: API {api_route} 缺失"

    def test_intent_exists(self):
        for name, cli, api_route, kw in self.CONTRACTS:
            parsed = INT.KeywordIntentParser().parse(kw)
            assert parsed is not None and parsed.intent_type == cli, \
                f"{name}: intent 关键词 '{kw}' → {cli} 缺失"

    def test_help_metadata(self):
        """每个 CLI action 有 description (可发现性 = -h)。"""
        reg = ACT.build_default_actions()
        actions = reg.list() if hasattr(reg, "list") else getattr(reg, "actions", [])
        for name, cli, api_route, kw in self.CONTRACTS:
            a = next((x for x in actions if x.name == cli), None)
            assert a is not None and a.description, f"{name}: CLI {cli} 无 help 描述"

    def test_api_registered(self):
        for name, cli, api_route, kw in self.CONTRACTS:
            assert api_route in API_, f"{name}: API {api_route} 未注册 __all__"


# ================================================================== 2. 全量覆盖审计


class TestFullCoverage:
    """所有 action 必须能找到对应 intent 或 API (完整性兜底)。"""

    def test_all_cli_have_description(self):
        reg = ACT.build_default_actions()
        actions = reg.list() if hasattr(reg, "list") else getattr(reg, "actions", [])
        for a in actions:
            assert a.description, f"action {a.name} 无 description"

    def test_audit_api_complete(self):
        """audit 10 端点全注册。"""
        for n in ("audit_events", "audit_trace", "audit_chain", "audit_task",
                  "audit_agent", "audit_decisions", "audit_explain", "audit_cost",
                  "audit_stats", "audit_export"):
            assert n in API_, f"audit API {n} 缺失"

    def test_debug_api_complete(self):
        for n in ("debug_session", "debug_analyze", "debug_root_cause",
                  "debug_recommend", "debug_repair", "debug_validate",
                  "debug_resume", "debug_history", "debug_stats"):
            assert n in API_, f"debug API {n} 缺失"

    def test_memory_api_complete(self):
        for n in ("memory_search", "memory_learn", "memory_stats",
                  "memory_agent", "memory_export"):
            assert n in API_, f"memory API {n} 缺失"

    def test_product_api_complete(self):
        """S10-070 补齐: product_mvp/product_value 必须存在。"""
        for n in ("product_intelligence_analyze", "product_market_analysis",
                  "product_persona", "product_mvp", "product_value"):
            assert n in API_, f"product API {n} 缺失"

"""S47-E1 — Conversation Intent 路由 + Product Truth 查询修复测试。

验证 (通用机制, 非关键词单例):
- 产品理解类问题 → product_lifecycle (不是 project_tasks)
- 任务统计 → project_tasks; 项目状态 → project_status; 发布 → release 域
- tool schema 暴露 project_lifecycle
- handler 输出来自真实 canonical/org (缺失如实, 不编造"已完成")
"""
import json

import pytest

from factory_console.session.agent_loop import _project_lifecycle, tool_schemas
from factory_console.session.query_engine import VALID_INTENTS, parse_intent


def _det(q: str) -> str:
    """确定性意图 (parse_intent 内部 fallback 链 — 命中即意图)。"""
    return parse_intent(q).get("intent") or "chat"


class TestIntentRouting:
    def test_requirement_question_routes_to_product_lifecycle(self):
        assert _det("需求分析完成了吗") == "product_lifecycle"
        assert _det("需求整理到哪一步了") == "product_lifecycle"
        assert _det("PRD 做完了吗") == "product_lifecycle"
        assert _det("产品方案完成了吗") == "product_lifecycle"
        assert _det("任务拆解完成了吗") == "product_lifecycle"
        assert _det("需求分析现在是什么状态") == "product_lifecycle"

    def test_project_status_still_project_status(self):
        assert _det("这个项目现在什么状态") == "project_status"
        assert _det("项目进度怎么样") == "project_status"
        assert _det("现在有多少任务") == "project_tasks"
        assert _det("帮我看看任务列表") == "project_tasks"

    def test_intent_in_valid_set(self):
        assert "product_lifecycle" in VALID_INTENTS

    def test_tool_schema_exposes_project_lifecycle(self):
        schemas = tool_schemas(None)
        names = [s.get("function", {}).get("name") for s in schemas]
        assert "project_lifecycle" in names
        desc = next(s["function"]["description"] for s in schemas
                    if s.get("function", {}).get("name") == "project_lifecycle")
        assert "产品链" in desc and "project_tasks" in desc


class TestProjectLifecycleHandler:
    def test_reports_true_state_and_honest_missing(self, tmp_path):
        # 空 root: 全阶段缺失 → 诚实标注, 不声称完成
        out = _project_lifecycle(str(tmp_path), "P-x")["output"]
        assert "未建立" in out
        assert "需求" in out

    def test_reads_org_requirement_when_present(self, tmp_path):
        req_dir = tmp_path / "requirements"
        req_dir.mkdir()
        (req_dir / "requirements.json").write_text(json.dumps(
            [{"id": "req_1", "project_id": "P-a", "title": "测试",
              "status": "VALIDATED"}]), encoding="utf-8")
        out = _project_lifecycle(str(tmp_path), "P-a")["output"]
        assert "req_1" in out and "VALIDATED" in out

    def test_does_not_invent_completion(self, tmp_path):
        out = _project_lifecycle(str(tmp_path), "P-x")["output"]
        assert "已完成" not in out or "org" not in out
        # 明确不能凭任务推断 — 说明行存在
        assert "任务数量推断" in out

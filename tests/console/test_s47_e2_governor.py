"""S47-E2 — Semantic Governor 测试 (LLM mock 返回真实形状; 零关键词行为)。

验证:
- 语义类别 (complaint/correction/confirm/continue/decline/question/opinion)
  → 对应引导 (recovery 禁诊断工具 / 执行提议 / 域工具 / 无工具克制)
- 域判定 → 域工具提示 (product_lifecycle 不用 project_tasks)
- no-tool (opinion) → 工具克制引导
- governor 失败 → 保守默认 (不引导诊断)
- state 持久化 (load/save)
"""
import pytest

from factory_console.session.agent_loop import (
    _conv_state_load, _conv_state_save, _govern_turn, _governance_guide,
)

H = [
    {"role": "user", "content": "需求分析完了吗？"},
    {"role": "assistant", "content": "需求分析未完成。我可以继续帮你分析，需要吗？"},
]


def _llm(rel: str, domain: str = "product_lifecycle", needs_tool: bool = True,
         topic: str = "需求分析"):
    def llm(prompt: str) -> str:
        return (f'{{"relation": "{rel}", "domain": "{domain}", '
                f'"needs_tool": {str(needs_tool).lower()}, "topic": "{topic}"}}')
    return llm


class TestGovern:
    def test_complaint_recovery(self):
        g = _govern_turn("你刚才回答的不对", {}, H, _llm("complaint", "conversation", False))
        guide = _governance_guide(g["relation"], g["domain"], g["needs_tool"], {}, "你刚才回答的不对")
        assert g["relation"] == "complaint"
        assert "不要调用项目诊断工具" in guide
        assert "project_status" in guide  # 显式禁止

    def test_correction_recovery(self):
        g = _govern_turn("不是这个意思，我说的是登录需求", {}, H, _llm("correction", "product_lifecycle", False))
        guide = _governance_guide(g["relation"], g["domain"], g["needs_tool"], {}, "x")
        assert "修正上一轮回答" in guide

    def test_confirm_with_state(self):
        st = {"topic": "需求分析", "pending": "启动需求分析流程",
              "domain": "product_lifecycle"}
        g = _govern_turn("接受建议", st, H, _llm("confirm", "product_lifecycle", True))
        guide = _governance_guide(g["relation"], g["domain"], g["needs_tool"], st, "接受建议")
        assert "执行该提议" in guide and "启动需求分析流程" in guide

    def test_continue_keeps_topic(self):
        st = {"topic": "需求分析", "domain": "product_lifecycle"}
        g = _govern_turn("继续分析需求", st, H, _llm("continue", "product_lifecycle", True))
        guide = _governance_guide(g["relation"], g["domain"], g["needs_tool"], st, "继续分析需求")
        assert "保持主题" in guide and "需求分析" in guide

    def test_decline(self):
        g = _govern_turn("不用了", {}, H, _llm("decline", "conversation", False))
        guide = _governance_guide(g["relation"], g["domain"], g["needs_tool"], {}, "不用了")
        assert "不执行" in guide

    def test_question_domain_product_lifecycle(self):
        g = _govern_turn("需求分析完了吗？", {}, [], _llm("question", "product_lifecycle", True))
        guide = _governance_guide(g["relation"], g["domain"], g["needs_tool"], {}, "需求分析完了吗？")
        assert "project_lifecycle" in guide and "勿用 project_tasks" in guide

    def test_question_domain_task_allows_project_tasks(self):
        g = _govern_turn("现在有多少任务？", {}, [], _llm("question", "task", True))
        guide = _governance_guide(g["relation"], g["domain"], g["needs_tool"], {}, "现在有多少任务？")
        assert "域 = task" in guide and "不用" not in guide

    def test_opinion_no_tool(self):
        g = _govern_turn("这个需求是不是太复杂了？", {}, [], _llm("opinion", "general", False))
        guide = _governance_guide(g["relation"], g["domain"], g["needs_tool"], {}, "x")
        assert "无需调用工具" in guide and "工具克制" in guide

    def test_govern_failure_conservative(self):
        def bad_llm(prompt: str) -> str:
            raise RuntimeError("boom")
        g = _govern_turn("需求分析完了吗？", {}, [], bad_llm)
        assert g["relation"] == "unknown" and g["needs_tool"] is False

    def test_state_roundtrip(self, tmp_path):
        _conv_state_save(str(tmp_path), "sess-1",
                         {"topic": "需求分析", "domain": "product_lifecycle", "relation": "confirm"})
        st = _conv_state_load(str(tmp_path), "sess-1")
        assert st["topic"] == "需求分析" and st["domain"] == "product_lifecycle"

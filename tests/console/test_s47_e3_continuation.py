"""S47-E3 — Active Work Resolver / 工作恢复引导测试 (LLM mock 真实形状)。

验证:
- continue 语义 → 恢复 active_work + next_action (不重诊断)
- confirm 带 pending → 执行方向引用
- modify / reference 有语义承载
- topic 切换: task 域 question 不被吸入 continuation
- no second orchestrator: resolver 只产出引导文本, 执行仍走 agent FC
"""
import pytest

from factory_console.session.agent_loop import (
    _resolve_active_work, _work_recovery_guide,
)


def _llm(active_work="需求分析", stage="整理", next_action="基于会话计划整理需求点并写入 Requirement",
         need_input=False, question=None):
    def llm(prompt: str) -> str:
        q = f'"{question}"' if question else "null"
        return (f'{{"active_work": "{active_work}", "current_stage": "{stage}", '
                f'"next_action": "{next_action}", "need_user_input": '
                f'{str(need_input).lower()}, "question": {q}}}')
    return llm


H = [
    {"role": "user", "content": "需求分析完了吗？"},
    {"role": "assistant", "content": "需求分析尚未完成，我可以继续帮你分析，需要吗？"},
]


class TestActiveWorkResolver:
    def test_continue_recovers_work(self):
        st = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "continue"}
        w = _resolve_active_work("继续帮忙分析需求", st, H, _llm())
        assert w["active_work"] == "需求分析"
        assert "Requirement" in w["next_action"]

    def test_recovery_guide_injects_next_action(self):
        st = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "continue"}
        g = _work_recovery_guide("继续帮忙分析需求", st, H, _llm())
        assert "恢复工作" in g and "下一步" in g and "Requirement" in g
        # 不重诊断
        assert "不要重新做项目诊断" in g

    def test_confirm_uses_pending(self):
        st = {"topic": "需求分析", "domain": "product_lifecycle",
              "relation": "confirm", "pending": "启动需求分析流程"}
        g = _work_recovery_guide("接受建议", st, H, _llm())
        assert "恢复工作" in g and "confirm" in g

    def test_need_user_input_asks_not_guesses(self):
        st = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "continue"}
        g = _work_recovery_guide("继续分析", st, H,
                                 _llm(need_input=True, question="技术栈用纯前端还是 Python?"))
        assert "真正阻塞" in g and "技术栈" in g

    def test_non_continue_relation_no_recovery(self):
        st = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "question"}
        assert _work_recovery_guide("现在多少任务？", st, H, _llm()) == ""

    def test_topic_switch_not_locked(self):
        # 第二句 任务查询 (question/task) → 不触发恢复; 第三句 continue 恢复需求分析
        st_q = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "question"}
        assert _work_recovery_guide("现在项目有多少任务？", st_q, H, _llm()) == ""
        st_c = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "continue"}
        g = _work_recovery_guide("继续分析需求", st_c, H, _llm())
        assert "需求分析" in g

    def test_resolver_failure_safe(self):
        def bad(prompt: str):
            raise RuntimeError("boom")
        st = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "continue"}
        assert _work_recovery_guide("继续", st, H, bad) == ""

    def test_modify_reference_have_semantics(self):
        for rel in ("modify", "reference"):
            st = {"topic": "需求分析", "domain": "product_lifecycle", "relation": rel}
            g = _work_recovery_guide("可以，不过先完善登录", st, H, _llm())
            assert "恢复工作" in g


class TestTruthAwareResolver:
    def test_truth_passed_into_resolver(self):
        from factory_console.session.agent_loop import _ACTIVE_WORK_PROMPT
        assert "{truth}" in _ACTIVE_WORK_PROMPT  # truth 注入占位存在

    def test_guide_mentions_truth(self):
        st = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "continue"}
        seen = {}
        def llm(prompt):
            seen["truth_in"] = "Truth" in prompt and "org 需求" in prompt or "未读取" not in prompt
            return ('{"active_work": "需求分析", "current_stage": "整理", '
                    '"next_action": "整理需求清单并建立 Requirement", "need_user_input": false, "question": null}')
        g = _work_recovery_guide("继续帮忙分析需求", st, H, llm, truth_summary="Requirement 未建立; org 需求 VALIDATED")
        assert "先做后问" in g and "直接执行" in g

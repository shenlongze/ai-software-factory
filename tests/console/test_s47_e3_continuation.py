"""S47-E3 / E3.1 / E3.2 — Active Work Resolver / 工作恢复引导测试。

覆盖: continue 恢复 / 先做后问 / need_user_input 受控 / 跨轮状态持久化 /
topic 切换 / 失败安全 / truth-aware / modify·reference。
"""
import pytest

from factory_console.session.agent_loop import (
    _ACTIVE_WORK_PROMPT,
    _conv_state_load,
    _conv_state_save,
    _resolve_active_work,
    _work_recovery_guide,
)

H = [
    {"role": "user", "content": "需求分析完了吗？"},
    {"role": "assistant", "content": "需求分析尚未完成，我可以继续帮你分析，需要吗？"},
]


def _llm(active_work="需求分析", stage="整理",
         next_action="基于会话计划整理需求点并写入 Requirement",
         need_input=False, question=None):
    def llm(prompt: str) -> str:
        q = f'"{question}"' if question else "null"
        return (f'{{"active_work": "{active_work}", "current_stage": "{stage}", '
                f'"next_action": "{next_action}", "need_user_input": '
                f'{str(need_input).lower()}, "question": {q}}}')
    return llm


class TestActiveWorkResolver:
    def test_continue_recovers_work(self):
        st = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "continue"}
        w = _resolve_active_work("继续帮忙分析需求", st, H, _llm())
        assert w["active_work"] == "需求分析"
        assert "Requirement" in w["next_action"]

    def test_execution_guide_and_state(self):
        st = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "continue"}
        g, aw = _work_recovery_guide("继续帮忙分析需求", st, H, _llm(need_input=False))
        assert "本轮执行指令" in g and "禁止" in g and "save_product_record" in g
        assert aw["next_action"] and aw["need_user_input"] is False and aw["blocked"] is False

    def test_need_user_input_blocks_ask(self):
        # need_user_input=False → 执行引导, 不进入 ask 路径
        g, aw = _work_recovery_guide("继续", st(), H, _llm(need_input=False))
        assert "等待关键信息" not in g and aw["blocked"] is False

    def test_need_user_input_allows_minimal_ask(self):
        st = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "continue"}
        g, aw = _work_recovery_guide("继续分析", st, H,
                                     _llm(need_input=True, question="技术栈用纯前端还是 Python?"))
        assert "等待关键信息" in g and "技术栈" in g and aw["blocked"] is True

    def test_confirm_uses_pending(self):
        st = {"topic": "需求分析", "domain": "product_lifecycle",
              "relation": "confirm", "pending": "启动需求分析流程"}
        g, aw = _work_recovery_guide("接受建议", st, H, _llm(need_input=False))
        assert "本轮执行指令" in g and "confirm" in g

    def test_non_continue_relation_no_recovery(self):
        st = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "question"}
        g, aw = _work_recovery_guide("现在多少任务？", st, H, _llm())
        assert g == "" and aw == {}

    def test_topic_switch_not_locked(self):
        st_q = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "question"}
        assert _work_recovery_guide("现在项目有多少任务？", st_q, H, _llm())[0] == ""
        st_c = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "continue"}
        g, _ = _work_recovery_guide("继续分析需求", st_c, H, _llm())
        assert "需求分析" in g

    def test_resolver_failure_safe(self):
        def bad(prompt: str):
            raise RuntimeError("boom")
        st = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "continue"}
        assert _work_recovery_guide("继续", st, H, bad) == ("", {})

    def test_modify_reference_have_semantics(self):
        for rel in ("modify", "reference"):
            st = {"topic": "需求分析", "domain": "product_lifecycle", "relation": rel}
            g, _ = _work_recovery_guide("可以，不过先完善登录", st, H, _llm())
            assert "本轮执行指令" in g


def st(**kw):
    d = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "continue"}
    d.update(kw)
    return d


class TestStatePersistence:
    def test_active_work_persists_across_turns(self, tmp_path):
        _conv_state_save(str(tmp_path), "sess-1", {
            "topic": "需求分析", "domain": "product_lifecycle", "relation": "continue",
            "active_work": "需求分析", "next_action": "整理需求清单",
            "current_stage": "整理", "need_user_input": False,
        })
        st2 = _conv_state_load(str(tmp_path), "sess-1")
        assert st2["active_work"] == "需求分析"
        assert st2["next_action"] == "整理需求清单"  # 跨轮继承锚定

    def test_prompt_has_work_anchor(self):
        assert "{work}" in _ACTIVE_WORK_PROMPT and "{prev_next}" in _ACTIVE_WORK_PROMPT


class TestTruthAwareResolver:
    def test_truth_passed_into_resolver(self):
        assert "{truth}" in _ACTIVE_WORK_PROMPT

    def test_truth_anchor_used(self):
        st = {"topic": "需求分析", "domain": "product_lifecycle", "relation": "continue"}
        seen = {}

        def llm(prompt):
            seen["truth"] = "org 需求" in prompt
            return ('{"active_work": "需求分析", "current_stage": "整理", '
                    '"next_action": "整理需求清单并建立 Requirement", '
                    '"need_user_input": false, "question": null}')
        g, aw = _work_recovery_guide("继续帮忙分析需求", st, H, llm,
                                     truth_summary="Requirement 未建立; org 需求 VALIDATED")
        assert seen["truth"] and aw["next_action"]

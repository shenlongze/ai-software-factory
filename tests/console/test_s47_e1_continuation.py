"""S47-E1 (cont) — Conversation Continuation 通用语义测试。

验证 (零硬编码, 语言层通用):
- AI 提议 → 用户 需要/好 → 产生确认引导 (非空 + tone=确认执行)
- AI 提议 → 用户 不需要 → 拒绝引导 (不执行)
- 无 AI 提议 (首轮) → 空 (不打扰)
- 非短确认普通消息 → 空
- 上一轮 assistant 不含提议问句 → 空
- routing 保持 (product_lifecycle 回归)
"""
from factory_console.session.agent_loop import _continuation_guide
from factory_console.session.query_engine import parse_intent

H = [
    {"role": "user", "content": "飞机大战现在做到哪了？"},
    {"role": "assistant", "content": "我可以继续帮你做需求分析，需要吗？"},
]


class TestContinuationGuide:
    def test_confirm_need(self):
        g = _continuation_guide("需要", H)
        assert g and "确认并执行上一轮提议" in g
        assert "不完整" in g  # 防呆: 禁止说消息不完整

    def test_confirm_hao(self):
        g = _continuation_guide("好", H)
        assert g and "确认并执行上一轮提议" in g

    def test_reject(self):
        g = _continuation_guide("不需要", H)
        assert g and "拒绝上一轮提议" in g

    def test_no_history_empty(self):
        assert _continuation_guide("需要", []) == ""

    def test_no_proposal_no_guide(self):
        h2 = [{"role": "user", "content": "你好"},
              {"role": "assistant", "content": "你好！有什么可以帮你？"}]
        assert _continuation_guide("需要", h2) == ""  # 无提议问句

    def test_first_turn_normal(self):
        assert _continuation_guide("帮我看看飞机大战", []) == ""

    def test_non_short_message_not_forced(self):
        # 普通长消息不触发 (确认词但非短确认)
        assert _continuation_guide("需要你帮我查一下项目状态和任务", H) == ""


class TestRoutingRegression:
    def test_product_lifecycle_still_routes(self):
        assert parse_intent("需求分析完了吗").get("intent") == "product_lifecycle"
        assert parse_intent("现在有多少任务").get("intent") == "project_tasks"
        assert parse_intent("项目现在什么状态").get("intent") == "project_status"

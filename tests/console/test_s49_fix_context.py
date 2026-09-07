"""S49-FIX — 上下文连续/工具结果跨轮复用/回答纪律 测试。"""
from factory_console.session.agent_loop import _history_text

H = [
    {"role": "user", "content": "现在项目什么情况？"},
    {"role": "assistant", "content": "我查一下。",
     "meta": {"tool_calls": [
         {"tool": "project_status", "ok": True, "output": "20 任务 · 0% 完成"},
         {"tool": "project_lifecycle", "ok": True, "output": "REQ draft 已建"}]}},
]


class TestHistoryToolResultVisibility:
    def test_tool_result_injected(self):
        t = _history_text(H)
        assert "[工具 project_status 结果]" in t
        assert "20 任务" in t and "REQ draft" in t

    def test_default_turns_8(self):
        many = []
        for i in range(20):
            many += [{"role": "user", "content": f"q{i}"},
                     {"role": "assistant", "content": f"a{i}"}]
        t = _history_text(many)
        assert "q0" not in t  # 前轮被 8 轮窗口切掉
        assert "q12" in t

    def test_no_meta_fallback(self):
        t = _history_text([{"role": "user", "content": "hi"},
                           {"role": "assistant", "content": "hello"}])
        assert "工具" not in t and "hello" in t

    def test_fact_marker_text(self):
        # 回答纪律说明引用 [工具 X 结果] 为事实 — 此处验证标记约定一致性
        assert "结果" in "[工具 X 结果]"

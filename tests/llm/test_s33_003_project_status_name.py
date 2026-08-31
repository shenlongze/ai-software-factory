"""S34-001: project_status 项目名解析 — org/projects.json SSOT。"""

import json
from pathlib import Path

from factory_console.session.observability import project_status


def _make_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "factory"
    (ws / "projects" / "P-abc").mkdir(parents=True)
    (ws / "projects" / "P-abc" / "project.json").write_text(
        json.dumps({"name": "P-abc", "status": "idea"}), encoding="utf-8"
    )
    (ws / "org").mkdir()
    (ws / "org" / "projects.json").write_text(
        json.dumps({"projects": {"P-abc": {"id": "P-abc", "name": "旅行记账"}}}),
        encoding="utf-8",
    )
    return ws


def test_project_status_uses_org_name(tmp_path: Path) -> None:
    ws = _make_workspace(tmp_path)
    st = project_status(ws, ws / "projects" / "P-abc")
    # project.json name 是 ID 占位 → org 覆盖为真实名称
    assert st.get("project") == "旅行记账"
    assert st.get("lifecycle") == "idea"


def test_project_status_org_missing_falls_back(tmp_path: Path) -> None:
    ws = tmp_path / "factory"
    (ws / "projects" / "P-def").mkdir(parents=True)
    (ws / "projects" / "P-def" / "project.json").write_text(
        json.dumps({"name": "P-def", "status": "idea"}), encoding="utf-8"
    )
    # 无 org/projects.json → 不崩溃, 用目录名兜底
    st = project_status(ws, ws / "projects" / "P-def")
    assert st.get("project") == "P-def"


# ---- S34-002: assistant_meta.run_ids 归属 (消息→Run 关联) ----

def test_assistant_meta_run_ids_binding(tmp_path: Path) -> None:
    """send_message assistant_meta 应携带 run_ids 且持久化 (GET 返回)。"""
    from factory_console.console_sessions import SessionStore, send_message

    store = SessionStore(tmp_path / "console_sessions.json")
    s = store.create_session(scope="company", title="S34-002")
    sid = s["id"]

    def _fake_llm(_prompt: str) -> str:
        return "开始执行，已创建 Run。"

    result = send_message(
        store, sid, "开始执行",
        llm_fn=_fake_llm,
        assistant_meta={
            "tool_calls": [{"tool": "start_workflow", "ok": True}],
            "run_ids": ["R-S34-002"],
        },
    )
    # assistant 消息 meta 持久化 run_ids
    assert result["assistant"]["meta"]["run_ids"] == ["R-S34-002"]
    # GET messages 返回同一 meta (刷新后归属不丢)
    msgs = store.list_messages(sid)
    asst = [m for m in msgs if m.get("role") == "assistant"][0]
    assert asst["meta"]["run_ids"] == ["R-S34-002"]


# ---- S34-003B: Tool Protocol 泄漏清洗 ----

def test_strip_fake_toolcalls_removes_protocol() -> None:
    """内部 Tool Protocol (<tool_calls>/<invoke>/<parameter>) 绝不进入用户正文。"""
    from factory_console.session.agent_loop import _strip_fake_toolcalls

    leaky = (
        "我已经定位到了核心逻辑文件。\n\n"
        "<tool_calls>\n<invoke name=\"read_file\">\n"
        "<parameter name=\"file_path\">/Users/x/agent_loop.py</parameter>\n"
        "</invoke>\n</tool_calls>"
    )
    cleaned = _strip_fake_toolcalls(leaky)
    assert "<tool_calls>" not in cleaned
    assert "<invoke" not in cleaned
    assert "<parameter" not in cleaned
    # 自然语言保留
    assert "我已经定位到了核心逻辑文件" in cleaned


def test_strip_fake_toolcalls_keeps_normal_text() -> None:
    """正常文本不受影响 (粗体/列表保留)。"""
    from factory_console.session.agent_loop import _strip_fake_toolcalls

    normal = "正常回答。**粗体** 和列表:\n- 项目 A\n- 项目 B"
    cleaned = _strip_fake_toolcalls(normal)
    assert cleaned == normal


def test_strip_fake_toolcalls_unpaired_tags() -> None:
    """散标签/未配对也清理。"""
    from factory_console.session.agent_loop import _strip_fake_toolcalls

    unpaired = "回答。</tool_calls><invoke name=\"bash_exec\">"
    cleaned = _strip_fake_toolcalls(unpaired)
    assert "<tool_calls>" not in cleaned
    assert "<invoke" not in cleaned


# ---- S34-003B: cost 估算 (usage.estimated_cost_usd) ----

def test_model_prices_deepseek() -> None:
    """deepseek 价格表匹配 (chat 档 0.27/1.10)。"""
    from factory_console.session.llm_gateway import _model_prices

    assert _model_prices("deepseek-chat") == (0.27, 1.10)
    assert _model_prices("deepseek-v4-flash") == (0.27, 1.10)
    assert _model_prices("unknown-model") == (0.0, 0.0)


def test_complete_usage_cost_estimated() -> None:
    """complete 返回 usage 带 estimated_cost_usd (真实价格估算)。"""
    from unittest.mock import patch

    import factory_console.session.llm_gateway as lg

    with patch.object(lg, "_openai_compat_complete", return_value={
        "content": "ok",
        "usage": {"prompt_tokens": 1000, "completion_tokens": 1000},
    }):
        out = lg.complete([], None, provider_id="deepseek", model="deepseek-chat",
                          base_url="", api_key="x")
    u = out["usage"]
    # 1000/1M * 0.27 + 1000/1M * 1.10 = 0.00137
    assert abs(u["estimated_cost_usd"] - 0.00137) < 1e-6


# ---- S34-003B: 模型上下文窗口 ----

def test_model_context_window_known() -> None:
    """deepseek-chat → 64K; v4-flash → 1M; 未知 → 0。"""
    from factory_console.session.llm_gateway import model_context_window

    assert model_context_window("deepseek-chat") == 65536
    assert model_context_window("deepseek-v4-flash") == 1048576
    assert model_context_window("unknown-model") == 0


def test_agent_loop_usage_context_fallback() -> None:
    """usage.context_window 为 0 时兜底到模型表 (deepseek-chat → 64K)。"""
    from factory_console.session.llm_gateway import model_context_window

    _mconf = {"model": "deepseek-chat", "context_window": 0}
    cw = int(_mconf.get("context_window") or 0) or model_context_window(str(_mconf.get("model") or ""))
    assert cw == 65536


# ---- P0 回归: DSML 全角变体泄漏 ----

def test_strip_fake_toolcalls_dsml_fullwidth() -> None:
    """模型输出全角 DSML 变体 <｜DSML｜tool_calls> / <||DSML||invoke> → 全清除。"""
    from factory_console.session.agent_loop import _strip_fake_toolcalls

    leaky = (
        "<｜DSML｜tool_calls>\n"
        "<｜DSML｜invoke name=\"bash_exec\">\n"
        "<｜DSML｜parameter name=\"command\">for d in /projects/*/; do ls; done</｜DSML｜parameter>\n"
        "<｜DSML｜/invoke>\n"
        "<｜DSML｜/tool_calls>"
    )
    cleaned = _strip_fake_toolcalls(leaky)
    assert cleaned.strip() == ""
    for bad in ("DSML", "tool_calls", "<invoke", "<parameter"):
        assert bad not in cleaned


def test_strip_fake_toolcalls_dsml_double_pipe() -> None:
    """双竖线变体 <||DSML||tool_calls> → 清除。"""
    from factory_console.session.agent_loop import _strip_fake_toolcalls

    leaky = "回答。<||DSML||tool_calls>\n<||DSML||invoke name=\"bash_exec\">\n</||DSML||invoke>\n<||DSML||/tool_calls>"
    cleaned = _strip_fake_toolcalls(leaky)
    assert "DSML" not in cleaned
    assert "回答" in cleaned


def test_strip_fake_toolcalls_keeps_normal_after_dsml() -> None:
    """DSML 块清除后自然语言保留。"""
    from factory_console.session.agent_loop import _strip_fake_toolcalls

    text = "目前共有 2 个项目。\n\n<||DSML||tool_calls>\n<||DSML||invoke name=\"bash_exec\">\n</||DSML||invoke>\n<||DSML||/tool_calls>"
    cleaned = _strip_fake_toolcalls(text)
    assert "目前共有 2 个项目" in cleaned
    assert "DSML" not in cleaned

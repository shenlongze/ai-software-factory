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

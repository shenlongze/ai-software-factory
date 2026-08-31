"""S30-003 — Session ↔ Run 一级关联测试 (真实 SessionStore, 零 Mock)。"""

import json
from pathlib import Path

from factory_console.console_sessions import SessionStore


def _store(tmp_path: Path) -> SessionStore:
    return SessionStore(str(tmp_path / "console_sessions.json"))


# ---- Test A: 创建 Session → add_run → 关联真实 Run ID ----

def test_a_session_run_association(tmp_path: Path) -> None:
    store = _store(tmp_path)
    s = store.create_session(scope="company", title="S30-003 TestA")
    sid = s["id"]
    # 初始无 run
    assert store.session_runs(sid) == []
    # Run 创建后关联 (真实 run_id 格式: R + 时间戳)
    run_id = "R1787000000000-APP"
    ok = store.add_run(sid, run_id)
    assert ok is True
    assert store.session_runs(sid) == [run_id]
    # get_session 返回 run_ids
    assert store.get_session(sid)["run_ids"] == [run_id]


# ---- Test B: 同 Session 多次执行 → 1:N cardinality ----

def test_b_session_multiple_runs(tmp_path: Path) -> None:
    store = _store(tmp_path)
    s = store.create_session(scope="company", title="S30-003 TestB")
    sid = s["id"]
    store.add_run(sid, "R1-APP")
    store.add_run(sid, "R2-APP")
    store.add_run(sid, "R3-APP")
    assert store.session_runs(sid) == ["R1-APP", "R2-APP", "R3-APP"]
    # 幂等: 重复添加不重复
    store.add_run(sid, "R2-APP")
    assert store.session_runs(sid) == ["R1-APP", "R2-APP", "R3-APP"]


# ---- Test C: Recovery — 重载 store 后关联仍在 (持久化) ----

def test_c_recovery_persisted(tmp_path: Path) -> None:
    path = tmp_path / "console_sessions.json"
    store = SessionStore(str(path))
    s = store.create_session(scope="company", title="S30-003 TestC")
    sid = s["id"]
    store.add_run(sid, "R-RECOVER-1")
    # 模拟重启: 新实例加载同一文件
    store2 = SessionStore(str(path))
    assert store2.session_runs(sid) == ["R-RECOVER-1"]
    assert store2.get_session(sid)["run_ids"] == ["R-RECOVER-1"]


# ---- Test D: Browser refresh — API 层可见 run_ids (模拟 GET) ----

def test_d_refresh_sees_runs(tmp_path: Path) -> None:
    store = _store(tmp_path)
    s = store.create_session(scope="company", title="S30-003 TestD")
    sid = s["id"]
    store.add_run(sid, "R-REFRESH-1")
    # 刷新 = 重新 GET (list_sessions / get_session)
    listed = [x for x in store.list_sessions() if x["id"] == sid][0]
    assert listed["run_ids"] == ["R-REFRESH-1"]
    assert store.get_session(sid)["run_ids"] == ["R-REFRESH-1"]


# ---- Test E: 历史 Session (无 run_ids 字段) 向后兼容 ----

def test_e_legacy_session_compat(tmp_path: Path) -> None:
    path = tmp_path / "console_sessions.json"
    # 手工构造历史数据: 无 run_ids 字段
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "sessions": {
            "sess-legacy-1": {
                "id": "sess-legacy-1", "scope": "company", "project_id": None,
                "title": "历史会话", "status": "active",
                "created_at": "2026-08-01T00:00:00+00:00",
                "updated_at": "2026-08-01T00:00:00+00:00", "summary": None,
            }
        },
        "messages": {},
    }), encoding="utf-8")
    store = SessionStore(str(path))
    s = store.get_session("sess-legacy-1")
    assert s is not None
    assert s["run_ids"] == []  # 补空, 不崩
    assert store.session_runs("sess-legacy-1") == []  # 查询不崩
    # add_run 到历史 session 仍工作 (写回 run_ids)
    assert store.add_run("sess-legacy-1", "R-LEGACY-1") is True
    assert store.session_runs("sess-legacy-1") == ["R-LEGACY-1"]


# ---- S30-004 P0-2: Session → Run 端点数据契约 ----

def test_session_runs_endpoint_contract(tmp_path: Path) -> None:
    """SessionStore.session_runs 返回 run_ids; get_session 含 run_ids (API 契约层)。"""
    store = _store(tmp_path)
    s = store.create_session(scope="company", title="S30-004 端点契约")
    sid = s["id"]
    store.add_run(sid, "R-API-1")
    store.add_run(sid, "R-API-2")
    # API 层契约: get_session.run_ids + session_runs
    assert store.get_session(sid)["run_ids"] == ["R-API-1", "R-API-2"]
    assert store.session_runs(sid) == ["R-API-1", "R-API-2"]
    # 列表 API 含 run_ids
    listed = [x for x in store.list_sessions() if x["id"] == sid][0]
    assert listed["run_ids"] == ["R-API-1", "R-API-2"]

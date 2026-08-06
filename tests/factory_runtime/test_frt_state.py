"""tests/factory_runtime/test_frt_state.py — RuntimeState 持久化 (原子写/round-trip/损坏兜底)。

重点: 状态文件 round-trip / 原子写 (无 tmp 残留) / 损坏失败安全 / 权限 600。
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest


def test_defaults(rt_pkg):
    st = rt_pkg.state.RuntimeState()
    assert st.status == "idle"
    assert st.pid is None
    assert st.port is None
    assert st.version == ""
    assert st.started_at is None
    assert st.stopped_at is None


def test_to_dict_keys(rt_pkg):
    st = rt_pkg.state.RuntimeState()
    assert set(st.to_dict().keys()) == {
        "pid",
        "port",
        "status",
        "version",
        "started_at",
        "stopped_at",
    }


def test_save_load_round_trip(rt_pkg, frt_root):
    st = rt_pkg.state.RuntimeState(
        pid=1234,
        port=8011,
        status="ready",
        version="0.1.0",
        started_at="2026-08-07T00:00:00Z",
    )
    rt_pkg.state.save_state(st, frt_root)
    loaded = rt_pkg.state.load_state(frt_root)
    assert loaded.to_dict() == st.to_dict()


def test_save_creates_config_dir(rt_pkg, frt_root):
    path = rt_pkg.state.save_state(rt_pkg.state.RuntimeState(), frt_root)
    assert path.parent.is_dir()
    assert path.name == "runtime_state.json"


def test_state_path_location(rt_pkg, frt_root):
    path = rt_pkg.state.state_path(frt_root)
    assert path == frt_root / "config" / "runtime_state.json"


def test_load_missing_file_defaults(rt_pkg, frt_root):
    st = rt_pkg.state.load_state(frt_root)
    assert st.status == "idle"
    assert st.to_dict() == rt_pkg.state.RuntimeState().to_dict()


def test_load_corrupt_json_defaults(rt_pkg, frt_root):
    path = frt_root / "config" / "runtime_state.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json!!")
    st = rt_pkg.state.load_state(frt_root)
    assert st.status == "idle"


def test_load_wrong_type_defaults(rt_pkg, frt_root):
    path = frt_root / "config" / "runtime_state.json"
    path.parent.mkdir(parents=True)
    path.write_text("[1, 2, 3]")
    st = rt_pkg.state.load_state(frt_root)
    assert st.status == "idle"


def test_load_unknown_status_falls_back_idle(rt_pkg, frt_root):
    path = frt_root / "config" / "runtime_state.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"status": "bogus", "pid": 1}))
    st = rt_pkg.state.load_state(frt_root)
    assert st.status == "idle"
    assert st.pid == 1  # 其余字段保留


def test_statuses_valid(rt_pkg):
    assert rt_pkg.state.STATUSES == (
        "idle",
        "starting",
        "ready",
        "stopping",
        "stopped",
        "failed",
    )


def test_running_statuses(rt_pkg):
    assert rt_pkg.state.RUNNING_STATUSES == ("starting", "ready")


def test_atomic_write_no_tmp_leftover(rt_pkg, frt_root):
    rt_pkg.state.save_state(rt_pkg.state.RuntimeState(status="ready"), frt_root)
    leftovers = [
        p
        for p in (frt_root / "config").iterdir()
        if p.name.startswith(".runtime_state.json.")
    ]
    assert leftovers == []


def test_state_file_perm_600(rt_pkg, frt_root):
    if os.name != "posix":
        pytest.skip("POSIX only")
    path = rt_pkg.state.save_state(rt_pkg.state.RuntimeState(), frt_root)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_set_fields(rt_pkg):
    st = rt_pkg.state.RuntimeState()
    st.status = "ready"
    st.port = 9999
    st.version = "1.2.3"
    d = st.to_dict()
    assert d["status"] == "ready"
    assert d["port"] == 9999
    assert d["version"] == "1.2.3"

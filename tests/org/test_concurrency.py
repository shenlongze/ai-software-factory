"""tests/org/test_concurrency.py — G2: 跨进程并发写安全 (flock + 原子写)。

真实多进程测试:
- A: 两进程同时 save 同一 Project 文件不同记录 → 无丢更新
- B: 两进程同时 save 同一 Task (各自追加 history) → history 不丢
- C: 多 Agent 更新不同 Task → 全部保留
- D: 进程异常退出 (写半途 SIGKILL) → JSON 仍有效 (原子写)
"""

from __future__ import annotations

import json
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest


def _worker_save_project(org_dir: str, project_id: str, name: str) -> None:
    """子进程: 经 ProjectStore 保存一条项目记录 (flock 保护 read-modify-write)。"""
    from org.projects import ProjectStore

    store = ProjectStore(org_dir)
    from org.projects import Project

    p = Project(id=project_id, name=name, lifecycle="idea", repo_path="", language="py")
    store.save_project(p)


def _worker_save_task(task_file: str, task_id: str, hist_actor: str) -> None:
    """子进程: 事务性 update_task 给同一 Task 追加 history (并发 append 不丢)。"""
    from org.management import HistoryEntry, ManagementStore

    store = ManagementStore(str(Path(task_file).parent.parent))  # .../management

    def _append(t):
        t.history.append(HistoryEntry(time="t", actor=hist_actor, action="update", result="ok"))
        return t

    store.update_task(task_id, _append)


def _worker_save_different_tasks(task_file: str, task_id: str, title: str) -> None:
    """子进程: 保存不同 Task (各自独立记录)。"""
    from org.management import ManagementStore, Task

    store = ManagementStore(str(Path(task_file).parent.parent))
    t = Task(id=task_id, title=title, description="")
    store.save_task(t)


def _worker_append_msg(store_path: str, session_id: str, tag: str) -> None:
    """子进程: 并发 append 消息 (SessionStore flock + 锁内刷新)。"""
    from factory_console.console_sessions import SessionStore

    store = SessionStore(store_path)
    store.append_message(session_id, "user", f"msg-{tag}")


# ---------------------------------------------------------------- A: 同 Project 文件, 不同记录


def test_two_processes_save_different_projects_no_lost_update(tmp_path: Path) -> None:
    org_dir = tmp_path / "org"
    org_dir.mkdir()
    (org_dir / "projects.json").write_text(json.dumps({"projects": {}}))

    procs = [
        multiprocessing.Process(
            target=_worker_save_project, args=(str(org_dir), f"P-{i}", f"proj-{i}")
        )
        for i in range(2)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    assert all(p.exitcode == 0 for p in procs)

    data = json.loads((org_dir / "projects.json").read_text())
    projects = data.get("projects", {})
    assert "P-0" in projects and "P-1" in projects, f"丢更新: {list(projects)}"


# ---------------------------------------------------------------- B: 同一 Task, 并发 history append


def test_two_processes_append_history_same_task_no_lost(tmp_path: Path) -> None:
    mgmt_dir = tmp_path / "workspace" / "projects" / "P-1" / "management"
    (mgmt_dir / "backlog").mkdir(parents=True)
    from org.management import ManagementStore, Task

    store = ManagementStore(str(mgmt_dir))
    store.save_task(Task(id="T-1", title="t", description=""))
    task_file = mgmt_dir / "backlog" / "task.json"

    procs = [
        multiprocessing.Process(target=_worker_save_task, args=(str(task_file), "T-1", f"agent-{i}"))
        for i in range(2)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    assert all(p.exitcode == 0 for p in procs)

    t = store.get_task("T-1")
    actors = [h.actor for h in (t.history if t else [])]
    assert "agent-0" in actors and "agent-1" in actors, f"history 丢更新: {actors}"


# ---------------------------------------------------------------- C: 不同 Task 并发


def test_multi_agent_save_different_tasks_all_kept(tmp_path: Path) -> None:
    mgmt_dir = tmp_path / "workspace" / "projects" / "P-1" / "management"
    (mgmt_dir / "backlog").mkdir(parents=True)
    task_file = mgmt_dir / "backlog" / "task.json"

    procs = [
        multiprocessing.Process(
            target=_worker_save_different_tasks, args=(str(task_file), f"T-{i}", f"title-{i}")
        )
        for i in range(4)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    assert all(p.exitcode == 0 for p in procs)

    from org.management import ManagementStore

    store = ManagementStore(str(mgmt_dir))
    ids = sorted(t.id for t in store.list_tasks())
    assert ids == ["T-0", "T-1", "T-2", "T-3"], f"丢任务: {ids}"


# ---------------------------------------------------------------- D: 崩溃安全 (原子写)


def test_atomic_write_survives_kill(tmp_path: Path) -> None:
    """写入中途 kill 进程 → JSON 仍有效 (临时文件 + os.replace)。"""
    from org.management import ManagementStore, Task

    mgmt_dir = tmp_path / "workspace" / "projects" / "P-1" / "management"
    (mgmt_dir / "backlog").mkdir(parents=True)
    store = ManagementStore(str(mgmt_dir))
    store.save_task(Task(id="T-1", title="t", description=""))
    task_file = mgmt_dir / "backlog" / "task.json"

    # 子进程: 反复写 (高频 save), 主进程在写中途 SIGKILL
    script = (
        "import sys,time\n"
        f"sys.path.insert(0, {str(Path(__file__).resolve().parents[2])!r})\n"
        "from org.management import ManagementStore, Task\n"
        f"store = ManagementStore({str(mgmt_dir)!r})\n"
        "for i in range(50):\n"
        "    store.save_task(Task(id='T-1', title=f't{i}', description=''))\n"
        "    time.sleep(0.02)\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.25)  # 让它跑几轮
    proc.kill()
    proc.wait()

    # JSON 必须仍有效 (原子写: 要么旧要么新, 绝无半写)
    raw = task_file.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert "tasks" in data
    assert "T-1" in data["tasks"]


# ---------------------------------------------------------------- E: 会话并发 append (跨进程)


def test_two_processes_append_session_messages(tmp_path: Path) -> None:
    from factory_console.console_sessions import SessionStore

    store_path = tmp_path / "console_sessions.json"
    store = SessionStore(store_path)
    sess = store.create_session(scope="company")
    sid = sess["id"]

    procs = [
        multiprocessing.Process(target=_worker_append_msg, args=(str(store_path), sid, f"p{i}"))
        for i in range(2)
    ]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=30)
    assert all(p.exitcode == 0 for p in procs)

    msgs = store.list_messages(sid)
    tags = {m["content"] for m in msgs}
    assert tags == {"msg-p0", "msg-p1"}, f"会话消息丢更新: {tags}"

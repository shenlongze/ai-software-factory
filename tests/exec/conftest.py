"""tests/exec/conftest.py — Execution Extension 测试 fixtures (Phase A, ADR-0037)。

fixtures:
- exec_dir: 独立 Exec 数据空间 (<root>/exec — 与 tasks/agents/product/intelligence 分离)
- exec_store: ExecStore (四子库门面: requests/results/artifacts/approvals)
- db_path / logger / event_store: 事件集成断言 (org.execution.* 7 事件)
- cli_root: 独立工厂根 (CLI 测试: main(["--root", ...]) 数据根 + 事件库 R/factory.db)
- project_dir: 最小 Python 项目 (沙箱源; 副本创建后原项目零接触)
- git_target: 真实 git 仓库目标项目 (审批 apply 目标; 本地身份 + 基线提交)
- fake_provider: 可配置内容的 FakeProvider (runtime/CLI 测试注入)

sys.path: 挂 factory-core (Core 包) + factory-exec (exec 包父目录 — 以 `exec`
导入)。本目录自洽 (不跨目录依赖 helper): exec_helpers 为唯一名; 测试文件
basename 一律 test_exec_* 前缀 (backend-developer skill 陷阱: 多非包目录共存时
同名模块互相遮蔽)。损坏文件测试的 mkdir 局部化在测试类 autouse fixture
(同 tests/org 模式), 不放在共享目录 fixture — 避免破坏"目录由首次原子写创建"
逆断言。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_FACTORY_EXEC = _ROOT / "factory-exec"
if str(_FACTORY_EXEC) not in sys.path:  # exec 包父目录 (factory-exec/exec/)
    sys.path.insert(0, str(_FACTORY_EXEC))

import pytest

from events.logger import EventLogger
from events.store import EventStore

from exec_helpers import write_files  # noqa: E402  (tests/exec/exec_helpers.py)

PROJECT_FILES = {
    "calc.py": (
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "def sub(a, b):\n"
        "    return a - b\n"
    ),
    "README.md": "# demo project\n",
}


@pytest.fixture
def exec_dir(tmp_path: Path) -> Path:
    """Exec 数据空间 (<root>/exec — 独立目录, 与 tasks/agents 分离)。"""
    return tmp_path / "factory" / "exec"


@pytest.fixture
def exec_store(exec_dir: Path):
    from exec.store import ExecStore

    return ExecStore(exec_dir)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "events.db"


@pytest.fixture
def logger(db_path: Path) -> EventLogger:
    """带事件库的 EventLogger (org.execution.* 事件集成断言); 退出时关闭连接。"""
    s = EventStore(db_path)
    yield EventLogger(s)
    s.close()


@pytest.fixture
def event_store(logger: EventLogger) -> EventStore:
    return logger.store


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根 (CLI 测试: 数据空间 R/exec/, 事件库 R/factory.db)。"""
    return tmp_path / "factory"


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    """最小 Python 项目 (沙箱副本源; 非 git 目录 — Sandbox 自建副本 git)。"""
    proj = tmp_path / "project"
    write_files(proj, PROJECT_FILES)
    return proj


@pytest.fixture
def git_target(tmp_path: Path) -> Path:
    """真实 git 仓库目标项目 (审批 apply 目标; 本地身份 + 基线提交)。"""
    repo = tmp_path / "target"
    write_files(repo, PROJECT_FILES)
    subprocess.run(["git", "-C", str(repo), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@local"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "baseline"], check=True)
    return repo


@pytest.fixture
def fake_provider():
    """FakeProvider (可配置 content/error/usage; 记录调用)。"""
    from exec_helpers import FakeProvider

    return FakeProvider()

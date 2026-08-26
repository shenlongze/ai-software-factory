"""tests/console/test_task_exec_bridge.py — P2b 任务→执行链桥 (factory task prompt|run)。

覆盖 (cli_factory.FactoryCLI.task):
- _find_task: 旧 tasks/*.json + backlog management/task.json
- task prompt: 生成执行指令 (factory run --project --objective --requirement), 只读
- 无任务/无目录 → 明确错误
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

_cli = importlib.import_module("factory-console.cli_factory")


def _make_cli(tmp_path: Path) -> _cli.FactoryCLI:
    data_dir = tmp_path / ".factory"
    data_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(json.dumps({"core": {"data_dir": str(data_dir)}}), encoding="utf-8")
    cfg = _cli.ConfigProvider(user_config_file=cfg_file, environ={})
    return _cli.FactoryCLI(cfg)


def _seed_backlog_task(root: Path, project: str, task_id: str, title: str, desc: str) -> Path:
    tf = root / "workspace" / "projects" / project / "management" / "backlog" / "task.json"
    tf.parent.mkdir(parents=True, exist_ok=True)
    tf.write_text(
        json.dumps(
            {"tasks": {task_id: {"id": task_id, "title": title, "description": desc, "status": "todo", "priority": "P2"}}}
        ),
        encoding="utf-8",
    )
    return tf.parent.parent.parent.parent.parent  # workspace/projects/<project>


class TestTaskExecBridge:
    def test_find_task_in_backlog(self, tmp_path, capsys):
        cli = _make_cli(tmp_path)
        _seed_backlog_task(tmp_path / ".factory", "P-1", "TASK-1", "完善导出功能", "给 X 完善导出")
        task = cli._find_task("TASK-1")
        assert task is not None
        assert task["title"] == "完善导出功能"
        assert task["project"] == "P-1"
        assert cli._find_task("NOPE") is None

    def test_task_prompt_generates_exec_cmd(self, tmp_path, capsys):
        cli = _make_cli(tmp_path)
        _seed_backlog_task(tmp_path / ".factory", "P-1", "TASK-1", "完善导出功能", "给 X 完善导出")
        # 无 product.json/workspace_dir → 项目目录 = workspace/projects/P-1
        rc = cli.task(_cli.argparse.Namespace(task_action="prompt", task_id="TASK-1", project=""))
        out = capsys.readouterr().out
        assert rc == 0
        assert "factory run --project" in out
        assert "--objective '完善导出功能'" in out
        assert "--requirement '给 X 完善导出'" in out

    def test_task_prompt_missing_task(self, tmp_path, capsys):
        cli = _make_cli(tmp_path)
        rc = cli.task(_cli.argparse.Namespace(task_action="prompt", task_id="NOPE", project=""))
        assert rc == 1
        assert "未找到任务" in capsys.readouterr().out


class TestTaskRowsSync:
    def test_task_rows_merges_backlog(self, tmp_path):
        """CLI task list 与 WebUI/会话任务同源: backlog management/task.json 并入。"""
        root = tmp_path / ".factory"
        root.mkdir(parents=True, exist_ok=True)
        _seed_backlog_task(root, "P-1", "TASK-1", "完善导出功能", "desc")
        (root / "tasks").mkdir(exist_ok=True)
        (root / "tasks" / "TASK-0.json").write_text(
            json.dumps({"id": "TASK-0", "title": "旧任务", "status": "done", "project": "P-0"}),
            encoding="utf-8",
        )
        rows = _cli._task_rows(root)
        ids = {r["id"] for r in rows}
        assert "TASK-0" in ids and "TASK-1" in ids
        row = next(r for r in rows if r["id"] == "TASK-1")
        assert row["project"] == "P-1"

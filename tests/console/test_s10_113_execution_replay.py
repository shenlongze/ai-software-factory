"""tests/console/test_s10_113_execution_replay.py — M5-1 执行重放引擎契约 (S10-113)。

计划: docs/sprint10/S10-113-execution-replay-plan.md §2 契约测试要点 1-7
覆盖 (≥6 契约):
1. dry-run 真实重建: 造记录 + audit 事件 → ReplayEngine.dry_run 输出含
   步骤/agent/结果/耗时 (相邻时间戳差); 无效 id → 明确错误 (不瞎跑)
2. re-exec 同输入重跑: 有 input_snapshot → 重跑 → 新 exec_id + 新记录 (可对比)
3. re-exec 缺快照: 旧记录无 input_snapshot → 明确错误不瞎跑
4. 对比报告: 两次执行真实 diff (结果/耗时/步骤数) + --save 落盘文件含真实 diff
5. 记录完善: execute_task 新记录含 input_snapshot (可还原输入)
6. 入口: /board replay (dry-run/--re-exec/--compare) + 自然语言 "重跑 <id>" → 意图路由
7. L4 (受限实现): snapshot → rollback 恢复执行前状态 (项目目录 git 仓库)

诚实纪律: dry-run 真实重建 / re-exec 真实重跑 (fake runner 模拟执行链, 断言
引擎契约) / 对比真实 diff / 缺快照如实报错 — 无 stub 假装成功。

basename 全仓库唯一 (test_s10_113_* 前缀, tests/console 既有模式)。
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录 (含连字符包名)
    sys.path.insert(0, str(_ROOT))

REPLAY = importlib.import_module("factory-console.session.execution_replay")
ACTIONS = importlib.import_module("factory-console.session.actions")
INTENT = importlib.import_module("factory-console.session.intent")
ROUTER = importlib.import_module("factory-console.session.router")
AUDIT = importlib.import_module("factory-console.session.audit")
SESS = importlib.import_module("factory-console.session.session")
CTX = importlib.import_module("factory-console.session.context")


# ------------------------------------------------------------------ 工具

def _write_records(ws: Path, records: list[dict[str, Any]]) -> Path:
    """写 execution_records.json 到临时工作区 (返回文件路径)。"""
    path = ws / "exec" / "execution_records.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _write_audit(ws: Path, events: list[dict[str, Any]]) -> Path:
    """写 audit_events.json 到临时工作区。"""
    path = ws / "audit" / "audit_events.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"events": events}, ensure_ascii=False), encoding="utf-8")
    return path


def _record(
    exec_id: str,
    *,
    task: str = "写登录功能",
    agent: str = "backend-1",
    result: str = "success",
    timestamp: str = "2026-08-25T10:00:00+00:00",
    error: Any = None,
    snapshot: bool = True,
    project: str = "",
) -> dict[str, Any]:
    """构造执行记录 (默认含 input_snapshot — 新记录口径)。"""
    record: dict[str, Any] = {
        "intent": "execute_task",
        "action": "agent.execute_task",
        "agent": agent,
        "task": task,
        "result": result,
        "result_id": exec_id,
        "timestamp": timestamp,
        "error": error,
    }
    if snapshot:
        record["input_snapshot"] = {
            "intent": "execute_task",
            "action": "agent.execute_task",
            "params": {"objective": task, "agent_id": agent},
            "context": {
                "workspace": "",
                "project": project,
                "task_id": "T-1",
                "agent_id": agent,
                "user": "user",
            },
        }
    return record


def _engine(ws: Path, **kw) -> REPLAY.ReplayEngine:
    return REPLAY.ReplayEngine(workspace=ws, **kw)


# ------------------------------------------------------------------ 1. dry-run 真实重建 (契约 1)

class TestDryRun:
    def test_dry_run_reconstructs_timeline(self, tmp_path):
        """记录 + audit 事件 → 时间线: 步骤/agent/结果/耗时 (相邻时间戳差)。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        records = [
            _record("EXS-001", timestamp="2026-08-25T10:00:00+00:00"),
            _record("EXS-002", timestamp="2026-08-25T11:00:00+00:00"),
            _record("EXS-003", timestamp="2026-08-25T12:00:00+00:00"),
        ]
        _write_records(ws, records)
        _write_audit(ws, [
            {"event_type": "TASK_STARTED", "task_id": "T-1", "agent_id": "backend-1",
             "timestamp": "2026-08-25T10:00:01+00:00", "result": "OK",
             "decision_reason": "开始写登录功能"},
            {"event_type": "ARTIFACT_CREATED", "task_id": "T-1", "agent_id": "backend-1",
             "timestamp": "2026-08-25T10:00:20+00:00", "result": "OK",
             "artifact_reference": "/tmp/ws/patch.patch", "decision_reason": "Agent 产物: 写登录功能"},
            {"event_type": "TASK_COMPLETED", "task_id": "T-1", "agent_id": "backend-1",
             "timestamp": "2026-08-25T10:00:30+00:00", "result": "OK",
             "decision_reason": "写登录功能 完成"},
        ])
        tl = _engine(ws).dry_run("EXS-001")
        # 记录 + 3 审计步骤 = 4 步, 按时间排序
        assert len(tl.steps) == 4
        assert tl.steps[0].kind == "record"
        assert [s.kind for s in tl.steps[1:]] == ["audit", "audit", "audit"]
        assert [s.event_type for s in tl.steps[1:]] == [
            "TASK_STARTED", "ARTIFACT_CREATED", "TASK_COMPLETED",
        ]
        # agent/结果/任务
        assert all(s.agent == "backend-1" for s in tl.steps)
        assert tl.agent == "backend-1"
        assert tl.result == "success"
        assert tl.task == "写登录功能"
        # 耗时 = 相邻时间戳差 (真实计算)
        assert tl.steps[0].duration == 1.0   # 10:00:00 → 10:00:01
        assert tl.steps[1].duration == 19.0  # 10:00:01 → 10:00:20
        assert tl.steps[2].duration == 10.0  # 10:00:20 → 10:00:30
        assert tl.steps[3].duration == 0.0   # 末步
        assert tl.total_duration == 30.0
        markdown = tl.to_markdown()
        assert "执行重放时间线: EXS-001" in markdown
        assert "任务开始" in markdown and "产物生成" in markdown and "任务完成" in markdown
        assert "总耗时: 30.0s" in markdown

    def test_dry_run_invalid_id_clear_error(self, tmp_path):
        """无效 exec_id → ReplayError 明确错误 (不瞎跑)。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        _write_records(ws, [_record("EXS-001")])
        with pytest.raises(REPLAY.ReplayError, match="执行记录不存在: EXS-NOPE"):
            _engine(ws).dry_run("EXS-NOPE")

    def test_dry_run_no_audit_single_step(self, tmp_path):
        """无 audit 事件 → 只有记录一步, 耗时 0.0 (诚实: 无更多数据)。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        _write_records(ws, [_record("EXS-001")])
        tl = _engine(ws).dry_run("EXS-001")
        assert len(tl.steps) == 1
        assert tl.steps[0].kind == "record"
        assert tl.total_duration == 0.0

    def test_dry_run_rejects_cross_run_audit_events(self, tmp_path):
        """跨次执行事件 (时间窗外) 不误关联 — 真实匹配非全量倾倒。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        # 记录在 10:00, 事件在 12:00 (2h 外, 默认窗 600s) — 文本含任务名但不关联
        _write_records(ws, [_record("EXS-001", timestamp="2026-08-25T10:00:00+00:00")])
        _write_audit(ws, [
            {"event_type": "TASK_COMPLETED", "task_id": "T-1", "agent_id": "backend-1",
             "timestamp": "2026-08-25T12:00:30+00:00", "result": "OK",
             "decision_reason": "写登录功能 完成"},
        ])
        tl = _engine(ws).dry_run("EXS-001")
        assert len(tl.steps) == 1  # 时间窗外 → 不关联


# ------------------------------------------------------------------ 2/3. re-exec (契约 2/3)

class TestReExec:
    def _runner(self, exec_id: str = "EXS-NEW"):
        def runner(snapshot: dict[str, Any]) -> dict[str, Any]:
            params = snapshot.get("params") or {}
            return {
                "intent": str(snapshot.get("intent") or "execute_task"),
                "action": "agent.execute_task",
                "agent": "backend-1",
                "task": str(params.get("objective") or ""),
                "result": "success",
                "result_id": exec_id,
                "timestamp": "2026-08-25T13:00:00+00:00",
                "error": None,
            }
        return runner

    def test_re_exec_with_snapshot_creates_new_record(self, tmp_path):
        """有 input_snapshot → 重跑 → 新 exec_id + 新记录 (含快照, 可对比)。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        rec_file = _write_records(ws, [_record("EXS-001")])
        engine = _engine(ws)
        new_id = engine.re_exec("EXS-001", self._runner("EXS-NEW"))
        assert new_id == "EXS-NEW"
        records = AUDIT.load_records(rec_file)
        assert [r["result_id"] for r in records] == ["EXS-001", "EXS-NEW"]
        new_record = records[1]
        # 新记录含 input_snapshot (引擎兜底复制) — 可对比
        assert new_record["input_snapshot"]["params"]["objective"] == "写登录功能"
        assert new_record["result"] == "success"
        # 可对原记录 dry-run (时间线可重建)
        assert engine.dry_run("EXS-NEW").record["result_id"] == "EXS-NEW"

    def test_re_exec_missing_snapshot_clear_error(self, tmp_path):
        """旧记录无 input_snapshot → 明确错误不瞎跑 (不执行 runner)。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        _write_records(ws, [_record("EXS-OLD", snapshot=False)])
        called = []

        def runner(snapshot):
            called.append(snapshot)
            return {"result_id": "SHOULD-NOT-RUN"}

        with pytest.raises(REPLAY.ReplayError, match="旧记录无输入快照, 无法重跑"):
            _engine(ws).re_exec("EXS-OLD", runner)
        assert called == []  # 缺快照 → 不瞎跑 (runner 未被调用)

    def test_re_exec_runner_invalid_record_error(self, tmp_path):
        """runner 未返回有效新记录 (缺 result_id) → ReplayError 明确。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        _write_records(ws, [_record("EXS-001")])
        with pytest.raises(REPLAY.ReplayError, match="未返回有效新记录"):
            _engine(ws).re_exec("EXS-001", lambda snap: {})

    def test_re_exec_dedupes_existing_record(self, tmp_path):
        """runner 返回已存在记录 → 幂等不重复写 (兼容 execute_task 已写路径)。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        rec_file = _write_records(ws, [_record("EXS-001"), _record("EXS-NEW")])
        new_id = _engine(ws).re_exec("EXS-001", self._runner("EXS-NEW"))
        assert new_id == "EXS-NEW"
        records = AUDIT.load_records(rec_file)
        assert len(records) == 2  # 无重复


# ------------------------------------------------------------------ 4. 对比报告 (契约 4)

class TestCompare:
    def _two_records(self, ws: Path):
        ws.mkdir(exist_ok=True)
        _write_records(ws, [
            _record("EXS-001", result="success", timestamp="2026-08-25T10:00:00+00:00"),
            _record("EXS-002", result="failed", timestamp="2026-08-25T11:00:00+00:00",
                    error="validation failed: tests red"),
        ])
        _write_audit(ws, [
            {"event_type": "TASK_STARTED", "task_id": "T-1", "agent_id": "backend-1",
             "timestamp": "2026-08-25T10:00:01+00:00", "result": "OK", "decision_reason": "开始写登录功能"},
            {"event_type": "TASK_COMPLETED", "task_id": "T-1", "agent_id": "backend-1",
             "timestamp": "2026-08-25T10:00:30+00:00", "result": "OK", "decision_reason": "写登录功能 完成"},
        ])

    def test_compare_real_diff(self, tmp_path):
        """两次执行 diff: 结果/耗时/步骤数 — 真实差异, 非"看起来一样"。"""
        ws = tmp_path / "ws"
        self._two_records(ws)
        report = _engine(ws).compare("EXS-001", "EXS-002")
        assert "执行对比报告: EXS-001 ↔ EXS-002" in report
        assert "| 结果 | success | failed | ⚠ 不同 |" in report
        assert "**不同**" in report          # 结果差异
        assert "步骤数" in report
        assert "```diff" in report           # 真实 difflib diff
        assert "--- EXS-001" in report and "+++ EXS-002" in report
        assert "record | 执行记录 | backend-1 | success" in report
        assert "record | 执行记录 | backend-1 | failed" in report
        assert "存在" in report and "项差异" in report  # 结论含差异计数

    def test_compare_save_writes_markdown(self, tmp_path):
        """--save: 落盘 docs/sprint10/replay-compare-<id1>-<id2>.md 含真实 diff。"""
        ws = tmp_path / "ws"
        self._two_records(ws)
        save_dir = tmp_path / "docs" / "sprint10"
        engine = _engine(ws)
        report = engine.compare("EXS-001", "EXS-002", save_to=save_dir)
        target = save_dir / "replay-compare-EXS-001-EXS-002.md"
        assert target.is_file()
        content = target.read_text(encoding="utf-8")
        assert content == report
        assert "```diff" in content and "failed" in content  # 真实 diff 落盘

    def test_compare_same_id_error(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        _write_records(ws, [_record("EXS-001")])
        with pytest.raises(REPLAY.ReplayError, match="不能是同一 id"):
            _engine(ws).compare("EXS-001", "EXS-001")

    def test_compare_missing_id_error(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        _write_records(ws, [_record("EXS-001")])
        with pytest.raises(REPLAY.ReplayError, match="执行记录不存在: EXS-002"):
            _engine(ws).compare("EXS-001", "EXS-002")


# ------------------------------------------------------------------ 5. 记录完善 (契约 5)

class TestRecordSnapshot:
    class _FakeExecCli:
        """exec.cli 桩 (monkeypatch _load_exec_cli): 记录调用, 返回注入结果。"""

        def __init__(self) -> None:
            self.result = {
                "ok": True,
                "command": "run",
                "result_id": "EXR-001",
                "status": "success",
                "error": None,
                "artifacts": [{"path": "/tmp/ws/patch.patch", "id": "art-1"}],
                "usage": {"cost_usd": "0.01", "total_tokens": 1234, "duration": "3.2s"},
                "exit_code": 0,
            }

        def cmd_exec_run(self, root, args):
            return dict(self.result)

    def test_execute_task_record_has_input_snapshot(self, monkeypatch, tmp_path):
        """execute_task 新记录含 input_snapshot (params/objective 完整输入可还原)。"""
        root = tmp_path / "ws"
        root.mkdir()
        monkeypatch.setattr(ACTIONS, "_load_exec_cli", lambda: self._FakeExecCli())
        intent = INTENT.IntentObject(
            intent_type="run_task",
            params={"objective": "实现登录功能", "agent_id": "backend-1", "task_id": "T-9"},
            raw="实现登录功能",
        )
        ctx = ACTIONS.ExecutionContext(
            workspace=root,
            session=CTX.SessionContext(workspace=str(root)),
            intent=intent,
            user="alice",
        )
        result = ACTIONS.build_default_actions().get("agent.execute_task").execute(ctx)
        assert result.ok is True
        records = AUDIT.load_records(root / "exec" / "execution_records.json")
        assert len(records) == 1
        record = records[0]
        snapshot = record["input_snapshot"]
        assert snapshot["intent"] == "run_task"
        assert snapshot["action"] == "agent.execute_task"
        assert snapshot["params"]["objective"] == "实现登录功能"
        assert snapshot["params"]["task_id"] == "T-9"
        assert snapshot["context"]["workspace"] == str(root)
        assert snapshot["context"]["task_id"] == "T-9"
        assert snapshot["context"]["agent_id"] == "backend-1"
        # 记录本身 JSON 可序列化 (落盘可重放)
        json.dumps(record, ensure_ascii=False)

    def test_input_snapshot_filters_non_json_values(self, monkeypatch, tmp_path):
        """非 JSON 参数 (如对象) → 快照降级为字符串, 不破坏记录可落盘。"""
        root = tmp_path / "ws"
        root.mkdir()
        monkeypatch.setattr(ACTIONS, "_load_exec_cli", lambda: self._FakeExecCli())
        intent = INTENT.IntentObject(
            intent_type="run_task",
            params={"objective": "x", "weird": object()},
            raw="x",
        )
        ctx = ACTIONS.ExecutionContext(
            workspace=root,
            session=CTX.SessionContext(workspace=str(root)),
            intent=intent,
        )
        ACTIONS.build_default_actions().get("agent.execute_task").execute(ctx)
        records = AUDIT.load_records(root / "exec" / "execution_records.json")
        snapshot = records[0]["input_snapshot"]
        assert snapshot["params"]["objective"] == "x"
        assert isinstance(snapshot["params"]["weird"], str)  # 对象 → 字符串 (失败安全)
        json.dumps(records[0], ensure_ascii=False)


# ------------------------------------------------------------------ 6. 入口 (契约 6)

class TestEntrypoints:
    def test_intent_replay_exec_rule(self):
        """自然语言 "重跑/重放/回放/replay <exec_id>" → replay_exec 意图。"""
        parser = INTENT.KeywordIntentParser()
        intent = parser.parse("重跑 EXS-abc")
        assert intent is not None
        assert intent.intent_type == INTENT.INTENT_REPLAY_EXEC
        assert intent.parameters["exec_id"] == "EXS-abc"
        assert parser.parse("replay EXS-abc").intent_type == INTENT.INTENT_REPLAY_EXEC
        assert parser.parse("重放 EXS-abc").parameters["exec_id"] == "EXS-abc"
        assert parser.parse("回放 EXS-abc").intent_type == INTENT.INTENT_REPLAY_EXEC
        # 不抢既有映射 (基线零变化)
        assert parser.parse("修复 main.py").intent_type == INTENT.INTENT_RUN_TASK

    def test_router_maps_replay_exec_to_action(self):
        """DEFAULT_ROUTES 映射 replay_exec → 已注册 action (路由可达)。"""
        assert ROUTER.DEFAULT_ROUTES["replay_exec"] == "replay_exec"
        registry = ACTIONS.build_default_actions()
        action = registry.get("replay_exec")
        assert action is not None
        intent = INTENT.IntentObject(intent_type="replay_exec", params={"exec_id": "EXS-1"})
        routed = ROUTER.IntentRouter().route(intent, registry)
        assert routed.name == "replay_exec"

    def test_board_replay_dry_run(self, capsys, tmp_path):
        """/board replay <id> 默认 dry-run → 时间线输出。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        _write_records(ws, [_record("EXS-001")])
        sess = SESS.InteractiveSession(
            context_manager=CTX.ContextManager(workspace=str(ws)),
        )
        sess._dispatch("/board replay EXS-001")
        out = capsys.readouterr().out
        assert "执行重放时间线: EXS-001" in out
        assert "backend-1" in out and "写登录功能" in out

    def test_board_replay_compare_save(self, capsys, tmp_path):
        """/board replay <id1> --compare <id2> --save → 报告 + 落盘 docs/sprint10/。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        _write_records(ws, [
            _record("EXS-001", result="success", timestamp="2026-08-25T10:00:00+00:00"),
            _record("EXS-002", result="failed", timestamp="2026-08-25T11:00:00+00:00"),
        ])
        _write_audit(ws, [
            {"event_type": "TASK_STARTED", "task_id": "T-1", "agent_id": "backend-1",
             "timestamp": "2026-08-25T10:00:01+00:00", "result": "OK", "decision_reason": "开始写登录功能"},
        ])
        sess = SESS.InteractiveSession(
            context_manager=CTX.ContextManager(workspace=str(ws)),
        )
        # --save 落盘到仓库 docs/sprint10 (BoardCommand 硬编码仓库路径) —
        # monkeypatch 仓库路径不现实, 只断言报告输出 + rc; 引擎级落盘由
        # test_compare_save_writes_markdown 覆盖
        sess._dispatch("/board replay EXS-001 --compare EXS-002")
        out = capsys.readouterr().out
        assert "执行对比报告: EXS-001 ↔ EXS-002" in out
        assert "```diff" in out
        assert "❌" not in out

    def test_board_replay_re_exec(self, capsys, monkeypatch, tmp_path):
        """/board replay <id> --re-exec → 同输入重跑 → 新记录 (含 input_snapshot)。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        _write_records(ws, [_record("EXS-001")])
        rec_file = ws / "exec" / "execution_records.json"

        class _FakeExec:
            def cmd_exec_run(self, root, args):
                return {
                    "ok": True, "command": "run", "result_id": "EXS-REEXEC",
                    "status": "success", "error": None, "artifacts": [],
                    "usage": {"cost_usd": "0.01", "duration": "3.2s"}, "exit_code": 0,
                }

        monkeypatch.setattr(ACTIONS, "_load_exec_cli", lambda: _FakeExec())
        sess = SESS.InteractiveSession(
            context_manager=CTX.ContextManager(workspace=str(ws)),
        )
        sess._dispatch("/board replay EXS-001 --re-exec")
        out = capsys.readouterr().out
        assert "重跑完成: EXS-001 → 新执行 EXS-REEXEC" in out
        records = AUDIT.load_records(rec_file)
        assert any(r["result_id"] == "EXS-REEXEC" for r in records)
        new_rec = next(r for r in records if r["result_id"] == "EXS-REEXEC")
        assert new_rec["input_snapshot"]["params"]["objective"] == "写登录功能"

    def test_board_replay_invalid_id_error(self, capsys, tmp_path):
        """/board replay 无效 id → 明确错误 (不瞎跑)。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        _write_records(ws, [_record("EXS-001")])
        sess = SESS.InteractiveSession(
            context_manager=CTX.ContextManager(workspace=str(ws)),
        )
        sess._dispatch("/board replay EXS-NOPE")
        out = capsys.readouterr().out
        assert "❌ 重放失败" in out
        assert "执行记录不存在: EXS-NOPE" in out

    def test_natural_language_replay_routes(self, capsys, tmp_path):
        """自然语言 "重跑 EXS-001" → 意图路由 → replay_exec action → dry-run 时间线。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        _write_records(ws, [_record("EXS-001")])
        sess = SESS.InteractiveSession(
            context_manager=CTX.ContextManager(workspace=str(ws)),
            intent_parser=INTENT.KeywordIntentParser(),  # 纯规则, 禁 LLM
        )
        sess._dispatch("重跑 EXS-001")
        out = capsys.readouterr().out
        assert "重放时间线: EXS-001" in out or "执行重放时间线: EXS-001" in out
        assert "backend-1" in out


# ------------------------------------------------------------------ 7. L4 快照回滚 (契约 7, 受限实现)

class TestL4SnapshotRollback:
    def _git_repo(self, tmp_path: Path, content: str = "v1") -> Path:
        """临时 git 仓库项目目录 (基线提交)。"""
        repo = tmp_path / "proj"
        repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.name", "t"], check=True
        )
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "t@t"], check=True
        )
        (repo / "a.txt").write_text(content, encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "base"], check=True)
        return repo

    def test_snapshot_then_rollback_restores_state(self, tmp_path):
        """snapshot_before → 修改 → rollback → 恢复执行前状态 (git 回滚)。"""
        repo = self._git_repo(tmp_path)
        ws = tmp_path / "ws"
        ws.mkdir()
        record = _record("EXS-001", project=str(repo))
        _write_records(ws, [record])
        engine = _engine(ws)
        baseline = engine.snapshot_before("EXS-001")
        assert baseline  # 基线提交 hash
        # 执行修改
        (repo / "a.txt").write_text("v2-changed", encoding="utf-8")
        (repo / "new.txt").write_text("extra", encoding="utf-8")
        engine.rollback("EXS-001")
        # 恢复执行前状态
        assert (repo / "a.txt").read_text(encoding="utf-8") == "v1"
        assert not (repo / "new.txt").exists()
        # pre_snapshot 已清除 (一次性)
        records = AUDIT.load_records(ws / "exec" / "execution_records.json")
        assert "pre_snapshot" not in records[0]

    def test_rollback_without_snapshot_error(self, tmp_path):
        """未 snapshot_before → rollback 明确错误。"""
        ws = tmp_path / "ws"
        ws.mkdir()
        _write_records(ws, [_record("EXS-001")])
        with pytest.raises(REPLAY.ReplayError, match="无 L4 快照"):
            _engine(ws).rollback("EXS-001")

    def test_snapshot_requires_git_repo(self, tmp_path):
        """非 git 仓库项目目录 → snapshot_before 明确错误 (不静默)。"""
        plain = tmp_path / "plain"
        plain.mkdir()
        ws = tmp_path / "ws"
        ws.mkdir()
        _write_records(ws, [_record("EXS-001", project=str(plain))])
        with pytest.raises(REPLAY.ReplayError, match="需要 git 仓库项目目录"):
            _engine(ws).snapshot_before("EXS-001")


# ------------------------------------------------------------------ 一致性 (契约 6 补充: 注册表)

def test_replay_exec_registry_consistency():
    """S10-112 一致性: 意图规则/路由/action 三方存在且连通。"""
    rules_intents = {rule[1] for rule in INTENT._KEYWORD_RULES}
    assert INTENT.INTENT_REPLAY_EXEC in rules_intents
    assert INTENT.INTENT_REPLAY_EXEC in ROUTER.DEFAULT_ROUTES
    assert ROUTER.DEFAULT_ROUTES[INTENT.INTENT_REPLAY_EXEC] == "replay_exec"
    registry_names = {a.name for a in ACTIONS.build_default_actions().list()}
    assert "replay_exec" in registry_names

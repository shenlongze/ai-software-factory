"""tests/console/test_s10_117_execution_quality.py — K-2 执行质量分 + 优选 (S10-117).

契约 (设计 docs/sprint10/S10-117-k2-execution-quality-plan.md §2, ≥10):
1. C-2 质量分确定性: 成功/失败/低质量 三类 fixture → 分数确定 + breakdown + 落盘 quality 字段
2. 评分器失败安全: 评分器异常 → score=None + reason, 不阻断执行 (execute_task 仍成功)
3. C-3 多候选优选: 多候选 fixture → ranking + selected + breakdown + reason;
   全失败 → rejection_reason 非空
4. 单候选不破坏: 单候选路径行为与改造前一致 (strategy off → evaluation={} + 单次调用)
5. B-5 失败策略: 低分 fixture → 重试有界 → 换 Agent (router 替代资源); 不无限重试;
   无替代 → 诚实报告 "低分无替代资源"
6. 路由回写: CapabilityResource.quality_score 字段存在且可排序 (priority 后
   tiebreaker); K-1 无分 fixture 行为零变化
7. B-6 PRD 评分: PRD fixture → 确定性分数 + 维度; 落盘 PRD.quality.json
8. B-6 工程计划评分: engineering fixture → 分数 + 维度; 落盘 engineering.quality.json
9. 展示只读: render_quality 渲染后 mtime 不变
10. 注册表门禁: /board quality 视图在 commands.py 注册可见
11. 全量回归 0 新增失败 (由本套件 + 版本断言同步保证)

basename 全仓库唯一 (test_s10_117_* 前缀); exec 辅助经 sys.path 挂载
(tests/exec/exec_helpers.py — 唯一名 helper, 与 test_console_agent_executor_api 同模式)。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_ROOT / "factory-core") not in sys.path:
    sys.path.insert(0, str(_ROOT / "factory-core"))
if str(_ROOT / "factory-exec") not in sys.path:
    sys.path.insert(0, str(_ROOT / "factory-exec"))
if str(_ROOT / "tests" / "exec") not in sys.path:
    sys.path.insert(0, str(_ROOT / "tests" / "exec"))

from exec_helpers import FakeProvider, git_diff_text, make_request, write_files  # noqa: E402

ACTIONS = importlib.import_module("factory-console.session.actions")
ACT = importlib.import_module("factory-console.session.action")
AUDIT = importlib.import_module("factory-console.session.audit")
BOARD = importlib.import_module("factory-console.session.board")
CMD = importlib.import_module("factory-console.session.commands")
CR = importlib.import_module("factory-console.session.capability_router")
CTX = importlib.import_module("factory-console.session.context")
EQ = importlib.import_module("factory-console.session.execution_quality")
INTENT = importlib.import_module("factory-console.session.intent")
ORCH = importlib.import_module("factory-console.session.orchestrator")
RT = importlib.import_module("exec.agent_runtime")

#: 最小 Python 项目 (沙箱源)
MINI_PROJECT = {
    "calc.py": "def add(a, b):\n    return a + b\n",
    "README.md": "# demo\n",
}
CALC_BEFORE = "def add(a, b):\n    return a + b\n\n"
CALC_AFTER = "def add(a, b):\n    return abs(a + b)\n\n"


def _intent(intent_type: str = "run_task", **params):
    return INTENT.IntentObject(intent_type=intent_type, params=params, raw="x")


def _exec_ctx(root: Path, intent=None):
    return ACT.ExecutionContext(
        workspace=root,
        session=CTX.SessionContext(workspace=str(root)),
        user="user",
        intent=intent,
    )


class _FakeExecCli:
    """exec.cli 桩 (monkeypatch _load_exec_cli): 记录调用, 返回注入结果。"""

    def __init__(self, result: dict | None = None) -> None:
        self.calls: list = []
        self.result = result or {
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
        self.calls.append((root, args))
        return dict(self.result)


def _product(**kw):
    defaults = {
        "name": "测试产品",
        "problem": "用户管理账目困难",
        "user": "个人用户",
        "platform": "mobile",
        "core_features": ["记账", "报表", "预算"],
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


GOOD_PRD = """# 测试产品 — 产品需求文档 (PRD)

## Product Overview
面向个人用户的记账应用, 平台: mobile。
## Problem
用户管理账目困难, 需要自动记账与报表。
## Target User
个人用户。
## Core Features
- 记账
- 报表
- 预算
## Usage Scenario
用户每天记录收支, 月末查看报表。
## Future Direction
未来支持多币种与团队共享。
## User Stories
作为用户, 我想快速记账。
## Acceptance Criteria
- 可创建一笔收支记录
- 报表按月汇总
- 预算超支提醒
"""

GOOD_PLAN = {
    "name": "测试产品",
    "platform": "mobile",
    "architecture": "Flutter + Backend API",
    "modules": [{"name": "记账", "slug": "bookkeeping"}],
    "technical_tasks": [
        {"id": "database_schema", "name": "数据库 Schema 设计", "type": "database"},
        {"id": "backend_api", "name": "后端 API 实现", "type": "backend"},
        {"id": "frontend_page", "name": "前端页面实现", "type": "frontend"},
        {"id": "test_suite", "name": "测试用例编写", "type": "test"},
    ],
    "prd_generated": True,
}


# ================================================================== 1. C-2 质量分确定性 + 落盘


class TestC2QualityDeterminism:
    def test_three_fixtures_deterministic_breakdown(self):
        """成功/失败/低质量 三类 fixture → 分数确定 + 分维度 breakdown + 规则说明。"""
        s1 = EQ.score_execution(
            {"result": "success"},
            {
                "validation_result": {"passed": True},
                "patch_apply_result": {"applied": True},
            },
        )
        s2 = EQ.score_execution(
            {"result": "success"},
            {
                "validation_result": {"passed": True},
                "patch_apply_result": {"applied": True},
            },
        )
        assert s1.score == s2.score  # 确定性
        assert s1.score > EQ.LOW_SCORE_THRESHOLD  # 成功 → 高分
        assert set(s1.dimensions) == set(EQ.EXECUTION_WEIGHTS)
        assert s1.evaluator_version == "1.0"
        assert s1.scored_at and s1.rules  # 可审计 (时间 + 规则说明)

        f1 = EQ.score_execution({"result": "failed", "error": "boom"}, {})
        f2 = EQ.score_execution({"result": "failed", "error": "boom"}, {})
        assert f1.score == f2.score == EQ.FAILURE_SCORE_CAP
        assert f1.score < EQ.LOW_SCORE_THRESHOLD  # 失败 → 低分 (B-5 触发)
        assert f1.dimensions["validation"] == 0.0  # 硬条件

        lq = EQ.score_execution(
            {"result": "success"},
            {
                "scope_result": {"changed_files": 8, "changed_lines": 300},
                "requirement_coverage_result": {"covered": 1, "total": 10},
            },
        )
        assert lq.score < EQ.LOW_SCORE_THRESHOLD  # 大范围+低覆盖 → 低质量
        assert any("scope" in r and "权重" in r for r in lq.rules)

    def test_execution_record_quality_field_persisted(self, monkeypatch, tmp_path):
        """execute_task 落盘 quality 字段 (score/dimensions/evaluator_version/scored_at)。"""
        root = tmp_path / "ws"
        root.mkdir()
        cli = _FakeExecCli()
        monkeypatch.setattr(ACTIONS, "_load_exec_cli", lambda: cli)
        intent = _intent("run_task", objective="实现登录功能", task_id="T-9")
        result = ACTIONS.build_default_actions().get("agent.execute_task").execute(
            _exec_ctx(root, intent=intent)
        )
        assert result.ok is True
        records = AUDIT.load_records(root / "exec" / "execution_records.json")
        assert len(records) == 1
        quality = records[0]["quality"]
        assert isinstance(quality, dict)
        assert quality["score"] is not None and 0 < quality["score"] <= 1
        assert set(quality["dimensions"]) == set(EQ.EXECUTION_WEIGHTS)
        assert quality["evaluator_version"] == "1.0"
        assert quality["scored_at"]
        assert "quality" in ACTIONS._RECORD_KEYS  # _RECORD_KEYS 同步


# ================================================================== 2. 评分器失败安全


class TestScorerFailureSafe:
    def test_scorer_exception_score_none_reason(self):
        """评分器异常 → score=None + reason (诚实标注, 不臆造分数)。"""

        class _EvilDict(dict):
            def get(self, key, default=None):  # noqa: ARG002
                raise RuntimeError("scorer boom")

        # 非空 evil dict (空 dict 为 falsy, `evidence or {}` 会替换掉 — 须带键)
        q = EQ.score_execution({"result": "success"}, _EvilDict({"x": 1}))
        assert q.score is None
        assert q.reason and "quality scorer failed" in q.reason

    def test_execute_task_does_not_block_on_scorer_failure(self, monkeypatch, tmp_path):
        """评分器异常不阻断执行: execute_task 仍成功 + 记录 quality score=None。"""
        root = tmp_path / "ws"
        root.mkdir()

        def _boom(record, evidence):  # noqa: ARG001
            raise RuntimeError("scorer boom")

        monkeypatch.setattr(EQ, "score_execution", _boom)
        cli = _FakeExecCli()
        monkeypatch.setattr(ACTIONS, "_load_exec_cli", lambda: cli)
        intent = _intent("run_task", objective="实现登录功能", task_id="T-9")
        result = ACTIONS.build_default_actions().get("agent.execute_task").execute(
            _exec_ctx(root, intent=intent)
        )
        assert result.ok is True  # 不阻断执行
        records = AUDIT.load_records(root / "exec" / "execution_records.json")
        quality = records[0]["quality"]
        assert quality["score"] is None
        assert "quality unavailable" in (quality.get("reason") or "")


# ================================================================== 3-4. C-3 多候选优选 / 单候选零变化


def _patch_content(tmp_path: Path) -> str:
    return git_diff_text(tmp_path, {"calc.py": CALC_BEFORE}, {"calc.py": CALC_AFTER})


def _ok_content(tmp_path: Path) -> str:
    return "fixed the bug\n<patch>\n" + _patch_content(tmp_path) + "\n</patch>"


def _bug_project(tmp_path: Path) -> Path:
    proj = tmp_path / "bug-project"
    write_files(proj, {"calc.py": CALC_BEFORE, "README.md": "# demo\n"})
    return proj


def _runtime(tmp_path: Path, provider, *, strategy: bool, runs: int = 3) -> RT.AgentRuntime:
    work_root = tmp_path / "work"
    work_root.mkdir(parents=True, exist_ok=True)
    return RT.AgentRuntime(
        provider,
        store=None,
        logger=None,
        work_root=work_root,
        execution_strategy_enabled=strategy,
        execution_strategy_runs=runs,
    )


class TestC3MultiCandidate:
    def test_multi_candidate_ranking_selected_breakdown_reason(self, tmp_path):
        """多候选 (3 成功) → ranking + selected + score_breakdown + reason。"""
        provider = FakeProvider(content=_ok_content(tmp_path))
        runtime = _runtime(tmp_path, provider, strategy=True, runs=3)
        result = runtime.execute(make_request(
            request_id="EXR-multi-1", project_dir=_bug_project(tmp_path)
        ))
        assert result.is_success
        evaluation = result.evaluation
        assert evaluation  # C-3: 评估明细随结果透出
        assert len(evaluation["ranking"]) == 3
        assert evaluation["selected_candidate_id"] == evaluation["ranking"][0]
        assert evaluation["selected_candidate_id"] is not None
        assert len(evaluation["score_breakdown"]) == 3
        assert evaluation["rejection_reason"] is None
        assert evaluation["total_candidates"] == 3
        # score_breakdown 与 ranking 同序 (可解释)
        assert [b["candidate_id"] for b in evaluation["score_breakdown"]] == evaluation["ranking"]
        assert runtime.last_evaluation is not None

    def test_all_failed_rejection_reason_nonempty(self, tmp_path):
        """全候选失败 → rejection_reason 非空 (诚实拒绝, 不静默选最差)。"""
        provider = FakeProvider(error="provider error: empty content")
        runtime = _runtime(tmp_path, provider, strategy=True, runs=3)
        result = runtime.execute(make_request(
            request_id="EXR-multi-fail-1", project_dir=_bug_project(tmp_path)
        ))
        assert not result.is_success
        evaluation = result.evaluation
        assert evaluation["rejection_reason"]
        assert "no qualified candidate" in evaluation["rejection_reason"]
        assert evaluation["selected_candidate_id"] is None
        assert evaluation["ranking"]  # 全排序诚实呈现 (最不差置顶)

    def test_single_candidate_legacy_zero_change(self, tmp_path):
        """单候选 (strategy 关) → 行为与改造前一致: evaluation={} + 单次 Provider 调用。"""
        provider = FakeProvider(content=_ok_content(tmp_path))
        runtime = _runtime(tmp_path, provider, strategy=False)
        result = runtime.execute(make_request(
            request_id="EXR-single-1", project_dir=_bug_project(tmp_path)
        ))
        assert result.is_success
        assert len(provider.calls) == 1  # 单次调用 (旧流程)
        assert result.evaluation == {}  # 单候选路径零变化 (无评估明细)
        assert runtime.last_candidates == []


# ================================================================== 5. B-5 失败策略 (低分换资源)


def _low_quality_fail(calls: list, agents: list):
    """execute_fn mock: 恒低分失败 (quality.score=0.2 < 0.5), 记录调用 + agent。"""
    def fn(task, project_dir, workspace):  # noqa: ARG001
        calls.append(1)
        agents.append(str(task.get("agent") or ""))
        return {
            "success": False,
            "error": "boom",
            "quality": {"score": 0.2, "dimensions": {}, "evaluator_version": "1.0"},
        }
    return fn


class TestB5LowScoreStrategy:
    def test_low_score_switch_resource_bounded(self, tmp_path):
        """低分 fixture → 重试有界 → 换 Agent (router 替代资源); 不无限重试。"""
        root = tmp_path / "ws"
        pdir = root / "projects" / "p1"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "project.json").write_text(
            json.dumps({"name": "P1", "status": "development"}), encoding="utf-8"
        )
        router = CR.CapabilityRouter([
            CR.CapabilityResource(
                id="backend-2", type="agent", capabilities=["code_generation"],
                priority=5, quality_score=0.9,
            ),
        ])
        orch = ORCH.ExecutionOrchestrator(root, resource_router=router)
        state = ORCH.ExecutionState(project="p1")
        task = {"id": "T1", "name": "实现登录功能", "agent": "backend-1"}
        calls: list[int] = []
        agents: list[str] = []
        outcome = orch._execute_with_retry(
            pdir, state, task, _low_quality_fail(calls, agents), max_retry=1
        )
        assert outcome["success"] is False
        assert task["resource_switched"] is True
        assert task["agent"] == "backend-2"  # 已换资源
        assert agents == ["backend-1", "backend-1", "backend-2", "backend-2"]
        # 有界: 1 次初始 + 1 次重试 + 1 次换资源后尝试 + 1 次终态 = 4 次, 不无限
        assert len(calls) == 4
        assert "resource_switch_reason" in task

    def test_low_score_no_alternative_honest_report(self, tmp_path):
        """无替代资源 → 诚实报告 "低分无替代资源", 不额外尝试。"""
        root = tmp_path / "ws"
        pdir = root / "projects" / "p1"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "project.json").write_text(
            json.dumps({"name": "P1", "status": "development"}), encoding="utf-8"
        )
        router = CR.CapabilityRouter([])  # 无候选 → 无替代
        orch = ORCH.ExecutionOrchestrator(root, resource_router=router)
        state = ORCH.ExecutionState(project="p1")
        task = {"id": "T1", "name": "实现登录功能", "agent": "backend-1"}
        calls: list[int] = []
        agents: list[str] = []
        outcome = orch._execute_with_retry(
            pdir, state, task, _low_quality_fail(calls, agents), max_retry=1
        )
        assert outcome["success"] is False
        assert task["low_quality_report"] == "低分无替代资源"
        assert len(calls) == 2  # 1 次初始 + 1 次重试, 无换资源额外尝试
        assert "resource_switched" not in task

    def test_high_score_no_switch(self, tmp_path):
        """非低分失败 → 不触发换资源 (只走既有重试语义, 行为不变)。"""
        root = tmp_path / "ws"
        pdir = root / "projects" / "p1"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "project.json").write_text(
            json.dumps({"name": "P1", "status": "development"}), encoding="utf-8"
        )
        router = CR.CapabilityRouter([
            CR.CapabilityResource(id="backend-2", type="agent", capabilities=["x"]),
        ])
        orch = ORCH.ExecutionOrchestrator(root, resource_router=router)
        state = ORCH.ExecutionState(project="p1")
        task = {"id": "T1", "name": "实现登录功能", "agent": "backend-1"}
        calls: list[int] = []

        def fn(task_, project_dir_, workspace_):  # noqa: ARG001
            calls.append(1)
            return {
                "success": False,
                "error": "boom",
                "quality": {"score": 0.9, "dimensions": {}},
            }

        orch._execute_with_retry(pdir, state, task, fn, max_retry=1)
        assert len(calls) == 2  # 既有重试语义 (不换资源)
        assert "resource_switched" not in task


# ================================================================== 6. 路由回写 (quality_score)


class TestRouterQualityScore:
    def test_quality_score_field_and_tiebreaker(self):
        """quality_score 字段存在 + priority 后 tiebreaker (quality desc → version → load)。"""
        router = CR.CapabilityRouter([
            CR.CapabilityResource(id="a", type="agent", capabilities=["x"],
                                  priority=1, quality_score=0.9),
            CR.CapabilityResource(id="b", type="agent", capabilities=["x"],
                                  priority=1, quality_score=0.4, version="2.0.0"),
            CR.CapabilityResource(id="c", type="agent", capabilities=["x"],
                                  priority=1, quality_score=0.4, version="1.0.0"),
            CR.CapabilityResource(id="d", type="agent", capabilities=["x"],
                                  priority=1, quality_score=None),
        ])
        decision = router.route(CR.CapabilityRequest(objective="x", capabilities=["x"]))
        assert decision is not None and decision.resource_id == "a"  # quality 最高
        assert "quality" in decision.reason  # reason 含质量分 (可解释)

    def test_quality_score_validation(self):
        """quality_score 越界 → 响亮报错 (不静默接受脏资源)。"""
        with pytest.raises(ValueError):
            CR.CapabilityResource(id="bad", type="agent", quality_score=1.5)
        ok = CR.CapabilityResource(id="ok", type="agent", quality_score=0.5)
        assert ok.quality_score == 0.5

    def test_k1_fixture_zero_change(self):
        """K-1 无 quality_score fixture → 排序行为零变化 (priority→version→load→id)。"""
        fixture = [
            CR.CapabilityResource(id="skill-a", type="skill", capabilities=["frontend_ui"],
                                  priority=5, version="1.0.0", load=0.0),
            CR.CapabilityResource(id="skill-b", type="skill", capabilities=["frontend_ui"],
                                  priority=5, version="2.0.0", load=0.0),
            CR.CapabilityResource(id="agent-a", type="agent", capabilities=["frontend_ui"],
                                  priority=3, version="1.0.0", load=0.0),
            CR.CapabilityResource(id="agent-b", type="agent", capabilities=["frontend_ui"],
                                  priority=3, version="1.0.0", load=0.5),
            CR.CapabilityResource(id="mcp-b", type="mcp", capabilities=["frontend_ui"],
                                  priority=2, version="1.0.0", load=0.0),
        ]
        router = CR.CapabilityRouter(fixture)
        decision = router.route(CR.CapabilityRequest(objective="做前端页面", capabilities=["frontend_ui"]))
        # 排序不变: priority desc → version desc → load asc → id → 首位 skill-b
        assert decision is not None and decision.resource_id == "skill-b"
        assert all(r.quality_score is None for r in fixture)  # 缺省 None 中性


# ================================================================== 7-8. B-6 PRD/工程计划评分


class TestB6PlanScores:
    def test_prd_deterministic_score_and_dimensions(self):
        """PRD fixture → 确定性分数 + 六维 breakdown + 规则说明。"""
        p = _product()
        q1 = EQ.score_prd(GOOD_PRD, p)
        q2 = EQ.score_prd(GOOD_PRD, p)
        assert q1.score == q2.score
        assert 0 < q1.score <= 1
        assert set(q1.dimensions) == set(EQ.PRD_WEIGHTS)
        assert len(q1.rules) == len(EQ.PRD_WEIGHTS)
        assert q1.dimensions["完整性"] > 0.5
        assert q1.dimensions["可测性"] > 0.5  # 含 Acceptance Criteria

    def test_engineering_deterministic_score_and_dimensions(self):
        """engineering fixture → 分数 + 六维 breakdown (M3d 权重)。"""
        q1 = EQ.score_engineering(GOOD_PLAN, _product())
        q2 = EQ.score_engineering(GOOD_PLAN, _product())
        assert q1.score == q2.score
        assert 0 < q1.score <= 1
        assert set(q1.dimensions) == set(EQ.ENGINEERING_WEIGHTS)
        assert q1.dimensions["依赖"] == 1.0  # db→backend→frontend→test 全链
        assert q1.dimensions["可测性"] == 1.0  # 含 test 任务

    def test_plan_quality_files_persisted(self, tmp_path):
        """prepare_project 侧落盘 PRD.quality.json + engineering.quality.json。"""
        product_dir = tmp_path / "projects" / "p1"
        product_dir.mkdir(parents=True, exist_ok=True)
        ACTIONS._write_plan_quality_files(product_dir, GOOD_PRD, GOOD_PLAN, _product())
        prd_q = json.loads((product_dir / "PRD.quality.json").read_text(encoding="utf-8"))
        eng_q = json.loads(
            (product_dir / "engineering.quality.json").read_text(encoding="utf-8")
        )
        assert prd_q["score"] is not None and prd_q["dimensions"]
        assert eng_q["score"] is not None and eng_q["dimensions"]
        assert prd_q["evaluator_version"] == "1.0"
        assert eng_q["evaluator_version"] == "1.0"


# ================================================================== 9. 展示只读


class TestQualityDisplayReadOnly:
    def test_render_quality_mtime_unchanged(self, tmp_path):
        """/board quality 渲染后 mtime 不变 (只读铁律)。"""
        ws = tmp_path / "ws"
        pdir = ws / "projects" / "p1"
        pdir.mkdir(parents=True, exist_ok=True)
        (pdir / "project.json").write_text(
            json.dumps({"name": "P1", "status": "development"}), encoding="utf-8"
        )
        (pdir / "PRD.quality.json").write_text(
            json.dumps({"score": 0.8, "dimensions": {"完整性": 1.0},
                        "evaluator_version": "1.0", "rules": []}), encoding="utf-8"
        )
        (pdir / "engineering.quality.json").write_text(
            json.dumps({"score": 0.9, "dimensions": {"可行性": 1.0},
                        "evaluator_version": "1.0", "rules": []}), encoding="utf-8"
        )
        rec_file = ws / "exec" / "execution_records.json"
        rec_file.parent.mkdir(parents=True, exist_ok=True)
        rec_file.write_text(json.dumps([
            {
                "intent": "run_task", "action": "agent.execute_task", "agent": "backend-1",
                "task": "实现登录功能", "result": "success", "result_id": "EXR-001",
                "timestamp": "2026-08-25T00:00:00+00:00", "error": None,
                "quality": {"score": 0.725, "dimensions": {"validation": 1.0},
                            "evaluator_version": "1.0", "scored_at": "2026-08-25T00:00:00+00:00"},
            }
        ], ensure_ascii=False), encoding="utf-8")
        files = [rec_file, pdir / "PRD.quality.json", pdir / "engineering.quality.json"]
        before = {f: f.stat().st_mtime_ns for f in files}

        text = BOARD.render_quality(ws, "p1")
        after = {f: f.stat().st_mtime_ns for f in files}
        assert before == after  # 只读: 渲染后 mtime 不变
        assert "PRD 质量" in text and "0.80" in text
        assert "工程计划质量" in text and "0.90" in text
        assert "0.72" in text  # 最近执行质量
        assert "只读" in text


# ================================================================== 10. 注册表门禁


class TestRegistryGate:
    def test_board_quality_view_registered(self):
        """/board quality 视图在 BoardCommand 注册可见 (commands.py 源码门禁)。"""
        src = Path(CMD.__file__).read_text(encoding="utf-8")
        assert 'view == "quality"' in src
        assert "render_quality" in src
        assert hasattr(BOARD, "render_quality")

    def test_contract_suite_at_least_10(self):
        """契约套件 ≥10 (防删减)。"""
        src = Path(__file__).read_text(encoding="utf-8")
        count = len([ln for ln in src.splitlines() if ln.startswith("    def test_")])
        assert count >= 10


class TestBoardQualityWeb:
    """S10-118 补: Web board 质量视图接线 (view=quality 路由 + 导航 tab)。"""

    def test_board_nav_has_quality_tab(self):
        nav = BOARD._board_nav("quality", "P-1")
        assert "📊 质量" in nav
        assert "view=quality&project=P-1" in nav
        nav2 = BOARD._board_nav("mainline", "")
        assert "view=quality" in nav2

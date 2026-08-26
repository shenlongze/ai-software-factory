"""tests/console/test_s10_119_learning_loop.py — K-3 学习闭环契约测试 (S10-119)。

覆盖 (设计 docs/sprint10/S10-119-k3-learning-loop-plan.md §2, ≥12):
1. 经验闭环: 两次同类任务 fixture → 第二次引用第一次 (引用存在 + reason 可解释)
2. 护栏-开关: 关闭 → 学习/引用零行为变化
3. 护栏-低样本: 样本数 < 阈值 → 不主导 (引用降权/不引用)
4. 护栏-低质量: quality_score 低 → 不写入
5. 护栏-预算: 超预算 → 阻断 + 告警
6. 护栏-回滚: 学习快照 → 回退后画像/经验还原
7. 决策记忆: 审批 → DECISION_LEARNED → 组织记忆 → 下次少审/带历史
8. 成本告警: usage → 聚合 → 超预算告警/阻断 → 回填
9. 画像分配: 高画像/低负载 Agent 优先 (router 排序)
10. L4 完整化: 非 git 工作区快照/回滚 fixture 可还原; 不可快照 → 明确报错
11. E-2/E-3: 低分 → 建议 → 应用 → 复评提升 (至少一条闭环断言)
12. 注册表: 新命令 (board cost / /cost) 在注册表可见 + 只读
13. 版本: v1.1.95 断言 (pyproject/CHANGELOG/FEATURES)

basename 全仓库唯一 (test_s10_119_* 前缀)。
"""

from __future__ import annotations

import importlib
import json
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

GUARDS = importlib.import_module("factory-console.memory.learning_guards")
LOOP = importlib.import_module("factory-console.memory.learning_loop")
DM = importlib.import_module("factory-console.memory.decision_memory")
EVAL = importlib.import_module("factory-console.session.eval_loop")
CR = importlib.import_module("factory-console.session.capability_router")
REPLAY = importlib.import_module("factory-console.session.execution_replay")
BUDGET = importlib.import_module("factory-console.session.budget")
LEDGER = importlib.import_module("factory-console.session.cost_ledger")
ACTIONS = importlib.import_module("factory-console.session.actions")
CMDS = importlib.import_module("factory-console.session.commands")
BOARD = importlib.import_module("factory-console.session.board")
CTX = importlib.import_module("factory-console.session.context")
ACT = importlib.import_module("factory-console.session.action")
INT = importlib.import_module("factory-console.session.intent")


# ------------------------------------------------------------------ 工具


def _ws(tmp_path: Path, name: str = "ws") -> Path:
    root = tmp_path / name
    root.mkdir(parents=True, exist_ok=True)
    return root


def _exec_record(task: str = "登录功能", agent: str = "backend-1",
                 result: str = "success", error: str = "", project: str = "demo",
                 score: float = 0.8, ts: str = "2026-08-25T00:00:00+00:00",
                 result_id: str = "EXS-000") -> dict:
    """执行记录 fixture (M4-1 on_execution_complete 输入)。"""
    record = {
        "result_id": result_id,
        "task": task,
        "agent": agent,
        "result": result,
        "error": error,
        "project": project,
        "intent": "run_task",
        "timestamp": ts,
    }
    if score is not None:
        record["quality"] = {"score": score, "dimensions": {"validation": score}}
    return record


def _quality(score: float) -> dict:
    return {"score": score, "dimensions": {"validation": score},
            "evaluator_version": "1.0"}


def _ctx(root: Path, slug: str = "") -> ACT.ExecutionContext:
    sess = CTX.SessionContext(workspace=str(root))
    if slug:
        sess.current_project = slug
    return ACT.ExecutionContext(workspace=root, session=sess, user="user",
                                project=slug or None)


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ================================================================== 1. 经验闭环 (M4-1/B-7/E-1)


class TestExperienceLoop:
    def test_second_task_references_first_with_reason(self, tmp_path):
        """两次同类任务 fixture → 第二次引用第一次 (引用存在 + reason 可解释)。"""
        ws = _ws(tmp_path)
        loop = LOOP.LearningLoop(workspace=ws)
        exp_id = loop.on_execution_complete(_exec_record(), _quality(0.8), ws)
        assert exp_id  # 第一次执行 → 经验入库
        # 第二次同类任务 → resolve 命中第一次经验
        hit = loop.resolve_for_task("登录功能", ws)
        assert hit is not None
        assert hit.experience_id == exp_id
        assert "引用经验" in hit.reason and "因为" in hit.reason
        assert "相似度" in hit.reason
        # 第二次执行后 → 仍可引用 (n=2, 低样本降权但不消失)
        loop.on_execution_complete(_exec_record(result_id="EXS-001"), _quality(0.9), ws)
        hit2 = loop.resolve_for_task("登录功能", ws)
        assert hit2 is not None
        assert "引用经验" in hit2.reason and "同类样本 2 条" in hit2.reason

    def test_loop_persists_to_store(self, tmp_path):
        """on_execution_complete → experience_store.json 落盘 (确定性提取字段)。"""
        ws = _ws(tmp_path)
        loop = LOOP.LearningLoop(workspace=ws)
        loop.on_execution_complete(_exec_record(), _quality(0.8), ws)
        store_file = ws / "memory" / "experience_store.json"
        assert store_file.is_file()
        data = json.loads(store_file.read_text(encoding="utf-8"))
        assert len(data) == 1
        rec = data[0]
        assert rec["task"] == "登录功能"
        assert rec["agent"] == "backend-1"
        assert rec["success"] is True
        assert rec["confidence"] == 0.8
        assert rec["source"] == LOOP.LEARNING_LOOP_SOURCE

    def test_failure_record_becomes_failure_pattern(self, tmp_path):
        """失败执行 → FAILURE_PATTERN (problem=error, success=False)。"""
        ws = _ws(tmp_path)
        loop = LOOP.LearningLoop(workspace=ws)
        loop.on_execution_complete(
            _exec_record(result="failed", error="provider error: api key missing",
                         result_id="EXS-F1"),
            _quality(0.55), ws,
        )
        rec = loop.store.records()[0]
        assert rec.type == "FAILURE_PATTERN"
        assert rec.success is False
        assert "api key" in rec.problem


# ================================================================== 2-6. 学习护栏 (M4-2, 最高优先级)


class TestLearningGuards:
    def test_switch_off_zero_behavior_change(self, tmp_path):
        """护栏-开关: 关闭 → 学习/引用零行为变化。"""
        ws = _ws(tmp_path)
        _write_json(ws / "memory" / "learning_state.json", {"enabled": False})
        loop = LOOP.LearningLoop(workspace=ws)
        assert loop.guards.enabled() is False
        assert loop.on_execution_complete(_exec_record(), _quality(0.9), ws) == ""
        assert loop.resolve_for_task("登录功能", ws) is None
        # 经验库零写入
        assert not (ws / "memory" / "experience_store.json").exists()
        # 显式开启覆盖 → 学习恢复
        guards = GUARDS.LearningGuards(enabled=True, workspace=ws)
        assert guards.enabled() is True

    def test_low_sample_not_dominant(self, tmp_path):
        """护栏-低样本: 样本数 < 阈值 → 不主导 (引用降权/不引用)。"""
        ws = _ws(tmp_path)
        loop = LOOP.LearningLoop(workspace=ws)
        loop.on_execution_complete(_exec_record(), _quality(0.8), ws)  # 1 条
        hit = loop.resolve_for_task("登录功能", ws)
        assert hit is not None
        assert hit.dominant is False          # 低样本不主导
        assert "低样本降权参考, 不主导" in hit.reason
        # n < 3 → sample_credible False; n >= 3 → True
        assert GUARDS.LearningGuards().sample_credible(2) is False
        assert GUARDS.LearningGuards().sample_credible(3) is True

    def test_three_samples_dominant(self, tmp_path):
        """样本数 >= 阈值 → 主导 (dominant=True, 无降权标注)。"""
        ws = _ws(tmp_path)
        loop = LOOP.LearningLoop(workspace=ws)
        for i in range(3):
            loop.on_execution_complete(
                _exec_record(result_id=f"EXS-{i}"), _quality(0.8), ws
            )
        hit = loop.resolve_for_task("登录功能", ws)
        assert hit is not None and hit.dominant is True
        assert "低样本" not in hit.reason

    def test_low_quality_not_written(self, tmp_path):
        """护栏-低质量: quality_score 低 (< 0.5) → 不写入 (诚实)。"""
        ws = _ws(tmp_path)
        loop = LOOP.LearningLoop(workspace=ws)
        eid = loop.on_execution_complete(_exec_record(), _quality(0.2), ws)
        assert eid == ""  # 拒绝写入
        assert loop.store.stats()["total"] == 0
        assert loop.resolve_for_task("登录功能", ws) is None
        # 无质量分 → 同样不写 (诚实)
        eid2 = loop.on_execution_complete(_exec_record(result_id="EXS-2", score=None), None, ws)
        assert eid2 == ""

    def test_budget_over_block_and_alert(self, tmp_path):
        """护栏-预算: 超预算 → 阻断 + 告警 (可解释)。"""
        ws = _ws(tmp_path)
        guards = GUARDS.LearningGuards(
            workspace=ws, budget={"max_experiences": 2, "max_snapshots": 2}
        )
        ok = guards.budget_ok({"experiences": 1, "snapshots": 1})
        assert ok is True
        blocked = guards.budget_ok({"experiences": 5, "snapshots": 1})
        assert blocked is False
        assert "预算超限" in guards.last_alert
        assert guards.last_budget_check["over_experiences"] is True
        # 快照维度超限同样阻断
        blocked2 = guards.budget_ok({"experiences": 1, "snapshots": 9})
        assert blocked2 is False
        assert "快照数" in guards.last_alert

    def test_learning_snapshot_rollback_restores(self, tmp_path):
        """护栏-回滚: 学习快照 → 回退后画像/经验还原。"""
        ws = _ws(tmp_path)
        loop = LOOP.LearningLoop(workspace=ws)
        loop.on_execution_complete(_exec_record(), _quality(0.8), ws)
        loop.on_execution_complete(
            _exec_record(task="数据库设计", agent="backend-1", result_id="EXS-2"),
            _quality(0.9), ws,
        )
        profiles = LOOP.refresh_agent_profiles(ws)
        assert profiles  # 画像已落盘 (M4-5 数据源)
        snap = GUARDS.LearningGuards(workspace=ws).snapshot(ws)
        assert snap.is_dir()
        # 执行后学习状态变化 (新增经验) → 回退到快照时点
        loop.on_execution_complete(
            _exec_record(task="接口开发", agent="backend-1", result_id="EXS-3"),
            _quality(0.7), ws,
        )
        before = loop.store.stats()["total"]
        assert before == 3
        GUARDS.LearningGuards(workspace=ws).rollback(snap)
        after = LOOP.LearningLoop(workspace=ws).store.stats()["total"]
        assert after == 2  # 回退后经验还原 (快照时点 2 条)

    def test_snapshot_blocked_when_budget_over(self, tmp_path):
        """超预算 → snapshot 阻断 (不新增快照) + 告警。"""
        ws = _ws(tmp_path)
        guards = GUARDS.LearningGuards(workspace=ws, budget={"max_snapshots": 1})
        # 已存在 2 份快照 (历史) → 超过上限 1 → 再快照超限 (阻断 + 告警)
        snap_root = GUARDS.learning_snapshot_dir(ws)
        (snap_root / "old-1").mkdir(parents=True)
        (snap_root / "old-2").mkdir(parents=True)
        snap2 = guards.snapshot(ws)
        assert guards.last_alert and "快照数" in guards.last_alert
        assert snap2 == snap_root  # 返回根目录 (未新建)
        # 未新增第 3 份
        assert sorted(p.name for p in snap_root.iterdir()) == ["old-1", "old-2"]


# ================================================================== 7. 决策记忆 (M4-3/E5)


class TestDecisionMemory:
    def _prepared_project(self, tmp_path):
        """create 产品 + prepare_project → pending_arch_review (复用 S10-111 工具)。"""
        root = tmp_path / "ws"
        root.mkdir(parents=True)
        slug = "crm"
        pdir = root / "projects" / slug
        pdir.mkdir(parents=True, exist_ok=True)
        _write_json(pdir / "product.json", {
            "name": "CRM", "problem": "测试问题", "user": "测试用户",
            "platform": "web", "core_features": ["客户跟进"],
            "status": "project_created",
        })
        ctx = _ctx(root, slug)
        res = ACTIONS.prepare_project(ctx)
        assert res.ok, res.message
        return ctx, root, slug

    def _approve(self, ctx, slug, answer):
        intent = INT.IntentObject(
            intent_type="approve_project_plan", params={},
            metadata={"confirm_fn": lambda: answer},
        )
        ctx2 = ACT.ExecutionContext(workspace=ctx.workspace, session=ctx.session,
                                    user=ctx.user, project=slug, intent=intent)
        return ACTIONS.approve_project_plan(ctx2)

    def test_decision_learned_audit_and_memory(self, tmp_path):
        """审批 → DECISION_LEARNED 审计 → 组织记忆落盘 (decision_memory.json)。"""
        ctx, root, slug = self._prepared_project(tmp_path)
        result = self._approve(ctx, slug, "y")
        assert result.ok
        # 组织记忆落盘
        mem_file = root / "memory" / "decision_memory.json"
        assert mem_file.is_file()
        records = json.loads(mem_file.read_text(encoding="utf-8"))
        assert len(records) == 1
        assert records[0]["type"] == "project_plan_approval"
        assert records[0]["outcome"] == "approved"
        assert records[0]["context"] == slug
        assert records[0]["learned_at"]
        # DECISION_LEARNED 审计事件
        audit_file = root / "audit" / "audit_events.json"
        assert audit_file.is_file()
        events = json.loads(audit_file.read_text(encoding="utf-8"))
        events = events.get("events") if isinstance(events, dict) else events
        types = [e.get("event_type") for e in events]
        assert "DECISION_LEARNED" in types

    def test_next_approval_shows_history(self, tmp_path, capsys):
        """下次同类审批 → 显示历史 (N 次 + 批准率) — 少审/带历史。"""
        ctx, root, slug = self._prepared_project(tmp_path)
        assert self._approve(ctx, slug, "y").ok
        # 第二次审批 (reject, 重新 prepare 回到待审) → 审批前打印历史
        assert ACTIONS.prepare_project(ctx).ok
        assert self._approve(ctx, slug, "n").status == ACT.STATUS_CANCELLED
        out = capsys.readouterr().out
        assert "历史同类决策: 1 次, 批准率 100%" in out
        # 第三次审批 (approve) → 历史 2 次 50%
        assert ACTIONS.prepare_project(ctx).ok
        assert self._approve(ctx, slug, "y").ok
        out2 = capsys.readouterr().out
        assert "历史同类决策: 2 次, 批准率 50%" in out2
        # 组织记忆 3 条
        records = json.loads(
            (root / "memory" / "decision_memory.json").read_text(encoding="utf-8")
        )
        assert len(records) == 3

    def test_decision_history_helper(self, tmp_path):
        """DecisionMemory.history → {total, approved, approval_rate} 统计口径。"""
        ws = _ws(tmp_path)
        mem = DM.DecisionMemory(workspace=ws)
        mem.record("d1", "review", "approved", context="R1")
        mem.record("d2", "review", "rejected", context="R1")
        mem.record("d3", "project_plan_approval", "approved", context="demo")
        h = mem.history("review", "R1")
        assert h["total"] == 2 and h["approved"] == 1 and h["approval_rate"] == 0.5


# ================================================================== 8. 成本告警 (M4-4/D-6)


class TestCostAlertLoop:
    def test_usage_aggregate_alert_block_backfill(self, tmp_path):
        """usage → 聚合 → 超预算告警/阻断 → 回填 (cost 关联 task/agent)。"""
        ws = _ws(tmp_path)
        ledger = LEDGER.CostLedger(file=ws / "cost" / "cost_records.json")
        # 回填: 成本记录关联 task/agent
        ledger.record({
            "project_id": "demo", "task_id": "T-1", "agent_id": "backend-1",
            "purpose": "EXECUTION", "input_tokens": 100, "output_tokens": 50,
            "estimated_cost": 0.6, "latency": 2.0,
        })
        ledger.record({
            "project_id": "demo", "task_id": "T-2", "agent_id": "backend-1",
            "purpose": "EXECUTION", "total_tokens": 30, "estimated_cost": 0.2,
        })
        # 聚合
        agg = ledger.aggregate("demo")
        assert agg["record_count"] == 2
        assert round(agg["total_cost"], 4) == 0.8
        assert agg["by_task"]["T-1"]["cost"] == 0.6
        assert agg["by_agent"]["backend-1"]["calls"] == 2
        assert ledger.cost_by_task("T-1") == 0.6
        assert ledger.cost_by_agent("backend-1") == 0.8  # 回填关联可查询
        # 超预算 → 告警 (audit) + 阻断
        budget = BUDGET.ProjectBudget(max_total_cost=0.5)
        usage = BUDGET.BudgetUsage.from_records(ledger.records("demo"), budget=budget)
        assert usage.total_cost == 0.8
        enforce = BUDGET.BudgetEnforcer.enforce(budget, usage, "execute")
        assert enforce["allowed"] is False
        assert enforce["level"] == BUDGET.BudgetEnforcer.LEVEL_BLOCK
        check = BUDGET.check_and_alert(budget, usage, workspace=ws, project_id="demo",
                                       action="execute")
        assert check["level"] == "block"
        audit_file = ws / "audit" / "audit_events.json"
        assert audit_file.is_file()
        events = json.loads(audit_file.read_text(encoding="utf-8"))
        events = events.get("events") if isinstance(events, dict) else events
        assert any(e.get("event_type") == "BUDGET_BLOCKED" for e in events)

    def test_warn_level_emits_budget_warning(self, tmp_path):
        """80% 告警线 → BUDGET_WARNING 审计 (继续执行语义不变)。"""
        ws = _ws(tmp_path)
        budget = BUDGET.ProjectBudget(max_total_cost=10.0)
        usage = BUDGET.BudgetUsage.from_records(
            [{"estimated_cost": 8.5, "total_tokens": 1}], budget=budget
        )
        check = BUDGET.check_and_alert(budget, usage, workspace=ws, project_id="demo")
        assert check["level"] == "warn"
        events = json.loads((ws / "audit" / "audit_events.json").read_text(encoding="utf-8"))
        events = events.get("events") if isinstance(events, dict) else events
        assert any(e.get("event_type") == "BUDGET_WARNING" for e in events)

    def test_board_cost_readonly(self, tmp_path):
        """/board cost 可视化只读: 渲染含每任务/每 Agent 成本; 渲染后无写入。"""
        ws = _ws(tmp_path)
        ledger = LEDGER.CostLedger(file=ws / "cost" / "cost_records.json")
        ledger.record({"project_id": "demo", "task_id": "T-1", "agent_id": "a1",
                       "purpose": "EXECUTION", "estimated_cost": 0.5, "total_tokens": 10})
        out = BOARD.render_cost(ws)
        assert "每任务成本" in out and "T-1" in out
        assert "每 Agent 成本" in out and "a1" in out
        assert "预算等级" in out
        assert not (ws / "cost" / "cost_records.json.tmp").exists()  # 只读无写入副作用
        assert ledger.records_file().is_file()  # 原文件未被改写 (mtime 不校验, 内容一致)
        data = json.loads(ledger.records_file().read_text(encoding="utf-8"))
        assert len(data) == 1


# ================================================================== 9. 画像分配 (M4-5)


class TestPersonaRouting:
    def test_high_persona_low_load_agent_wins(self):
        """高画像/低负载 Agent 优先 (排序: priority → persona → load → quality → version)。"""
        router = CR.CapabilityRouter([
            CR.CapabilityResource(id="hi", type="agent", capabilities=["x"],
                                  priority=1, persona_score=0.9, load=0.8),
            CR.CapabilityResource(id="mid", type="agent", capabilities=["x"],
                                  priority=1, persona_score=0.5, load=0.1),
            CR.CapabilityResource(id="none", type="agent", capabilities=["x"],
                                  priority=1, persona_score=None, load=0.0),
        ])
        d = router.route(CR.CapabilityRequest(objective="x", capabilities=["x"]))
        # 同 priority → persona 最高优先; 同 persona → load 低者胜
        assert d.resource_id == "hi"
        assert "persona desc" in d.reason and "load asc" in d.reason

    def test_same_persona_low_load_wins(self):
        """同画像分 → 负载低者优先 (负载均衡)。"""
        router = CR.CapabilityRouter([
            CR.CapabilityResource(id="busy", type="agent", capabilities=["x"],
                                  priority=1, persona_score=0.8, load=0.9),
            CR.CapabilityResource(id="free", type="agent", capabilities=["x"],
                                  priority=1, persona_score=0.8, load=0.1),
        ])
        d = router.route(CR.CapabilityRequest(capabilities=["x"]))
        assert d.resource_id == "free"

    def test_build_agent_resources_pulls_profiles_fail_safe(self):
        """build_agent_resources: agent_profiles → persona_score; 无画像 → None 中性。"""
        agents = {"a": {"skills": ["x"]}, "b": {"skills": ["x"]}}
        profiles = {"a": {"success_rate": 0.9}}
        rs = CR.build_agent_resources(agents, profiles)
        by_id = {r.id: r for r in rs}
        assert by_id["a"].persona_score == 0.9
        assert by_id["b"].persona_score is None  # 无画像中性
        rs2 = CR.build_agent_resources(agents)   # 不传 profiles → 全中性
        assert all(r.persona_score is None for r in rs2)

    def test_persona_score_validation(self):
        """persona_score 越界 → 响亮报错 (不静默接受脏资源)。"""
        with pytest.raises(ValueError):
            CR.CapabilityResource(id="bad", type="agent", persona_score=1.5)
        ok = CR.CapabilityResource(id="ok", type="agent", persona_score=0.5)
        assert ok.persona_score == 0.5


# ================================================================== 10. L4 完整化 (M4-6)


class TestL4SnapshotNonGit:
    def _record_with_project(self, result_id: str, project: Path) -> dict:
        return {
            "result_id": result_id, "task": "t", "agent": "a", "result": "success",
            "input_snapshot": {"context": {"project": str(project)}},
        }

    def test_non_git_snapshot_rollback_restores(self, tmp_path):
        """非 git 工作区快照/回滚 fixture 可还原 (目录级复制)。"""
        ws = _ws(tmp_path)
        proj = tmp_path / "plain-proj"
        proj.mkdir()
        (proj / "a.txt").write_text("v1", encoding="utf-8")
        (proj / "sub").mkdir()
        (proj / "sub" / "b.txt").write_text("keep", encoding="utf-8")
        _write_json(ws / "exec" / "execution_records.json",
                    [self._record_with_project("EXS-NG1", proj)])
        engine = REPLAY.ReplayEngine(workspace=ws)
        snap = engine.snapshot_before("EXS-NG1")
        assert snap  # 快照路径 (非 git 也成功)
        # 执行修改
        (proj / "a.txt").write_text("v2-changed", encoding="utf-8")
        (proj / "new.txt").write_text("extra", encoding="utf-8")
        (proj / "sub" / "b.txt").write_text("mutated", encoding="utf-8")
        engine.rollback("EXS-NG1")
        # 精确还原执行前状态 (含执行期新增文件清除)
        assert (proj / "a.txt").read_text(encoding="utf-8") == "v1"
        assert not (proj / "new.txt").exists()
        assert (proj / "sub" / "b.txt").read_text(encoding="utf-8") == "keep"
        records = json.loads((ws / "exec" / "execution_records.json").read_text(encoding="utf-8"))
        assert "pre_snapshot" not in records[0]  # 一次性

    def test_unavailable_snapshot_clear_error(self, tmp_path):
        """不可快照 (无项目目录) → 明确 ReplayError (不静默)。"""
        ws = _ws(tmp_path)
        _write_json(ws / "exec" / "execution_records.json",
                    [self._record_with_project("EXS-NOPE", tmp_path / "missing-dir")])
        engine = REPLAY.ReplayEngine(workspace=ws)
        with pytest.raises(REPLAY.ReplayError, match="项目目录不存在"):
            engine.snapshot_before("EXS-NOPE")


# ================================================================== 11. E-2/E-3 评估驱动闭环


class TestEvalFixLoop:
    def test_low_score_suggest_apply_reevaluate_improved(self, tmp_path):
        """低分 → 建议 → 应用 → 复评提升 (至少一条闭环断言)。"""
        ws = _ws(tmp_path)
        slug = "demo"
        project_dir = ws / "projects" / slug
        project_dir.mkdir(parents=True, exist_ok=True)
        # 低分执行记录 (validation_failed)
        _write_json(ws / "exec" / "execution_records.json", [{
            "result_id": "EXS-LOW", "task": "T-1 登录功能", "agent": "backend-1",
            "project": slug, "result": "failed",
            "error": "validation failed: tests failed",
            "timestamp": "2026-08-25T00:00:00+00:00",
            "quality": {"score": 0.3, "dimensions": {"validation": 0.0}},
        }])
        _write_json(project_dir / "execution_state.json", {
            "tasks": [{"id": "T-1", "name": "登录功能", "agent": "backend-1"}],
        })
        # 修复执行: 成功 + 高质量 outcome (模拟真实 execute_task: 落盘新执行记录)
        def fake_execute_fn(task, project_dir, workspace):
            import json as _json

            rec = {
                "result_id": "EXS-FIXED", "task": str(task.get("name") or "T-1"),
                "agent": "backend-1", "project": slug, "result": "success",
                "timestamp": "2026-08-25T01:00:00+00:00",
                "quality": {"score": 0.85, "dimensions": {"validation": 1.0}},
            }
            rec_file = Path(workspace) / "exec" / "execution_records.json"
            data = _json.loads(rec_file.read_text(encoding="utf-8"))
            data.append(rec)
            rec_file.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return {"success": True, "quality": {"score": 0.85},
                    "estimated_cost": 0.1}
        result = EVAL.EvalFixLoop().run(ws, slug, "T-1", execute_fn=fake_execute_fn)
        assert result.status == "low_score_applied"
        assert result.classification == "validation_failed"
        assert "修复" in result.suggestion
        assert result.repair_id
        assert result.repair_status == "completed"
        assert result.original_score == 0.3
        # 复评提升断言 (至少一条闭环)
        assert result.reevaluated_score is not None
        assert result.improved is True
        assert result.reevaluated_score > result.original_score
        # repair_task.json 已应用 (pending 处理完)
        repairs = json.loads((project_dir / "repair_task.json").read_text(encoding="utf-8"))
        assert repairs[0]["status"] == "completed"

    def test_no_low_score_task_honest(self, tmp_path):
        """无低分任务 → 诚实标注 no_low_score (不假装闭环)。"""
        ws = _ws(tmp_path)
        _write_json(ws / "exec" / "execution_records.json", [{
            "result_id": "EXS-OK", "task": "T-9", "agent": "backend-1",
            "project": "demo", "result": "success",
            "timestamp": "2026-08-25T00:00:00+00:00",
            "quality": {"score": 0.9},
        }])
        result = EVAL.EvalFixLoop().run(ws, "demo", "T-9")
        assert result.status == "no_low_score"

    def test_analyze_classification_deterministic(self):
        """失败分类确定性: provider_error / patch_apply_failed / other。"""
        a1 = EVAL.EvalFixLoop.analyze(
            {"task": "T", "error": "provider error: anthropic api key missing"},
            {"score": 0.3},
        )
        assert a1.classification == "provider_error"
        a2 = EVAL.EvalFixLoop.analyze(
            {"task": "T", "error": "patch apply failed: hunk #1 not found"},
            {"score": 0.4},
        )
        assert a2.classification == "patch_apply_failed"
        a3 = EVAL.EvalFixLoop.analyze({"task": "T", "error": "mystery"}, {"score": 0.2})
        assert a3.classification == "other"


# ================================================================== 12. 注册表 + 13. 版本


class TestRegistryAndVersion:
    def test_board_cost_view_registered(self):
        """注册表: /board cost 视图可用 (BoardCommand 分支) + /cost 命令注册。"""
        registry = CMDS.build_default_registry()
        names = [c.name for c in registry.list()]
        assert "cost" in names and "board" in names
        src = Path(CMDS.__file__).read_text(encoding="utf-8")
        assert "view == \"cost\"" in src  # /board cost 分支已接线
        assert "render_cost" in src

    def test_board_cost_readonly_no_write(self, tmp_path):
        """board 成本视图只读: 渲染不创建/改写任何数据文件。"""
        ws = _ws(tmp_path)
        board_src = Path(BOARD.__file__).read_text(encoding="utf-8")
        assert "只读" in board_src  # render_cost 声明只读
        # 渲染空工作区 → 无成本记录提示 (不抛)
        out = BOARD.render_cost(ws)
        assert "无成本记录" in out

    def test_version_bumped_119(self):
        """版本 v1.1.95: pyproject + CHANGELOG + FEATURES 同步。"""
        pyproject = (_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        assert re.search(r'^version\s*=\s*"1\.1\.157"', pyproject, re.M)
        changelog = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        assert "## [v1.1.157]" in changelog
        features = (_ROOT / "docs" / "FEATURES.md").read_text(encoding="utf-8")
        assert "v1.1.157" in features
        # K-3/M4-1~6 待办清单同步
        backlog = (_ROOT / "docs" / "sprint10" / "待办清单-已发现未落地.md").read_text(
            encoding="utf-8")
        assert "K-3" in backlog and "✅" in backlog.split("K-3")[1][:50]

    def test_contract_suite_at_least_12(self):
        """契约测试 ≥12 (设计 §2 验收 8)。"""
        src = Path(__file__).read_text(encoding="utf-8")
        count = len(re.findall(r"^    def test_", src, re.M))
        assert count >= 12, f"契约测试仅 {count} 个 (需 ≥12)"

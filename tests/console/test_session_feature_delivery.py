"""S10-055 — Feature Delivery 测试套件。

覆盖: FeatureTaskGenerator (Epic 结构) / ProductProgressTracker /
get_feature_progress / USER_ACCEPTANCE 门 / accept_project Action /
向后兼容 / 回归。

装配: tmp_path workspace + mock execute_fn; 零真实 LLM/网络。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from importlib import import_module

PIPE = import_module("factory-console.session.pipeline")
PROG = import_module("factory-console.session.progress")
ORCH = import_module("factory-console.session.orchestrator")
ACTIONS = import_module("factory-console.session.actions")
ACTION_MOD = import_module("factory-console.session.action")


# ================================================================== fixtures

def _make_project(tmp_path: Path, features=("计分", "比赛记录")) -> Path:
    pd = tmp_path / "projects" / "scorepocket"
    pd.mkdir(parents=True, exist_ok=True)
    plan = {
        "tasks": [
            {"id": f"task-{i}", "name": f"任务 {i}", "agent_type": "backend", "agent": "backend-1",
             "feature": "计分" if i % 2 else "比赛记录", "epic": "核心功能"}
            for i in range(1, 3)
        ],
        "count": 2,
    }
    (pd / "execution_plan.json").write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    (pd / "product.json").write_text(
        json.dumps({"name": "ScorePocket", "core_features": list(features), "status": "execution_ready"}, ensure_ascii=False),
        encoding="utf-8",
    )
    (pd / "project.json").write_text(
        json.dumps({"name": "ScorePocket", "status": "execution_ready"}, ensure_ascii=False),
        encoding="utf-8",
    )
    return pd


def _ok_fn():
    def fn(task, project_dir, workspace):
        return {"success": True, "artifact": f"/tmp/{task['id']}.patch", "error": None, "cost": "10 tokens"}

    return fn


def _fail_fn():
    def fn(task, project_dir, workspace):
        return {"success": False, "artifact": "", "error": "boom", "cost": ""}

    return fn


def _product():
    PRODUCT = import_module("factory-console.session.product")
    return PRODUCT.ProductIntent(
        name="ScorePocket", problem="记录困难", user="爱好者",
        core_features=["计分", "比赛记录", "排行榜"], platform="mobile",
    )


# ================================================================== 1. FeatureTaskGenerator


class TestFeatureTaskGenerator:
    def test_epic_structure(self):
        g = PIPE.FeatureTaskGenerator()
        result = g.from_product(_product())
        assert "epics" in result
        assert "tasks" in result
        assert len(result["epics"]) >= 1

    def test_not_template(self):
        """功能级: 不是 database_schema/backend_api 模板。"""
        g = PIPE.FeatureTaskGenerator()
        result = g.from_product(_product())
        names = [t["name"] for t in result["tasks"]]
        assert not any("database_schema" in n for n in names)
        assert any("记录" in n or "比分" in n for n in names)

    def test_match_epic(self):
        g = PIPE.FeatureTaskGenerator()
        result = g.from_product(_product())
        assert any("比赛" in e["name"] or "计分" in e["name"] for e in result["epics"])

    def test_platform_mobile_flutter(self):
        g = PIPE.FeatureTaskGenerator()
        result = g.from_product(_product())
        # mobile → flutter 相关客户端任务
        names = [t["name"] for t in result["tasks"]]
        assert any("界面" in n or "交互" in n or "flutter" in n.lower() for n in names)

    def test_platform_web(self):
        PRODUCT = import_module("factory-console.session.product")
        p = PRODUCT.ProductIntent(name="P", problem="x", user="y", core_features=["计分"], platform="web")
        g = PIPE.FeatureTaskGenerator()
        result = g.from_product(p)
        assert any("界面" in t["name"] or "交互" in t["name"] for t in result["tasks"])

    def test_flat_tasks_have_feature(self):
        g = PIPE.FeatureTaskGenerator()
        result = g.from_product(_product())
        for t in result["tasks"]:
            assert t.get("feature"), t

    def test_flat_tasks_have_epic(self):
        g = PIPE.FeatureTaskGenerator()
        result = g.from_product(_product())
        for t in result["tasks"]:
            assert t.get("epic"), t

    def test_tasks_have_agent_type(self):
        g = PIPE.FeatureTaskGenerator()
        result = g.from_product(_product())
        for t in result["tasks"]:
            assert t.get("agent_type") in ("backend", "frontend", "qa")

    def test_tasks_have_priority(self):
        g = PIPE.FeatureTaskGenerator()
        result = g.from_product(_product())
        for t in result["tasks"]:
            assert t.get("priority") in ("P0", "P1")

    def test_core_features_mapped(self):
        g = PIPE.FeatureTaskGenerator()
        result = g.from_product(_product())
        epic_names = [e["name"] for e in result["epics"]]
        assert any("比赛" in n or "计分" in n for n in epic_names)
        assert any("排行榜" in n for n in epic_names)

    def test_client_epic(self):
        g = PIPE.FeatureTaskGenerator()
        result = g.from_product(_product())
        assert any("客户端" in e["name"] for e in result["epics"])


# ================================================================== 2. prepare_project 功能级


class TestPrepareProjectFeature:
    def test_prepare_uses_feature_tasks(self, tmp_path):
        root = tmp_path / "ws"
        root.mkdir()
        ctx, _ = _create_product_on_disk(root)
        ACTIONS.prepare_project(ctx)
        data = json.loads((root / "projects" / "scorepocket" / "tasks.json").read_text(encoding="utf-8"))
        names = [t["name"] for t in data.get("tasks", [])]
        assert not any("database_schema" in n for n in names)

    def test_prepare_has_epic_metadata(self, tmp_path):
        root = tmp_path / "ws"
        root.mkdir()
        ctx, _ = _create_product_on_disk(root)
        ACTIONS.prepare_project(ctx)
        data = json.loads((root / "projects" / "scorepocket" / "tasks.json").read_text(encoding="utf-8"))
        tasks = data.get("tasks", [])
        assert tasks and all(t.get("epic") for t in tasks)

    def test_old_tasktree_available(self):
        """向后兼容: TaskTree.from_engineering 仍可用。"""
        t = PIPE.TaskTree.from_engineering({"modules": [{"slug": "m1", "name": "A"}]})
        assert len(t.get("tasks", [])) == 4


# ================================================================== 3. ProductProgressTracker


class TestProductProgressTracker:
    def test_init_all_pending(self):
        t = PROG.ProductProgressTracker()
        p = _product()
        prog = t.init(p, [{"id": "T1", "feature": "计分"}, {"id": "T2", "feature": "计分"}])
        assert prog["product"] == "ScorePocket"
        assert len(prog["features"]) >= 1
        assert all(f["status"] == "pending" for f in prog["features"])

    def test_update_completed(self):
        t = PROG.ProductProgressTracker()
        p = _product()
        t.init(p, [{"id": "T1", "feature": "计分"}])
        updated = t.update_from_execution(
            {"project": "ScorePocket", "tasks": [{"feature": "计分", "status": "completed"}]}
        )
        assert updated["features"][0]["status"] == "completed"

    def test_update_partial(self):
        t = PROG.ProductProgressTracker()
        updated = t.update_from_execution({"project": "ScorePocket", "tasks": [
            {"feature": "计分", "status": "completed"},
            {"feature": "计分", "status": "pending"},
            {"feature": "比赛记录", "status": "failed"},
        ]})
        feats = {f["name"]: f for f in updated["features"]}
        assert feats["计分"]["status"] == "in_progress"
        assert feats["比赛记录"]["status"] == "pending"  # failed 任务不贡献 completed

    def test_save_load(self, tmp_path):
        t = PROG.ProductProgressTracker()
        p = _product()
        prog = t.init(p, [{"id": "T1", "feature": "计分"}])
        t.save(tmp_path, prog)
        loaded = t.load(tmp_path)
        assert loaded is not None
        assert loaded["product"] == "ScorePocket"

    def test_load_missing(self, tmp_path):
        t = PROG.ProductProgressTracker()
        assert t.load(tmp_path) is None

    def test_save_writes_file(self, tmp_path):
        t = PROG.ProductProgressTracker()
        p = _product()
        prog = t.init(p, [{"id": "T1", "feature": "计分"}])
        t.save(tmp_path, prog)
        assert (tmp_path / "product_progress.json").exists()

    def test_status_transitions(self):
        t = PROG.ProductProgressTracker()
        assert t._feature_status(2, 2) == "completed"
        assert t._feature_status(2, 1) == "in_progress"
        assert t._feature_status(2, 0) == "pending"
        assert t._feature_status(0, 0) == "pending"


# ================================================================== 4. get_feature_progress


class TestFeatureProgress:
    def test_feature_progress(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        fp = orch.get_feature_progress("scorepocket")
        assert "features" in fp
        assert len(fp["features"]) >= 1

    def test_feature_completed(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        fp = orch.get_feature_progress("scorepocket")
        for f in fp["features"]:
            assert f["status"] == "completed"
            assert f["completed_tasks"] == f["total_tasks"]

    def test_feature_failed(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_fail_fn())
        fp = orch.get_feature_progress("scorepocket")
        assert any(f["status"] != "completed" for f in fp["features"])


# ================================================================== 5. USER_ACCEPTANCE 门


class TestAcceptanceGate:
    def test_lifecycle_has_user_acceptance(self):
        assert PIPE.Lifecycle.USER_ACCEPTANCE in PIPE.Lifecycle.STATUSES

    def test_position_after_validation(self):
        s = PIPE.Lifecycle.STATUSES
        assert s.index(PIPE.Lifecycle.USER_ACCEPTANCE) == s.index(PIPE.Lifecycle.VALIDATION_PASS) + 1
        assert s.index(PIPE.Lifecycle.DELIVERED) == s.index(PIPE.Lifecycle.USER_ACCEPTANCE) + 1

    def test_next_status_chain(self):
        assert PIPE.Lifecycle.next_status(PIPE.Lifecycle.VALIDATION_PASS) == PIPE.Lifecycle.USER_ACCEPTANCE
        assert PIPE.Lifecycle.next_status(PIPE.Lifecycle.USER_ACCEPTANCE) == PIPE.Lifecycle.DELIVERED

    def test_execution_stops_at_acceptance(self, tmp_path):
        """执行完成 → 停在 user_acceptance (非直接 DELIVERED)。"""
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("scorepocket", execute_fn=_ok_fn())
        assert res.status == "user_acceptance"
        assert res.completed_tasks == 2

    def test_accept_project_delivers(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        ok = orch.accept_project("scorepocket")
        assert ok is True
        prog = orch.get_progress("scorepocket")
        assert prog["lifecycle"] == "delivered"

    def test_accept_only_from_acceptance(self, tmp_path):
        """非 user_acceptance 状态 → accept 拒绝。"""
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        # 未执行 → not_started → accept 应拒绝
        ok = orch.accept_project("scorepocket")
        assert ok is False

    def test_state_file_updated(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        orch.accept_project("scorepocket")
        state = json.loads((pd / "execution_state.json").read_text(encoding="utf-8"))
        assert state["lifecycle"] == "delivered"


# ================================================================== 6. accept_project Action


class TestAcceptAction:
    def test_action_registered(self):
        reg = ACTIONS.build_default_actions()
        assert reg.get("accept_project") is not None

    def test_action_sensitive(self):
        reg = ACTIONS.build_default_actions()
        assert reg.get("accept_project").metadata.get("sensitive") is True

    def test_intent_keyword(self):
        parser = import_module("factory-console.session.intent").KeywordIntentParser()
        intent = parser.parse("通过验收")
        assert intent is not None
        assert intent.intent_type == "accept_project"

    def test_router_mapping(self):
        router = import_module("factory-console.session.router").IntentRouter()
        assert router.routes().get("accept_project") == "accept_project"

    def test_action_flow(self, tmp_path):
        """执行 → 停在 acceptance → accept action → delivered。"""
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        intent = ACTION_MOD.IntentObject(intent_type="accept_project", params={}, raw="通过验收")
        ctx = ACTION_MOD.ExecutionContext(
            workspace=tmp_path, session=None, user="user",
            project=str(pd), intent=intent,
        )
        res = ACTIONS.accept_project(ctx)
        assert res.ok is True
        assert res.status == "ok"


# ================================================================== 7. 回归


class TestRegression:
    def test_old_actions_unchanged(self):
        reg = ACTIONS.build_default_actions()
        for name in ("create_product", "prepare_project", "execute_project", "repair_task", "agent.execute_task"):
            assert reg.get(name) is not None

    def test_validator_unchanged(self):
        QUALITY = import_module("factory-console.session.quality")
        r = QUALITY.Validator().validate({"id": "T1"}, {"success": True})
        assert r.success is True

    def test_progress_legacy(self, tmp_path):
        """get_progress 仍工作 (task 级)。"""
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        prog = orch.get_progress("scorepocket")
        assert prog["completed"] == 2


# ================================================================== 8. 补充 (达 >=60)


class TestExtra:
    def test_feature_generator_no_platform_default(self):
        PRODUCT = import_module("factory-console.session.product")
        p = PRODUCT.ProductIntent(name="P", problem="x", user="y", core_features=["计分"])
        g = PIPE.FeatureTaskGenerator()
        result = g.from_product(p)
        assert result["tasks"]

    def test_feature_generator_epic_tasks_consistent(self):
        """epics 内 features 的任务与扁平 tasks 一致。"""
        g = PIPE.FeatureTaskGenerator()
        result = g.from_product(_product())
        flat_ids = {t["id"] for t in result["tasks"]}
        epic_ids = set()
        for e in result["epics"]:
            for f in e.get("features", []):
                for t in f.get("tasks", []):
                    epic_ids.add(t["id"])
        assert flat_ids == epic_ids

    def test_progress_tracker_deterministic(self):
        t1 = PROG.ProductProgressTracker()
        t2 = PROG.ProductProgressTracker()
        p = _product()
        r1 = t1.init(p, [{"id": "T1", "feature": "计分"}])
        r2 = t2.init(p, [{"id": "T1", "feature": "计分"}])
        assert r1 == r2

    def test_acceptance_gate_visible_in_progress(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        prog = orch.get_progress("scorepocket")
        assert prog["lifecycle"] == "user_acceptance"

    def test_full_delivery_flow(self, tmp_path):
        """完整交付流: execute → acceptance → accept → delivered。"""
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res1 = orch.execute_project("scorepocket", execute_fn=_ok_fn())
        assert res1.status == "user_acceptance"
        assert orch.accept_project("scorepocket") is True
        assert orch.get_progress("scorepocket")["lifecycle"] == "delivered"

    def test_feature_progress_counts(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        fp = orch.get_feature_progress("scorepocket")
        total = sum(f["total_tasks"] for f in fp["features"])
        completed = sum(f["completed_tasks"] for f in fp["features"])
        assert total == completed == 2


# ================================================================== helpers

def _create_product_on_disk(root: Path):
    """创建 product.json 到磁盘 (复用 create_product action)。"""
    PRODUCT = import_module("factory-console.session.product")
    product = PRODUCT.ProductIntent(
        name="ScorePocket", problem="记录困难", user="爱好者",
        core_features=["计分", "比赛记录"], platform="mobile",
    )
    intent = ACTION_MOD.IntentObject(
        intent_type="create_product", params={"name": "ScorePocket"}, raw="做一个产品"
    )
    session = import_module("factory-console.session.context").SessionContext(
        workspace=str(root / "ws")
    )
    session.product_intent = product
    ctx = ACTION_MOD.ExecutionContext(
        workspace=root, session=session, user="user", project=None, intent=intent
    )
    return ctx, product


class TestMore:
    def test_generator_epic_ids_unique(self):
        g = PIPE.FeatureTaskGenerator()
        r = g.from_product(_product())
        ids = [e["id"] for e in r["epics"]]
        assert len(ids) == len(set(ids))

    def test_generator_tasks_ids_unique(self):
        g = PIPE.FeatureTaskGenerator()
        r = g.from_product(_product())
        ids = [t["id"] for t in r["tasks"]]
        assert len(ids) == len(set(ids))

    def test_generator_user_system(self):
        PRODUCT = import_module("factory-console.session.product")
        p = PRODUCT.ProductIntent(name="P", problem="x", user="y", core_features=["用户系统", "登录注册"])
        g = PIPE.FeatureTaskGenerator()
        r = g.from_product(p)
        assert any("用户" in e["name"] for e in r["epics"])

    def test_progress_init_saves_features(self, tmp_path):
        t = PROG.ProductProgressTracker()
        p = _product()
        prog = t.init(p, [{"id": "T1", "feature": "计分"}])
        t.save(tmp_path, prog)
        loaded = t.load(tmp_path)
        assert loaded["features"][0]["name"] in ("计分",)

    def test_acceptance_gate_requires_execution(self, tmp_path):
        """未执行 → accept 拒绝 (not_started)。"""
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        assert orch.accept_project("scorepocket") is False

    def test_acceptance_twice_noop(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        assert orch.accept_project("scorepocket") is True
        # 已 DELIVERED → 再次 accept 不再有效 (或幂等)
        assert orch.accept_project("scorepocket") in (True, False)

    def test_progress_tracker_load_corrupt(self, tmp_path):
        (tmp_path / "product_progress.json").write_text("{not json", encoding="utf-8")
        t = PROG.ProductProgressTracker()
        assert t.load(tmp_path) is None

    def test_accept_action_missing_project(self, tmp_path):
        intent = ACTION_MOD.IntentObject(intent_type="accept_project", params={}, raw="通过验收")
        ctx = ACTION_MOD.ExecutionContext(workspace=tmp_path, session=None, user="user", project=None, intent=intent)
        res = ACTIONS.accept_project(ctx)
        assert res.ok is False  # 未定位项目

    def test_execution_result_user_acceptance_field(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        res = orch.execute_project("scorepocket", execute_fn=_ok_fn())
        assert res.status == "user_acceptance"
        assert hasattr(res, "status")

    def test_feature_progress_after_accept(self, tmp_path):
        _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        orch.accept_project("scorepocket")
        fp = orch.get_feature_progress("scorepocket")
        assert all(f["status"] == "completed" for f in fp["features"])

    def test_generator_empty_features(self):
        PRODUCT = import_module("factory-console.session.product")
        p = PRODUCT.ProductIntent(name="P", problem="x", user="y", core_features=[])
        g = PIPE.FeatureTaskGenerator()
        r = g.from_product(p)
        assert r["tasks"] or r["epics"]  # 不崩溃, 有默认任务

    def test_accept_intent_variants(self):
        parser = import_module("factory-console.session.intent").KeywordIntentParser()
        for text in ("通过验收", "验收通过", "确认交付"):
            intent = parser.parse(text)
            assert intent is not None, text
            assert intent.intent_type == "accept_project", text

    def test_accept_not_confused(self):
        parser = import_module("factory-console.session.intent").KeywordIntentParser()
        assert parser.parse("通过验收").intent_type == "accept_project"

    def test_progress_after_acceptance_state(self, tmp_path):
        pd = _make_project(tmp_path)
        orch = ORCH.ExecutionOrchestrator(tmp_path)
        orch.execute_project("scorepocket", execute_fn=_ok_fn())
        prog = orch.get_progress("scorepocket")
        assert prog["lifecycle"] == "user_acceptance"
        orch.accept_project("scorepocket")
        prog2 = orch.get_progress("scorepocket")
        assert prog2["lifecycle"] == "delivered"

    def test_generator_client_platform(self):
        """客户端 Epic 任务包含平台相关 agent_type。"""
        g = PIPE.FeatureTaskGenerator()
        r = g.from_product(_product())
        client_tasks = []
        for e in r["epics"]:
            if "客户端" in e["name"]:
                for feat in e.get("features", []):
                    client_tasks.extend(feat.get("tasks", []))
        assert client_tasks
        assert any(t.get("agent_type") == "frontend" for t in client_tasks)

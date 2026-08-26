"""tests/console/test_s10_125_c2_contract_wiring.py — C-2 产出物契约引擎接线 (S10-125)。

覆盖: 全部引擎写点改走 set_artifact 后的接线断言 (Manifest + 版本 + 追溯 + 历史):
- actions.create_product (product.json) / generate_prd (PRD.md + product.json) /
  prepare_project (PRD/engineering/tasks/execution_plan/product) / rename_project
- orchestrator._save_state (execution_state) / _insert_tasks (tasks) / _bump_plan
  (execution_plan)
- change_control.apply (PRD v2 追加场景 + tasks/plan/execution_plan 合并)
- 写后 manifest 条目 + 版本+1 + producer/trace_id (K-4 trace 上下文) +
  history 归档 (第二次写) + 内容一致
- 失败安全: set_artifact 异常 (mock) → 引擎不中断 (不写直写回退)
- 直写归零: 源码断言 4 个改造文件无残留直写标准文件名

设计: docs/sprint10/S10-125-c2-plan.md §0/§1/§3
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

_ac = importlib.import_module("factory-console.artifact_contract")
_act = importlib.import_module("factory-console.session.action")
_actions = importlib.import_module("factory-console.session.actions")
_ctx = importlib.import_module("factory-console.session.context")
_cc = importlib.import_module("factory-console.session.change_control")
_orch = importlib.import_module("factory-console.session.orchestrator")
_pipe = importlib.import_module("factory-console.session.pipeline")
_prod = importlib.import_module("factory-console.session.product")
_replan = importlib.import_module("factory-console.session.replanning")
_trace = importlib.import_module("factory-console.audit.trace_context")


# ------------------------------------------------------------------ 工具


def _exec_ctx(root: Path, **kw) -> _act.ExecutionContext:
    sess = _ctx.SessionContext(workspace=str(root))
    return _act.ExecutionContext(
        workspace=root, session=sess, user="user", **kw
    )


def _complete_product(**kw) -> _prod.ProductIntent:
    data = dict(
        name="ScorePocket",
        problem="台球比赛计分麻烦",
        user="台球爱好者",
        platform="mobile",
        core_features=["计分", "比赛记录", "排行榜"],
        raw="我想开发一个台球计分APP",
    )
    data.update(kw)
    return _prod.ProductIntent(**data)


class FakeOrgCli:
    """org 注册桩 (monkeypatch actions._load_org_cli) — 同既有测试模式。"""

    def __init__(self, *, ok: bool = True, project: dict | None = None,
                 error: str | None = None) -> None:
        self.calls: list = []
        self.ok = ok
        self.project = project
        self.error = error

    def cmd_project_register(self, root, args):
        self.calls.append((root, args))
        if not self.ok:
            return {"ok": False, "error": self.error or "注册失败", "exit_code": 1}
        return {
            "ok": True,
            "project": self.project
            or {"id": "p1", "name": args.name, "slug": "scorepocket"},
            "analysis_ref": None,
            "baseline_ref": None,
            "snapshot_ref": None,
            "exit_code": 0,
        }


@pytest.fixture
def fake_org(monkeypatch):
    org = FakeOrgCli()
    monkeypatch.setattr(_actions, "_load_org_cli", lambda: org)
    return org


def _create_product(root: Path) -> _act.ExecutionContext:
    ctx = _exec_ctx(root)
    ctx.session.product_intent = _complete_product()
    result = _actions.create_product(ctx)
    assert result.ok, result.message
    return ctx


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _make_project_assets(root: Path, slug: str = "scorepocket") -> Path:
    """构造 orchestrator 固定资产 (execution_plan/project/product/tasks)。"""
    pdir = root / "projects" / slug
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "execution_plan.json").write_text(
        json.dumps({"tasks": [{"id": "T1", "name": "A"}], "count": 1},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    (pdir / "project.json").write_text(
        json.dumps({"name": "ScorePocket", "status": "execution_ready"},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    (pdir / "product.json").write_text(
        json.dumps({"name": "ScorePocket", "status": "execution_ready"},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    (pdir / "tasks.json").write_text(
        json.dumps({"tasks": [{"id": "T1", "name": "A"}], "count": 1},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    return pdir


# ================================================================== actions.py 写点


class TestActionsContractWiring:
    """写点 1/2/3/12 + 补全 (prepare_project 四件套 / rename_project)。"""

    def test_create_product_contract_manifest(self, fake_org, tmp_path):
        """写点 1: create_product → product.json 经 set_artifact (producer/trace_id)。"""
        root = tmp_path / "ws"
        root.mkdir()
        ctx = _exec_ctx(root)
        ctx.session.product_intent = _complete_product()
        with _trace.trace_context("trace-cp"):
            result = _actions.create_product(ctx)
        assert result.ok
        manifest = _ac.read_manifest(root, "scorepocket")
        entry = manifest["artifacts"]["product"]
        assert entry["version"] == 1
        assert entry["file"] == "product.json"
        assert entry["producer"] == "product-pipeline"
        assert entry["trace_id"] == "trace-cp"
        assert manifest["version"] == 1
        data = _read_json(root / "projects" / "scorepocket" / "product.json")
        assert data["name"] == "ScorePocket"
        assert data["status"] == "product_defined"

    def test_create_product_no_context_trace_none(self, fake_org, tmp_path):
        """无 trace 上下文 → trace_id=None (K-4 失败安全, 不伪造)。"""
        root = tmp_path / "ws"
        root.mkdir()
        ctx = _exec_ctx(root)
        ctx.session.product_intent = _complete_product()
        result = _actions.create_product(ctx)
        assert result.ok
        entry = _ac.read_manifest(root, "scorepocket")["artifacts"]["product"]
        assert entry["trace_id"] is None

    def test_create_product_second_write_archives_history(self, fake_org, tmp_path):
        """第二次写 → 版本+1 + history/product.v1.json 归档。"""
        root = tmp_path / "ws"
        root.mkdir()
        _create_product(root)
        ctx2 = _exec_ctx(root)
        ctx2.session.product_intent = _complete_product(name="ScorePocket-2")
        with _trace.trace_context("trace-2"):
            result = _actions.create_product(ctx2)
        assert result.ok
        manifest = _ac.read_manifest(root, "scorepocket")
        entry = manifest["artifacts"]["product"]
        assert entry["version"] == 2
        assert entry["trace_id"] == "trace-2"
        assert (root / "projects" / "scorepocket" / "history" / "product.v1.json").is_file()
        versions = entry["versions"]
        assert len(versions) == 2
        assert versions[0]["file"] == "history/product.v1.json"
        assert versions[0]["producer"] == "product-pipeline"

    def test_generate_prd_contract(self, fake_org, tmp_path):
        """写点 2/3: generate_prd → PRD.md (raw_text 全文) + product.json (合并) 经契约。"""
        root = tmp_path / "ws"
        root.mkdir()
        _create_product(root)
        ctx = _exec_ctx(root)
        ctx.session.product_intent = _complete_product()
        with _trace.trace_context("trace-prd"):
            result = _actions.generate_prd(ctx)
        assert result.ok
        manifest = _ac.read_manifest(root, "scorepocket")
        prd = manifest["artifacts"]["prd"]
        assert prd["version"] == 1
        assert prd["file"] == "PRD.md"
        assert prd["producer"] == "product-pipeline"
        assert prd["trace_id"] == "trace-prd"
        product = manifest["artifacts"]["product"]
        assert product["version"] == 2  # create v1 + generate_prd 合并 v2
        # 内容一致: markdown 全文逐字节一致
        expected = _pipe.ProductDocument.from_product_intent(_complete_product())
        actual = (root / "projects" / "scorepocket" / "PRD.md").read_text(
            encoding="utf-8"
        )
        assert actual == expected
        # product.json 合并内容一致 (无 canonical project.json → status=engineering_ready)
        data = _read_json(root / "projects" / "scorepocket" / "product.json")
        assert data["name"] == "ScorePocket"
        assert data["status"] == "engineering_ready"

    def test_generate_prd_second_write_archives_history(self, fake_org, tmp_path):
        """第二次 generate_prd → PRD v2 + history/PRD.v1.md 归档 (内容含旧全文)。"""
        root = tmp_path / "ws"
        root.mkdir()
        _create_product(root)
        for _ in range(2):
            ctx = _exec_ctx(root)
            ctx.session.product_intent = _complete_product()
            result = _actions.generate_prd(ctx)
            assert result.ok
        manifest = _ac.read_manifest(root, "scorepocket")
        prd = manifest["artifacts"]["prd"]
        assert prd["version"] == 2
        hist = root / "projects" / "scorepocket" / "history" / "PRD.v1.md"
        assert hist.is_file()
        expected = _pipe.ProductDocument.from_product_intent(_complete_product())
        assert hist.read_text(encoding="utf-8") == expected

    def test_prepare_project_contract(self, fake_org, tmp_path):
        """写点 12 + 补全: prepare_project → prd/engineering/tasks/execution_plan/product 全经契约。"""
        root = tmp_path / "ws"
        root.mkdir()
        _create_product(root)
        ctx = _exec_ctx(root)
        ctx.session.product_intent = _complete_product()
        with _trace.trace_context("trace-prep"):
            result = _actions.prepare_project(ctx)
        assert result.ok, result.message
        manifest = _ac.read_manifest(root, "scorepocket")
        for atype in ("prd", "engineering", "tasks", "execution_plan", "product"):
            entry = manifest["artifacts"].get(atype)
            assert entry is not None, f"manifest 缺 {atype}"
            assert entry["producer"] == "product-pipeline"
            assert entry["trace_id"] == "trace-prep"
            assert entry["version"] >= 1
        # 文件真实落盘 + JSON 内容可读
        pdir = root / "projects" / "scorepocket"
        for fname in ("PRD.md", "engineering.json", "tasks.json",
                      "execution_plan.json", "product.json"):
            assert (pdir / fname).is_file(), f"{fname} 未落盘"
        plan = _read_json(pdir / "engineering.json")
        assert plan["name"] == "ScorePocket"
        tree = _read_json(pdir / "tasks.json")
        assert tree["count"] >= 1
        ep = _read_json(pdir / "execution_plan.json")
        assert ep["count"] >= 1

    def test_prepare_project_second_write_archives_history(self, fake_org, tmp_path):
        """第二次 prepare_project → 每类版本+1 + history/<名>.v1.* 归档。"""
        root = tmp_path / "ws"
        root.mkdir()
        _create_product(root)
        for _ in range(2):
            ctx = _exec_ctx(root)
            ctx.session.product_intent = _complete_product()
            result = _actions.prepare_project(ctx)
            assert result.ok
        pdir = root / "projects" / "scorepocket"
        manifest = _ac.read_manifest(root, "scorepocket")
        for atype, hist_name, version in (
            ("prd", "PRD.v1.md", 2),
            ("engineering", "engineering.v1.json", 2),
            ("tasks", "tasks.v1.json", 2),
            ("execution_plan", "execution_plan.v1.json", 2),
            # product: create v1 + prepare v2 + prepare v3 (含 create 写点)
            ("product", "product.v1.json", 3),
        ):
            assert manifest["artifacts"][atype]["version"] == version
            assert (pdir / "history" / hist_name).is_file(), f"{hist_name} 未归档"

    def test_rename_project_contract(self, fake_org, tmp_path):
        """补全写点: rename_project → product.json 名称同步经契约 (版本+1)。"""
        root = tmp_path / "ws"
        root.mkdir()
        _create_product(root)
        # org/projects.json 记录 (rename_project 读 org 数据)
        org = root / "org"
        org.mkdir(parents=True, exist_ok=True)
        (org / "projects.json").write_text(
            json.dumps({"projects": {"P-scorepocket": {"name": "ScorePocket", "slug": "scorepocket"}}},
                       ensure_ascii=False),
            encoding="utf-8",
        )
        ctx = _exec_ctx(root, project="scorepocket")
        ctx.intent = _act.IntentObject(
            intent_type="rename_project",
            params={"project_id": "P-scorepocket", "name": "新名字"},
        )
        with _trace.trace_context("trace-rename"):
            result = _actions.rename_project(ctx)
        assert result.ok, result.message
        manifest = _ac.read_manifest(root, "scorepocket")
        entry = manifest["artifacts"]["product"]
        assert entry["version"] == 2
        assert entry["producer"] == "product-pipeline"
        assert entry["trace_id"] == "trace-rename"
        data = _read_json(root / "projects" / "scorepocket" / "product.json")
        assert data["name"] == "新名字"


# ================================================================== orchestrator.py 写点


class TestOrchestratorContractWiring:
    """写点 5/6/7: execution_state / tasks (replan 同步) / execution_plan (bump)。"""

    def test_execute_project_state_contract(self, tmp_path):
        """写点 5: 执行 → execution_state.json 经契约 (producer/trace_id/版本递增/历史)。"""
        root = tmp_path / "ws"
        root.mkdir()
        _make_project_assets(root)
        orch = _orch.ExecutionOrchestrator(root)

        def ok_fn(task, project_dir, workspace):
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        with _trace.trace_context("trace-exec"):
            result = orch.execute_project("scorepocket", execute_fn=ok_fn)
        assert result.status in ("user_acceptance", "delivered")
        manifest = _ac.read_manifest(root, "scorepocket")
        entry = manifest["artifacts"]["execution_state"]
        assert entry["file"] == "execution_state.json"
        assert entry["producer"] == "orchestrator"
        assert entry["trace_id"] == "trace-exec"
        assert entry["version"] >= 1
        # 每任务状态变更多次 _save_state → 第二次写归档 history
        assert (root / "projects" / "scorepocket" / "history" / "execution_state.v1.json").is_file()
        state = _orch.ExecutionState.load(
            root / "projects" / "scorepocket" / "execution_state.json"
        )
        assert state is not None
        assert len(state.tasks) >= 1

    def test_replan_tasks_and_execution_plan_contract(self, tmp_path):
        """写点 6/7: INSERT_TASK replan → tasks.json + execution_plan.json 经契约。"""
        root = tmp_path / "ws"
        root.mkdir()
        _make_project_assets(root)
        eng = _replan.ReplanningEngine(file=root / "replanning_decisions.json")
        calls: list = []

        def fn(task, project_dir, workspace):
            calls.append(task["id"])
            if task["id"] == "T1":
                return {"success": False, "error": "missing api contract"}
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        orch = _orch.ExecutionOrchestrator(root)
        with _trace.trace_context("trace-replan"):
            orch.execute_project(
                "scorepocket",
                execute_fn=fn,
                replanner=eng,
                insert_tasks=[{"id": "T2", "name": "API Contract"}],
            )
        assert "T2" in calls
        manifest = _ac.read_manifest(root, "scorepocket")
        for atype in ("tasks", "execution_plan", "execution_state"):
            entry = manifest["artifacts"].get(atype)
            assert entry is not None, f"manifest 缺 {atype}"
            assert entry["producer"] == "orchestrator"
            assert entry["trace_id"] == "trace-replan"
        # tasks.json 内容含新任务
        tasks = _read_json(root / "projects" / "scorepocket" / "tasks.json")
        assert "T2" in {t.get("id") for t in tasks["tasks"]}
        # execution_plan.json 含 plan_version 推进
        ep = _read_json(root / "projects" / "scorepocket" / "execution_plan.json")
        assert int(ep.get("plan_version") or 1) >= 2


# ================================================================== change_control.py 写点


class TestChangeControlContractWiring:
    """写点 9/10 + 补全: PRD v2 追加场景 + tasks/plan/execution_plan 合并。"""

    def _prepared(self, root: Path) -> str:
        """create + prepare_project → slug (资产经契约写入, manifest 已存在)。"""
        _create_product(root)
        ctx = _exec_ctx(root)
        ctx.session.product_intent = _complete_product()
        result = _actions.prepare_project(ctx)
        assert result.ok, result.message
        return "scorepocket"

    def test_change_control_prd_v2_contract(self, tmp_path):
        """PRD v2: 读全文+合并 → 整体 set_artifact (归档旧版, producer/trace_id)。"""
        root = tmp_path / "ws"
        root.mkdir()
        slug = self._prepared(root)
        controller = _cc.ChangeController(root)
        proposal = _cc.ChangeProposal(
            id="cp-1", project_slug=slug, request="加导出", reason="用户需要导出"
        )
        with _trace.trace_context("trace-cc"):
            result = controller.apply(proposal, True)
        assert result["applied"] is True
        manifest = _ac.read_manifest(root, slug)
        prd = manifest["artifacts"]["prd"]
        assert prd["version"] == 2  # prepare v1 + change v2
        assert prd["producer"] == "change-control"
        assert prd["trace_id"] == "trace-cc"
        # 旧版归档 (history/PRD.v1.md) — 历史不丢
        hist = root / "projects" / slug / "history" / "PRD.v1.md"
        assert hist.is_file()
        # 内容: PRD.md 含变更记录 v2 + 旧全文仍在
        prd_text = (root / "projects" / slug / "PRD.md").read_text(encoding="utf-8")
        assert "# 变更记录 v2: 加导出" in prd_text
        expected = _pipe.ProductDocument.from_product_intent(_complete_product())
        assert expected in prd_text

    def test_change_control_merge_tasks_plan_contract(self, tmp_path):
        """tasks/plan/execution_plan 合并全部经契约 (版本+producer/trace_id)。"""
        root = tmp_path / "ws"
        root.mkdir()
        slug = self._prepared(root)
        controller = _cc.ChangeController(root)
        proposal = _cc.ChangeProposal(
            id="cp-2", project_slug=slug, request="加统计", reason="报表需要"
        )
        with _trace.trace_context("trace-cc2"):
            result = controller.apply(proposal, True)
        assert result["applied"] is True
        manifest = _ac.read_manifest(root, slug)
        # tasks: prepare v1 → change v2; plan: 新建 v1; execution_plan: prepare v1 → change v2
        tasks = manifest["artifacts"]["tasks"]
        assert tasks["version"] == 2
        assert tasks["producer"] == "change-control"
        assert tasks["trace_id"] == "trace-cc2"
        plan = manifest["artifacts"]["plan"]
        assert plan["version"] == 1
        assert plan["producer"] == "change-control"
        assert plan["trace_id"] == "trace-cc2"
        ep = manifest["artifacts"]["execution_plan"]
        assert ep["version"] == 2
        assert ep["producer"] == "change-control"
        # 内容: tasks.json 含新任务 (feature=request), plan.json 含新 id
        tasks_data = _read_json(root / "projects" / slug / "tasks.json")
        new_tasks = [t for t in tasks_data["tasks"] if t.get("feature") == "加统计"]
        assert new_tasks
        plan_data = _read_json(root / "projects" / slug / "plan.json")
        new_ids = {t["id"] for t in new_tasks}
        assert new_ids <= {t["id"] for t in plan_data["tasks"]}


# ================================================================== 失败安全


class TestContractFailureSafety:
    """set_artifact 异常 (mock) → 引擎不中断 (不写直写回退)。"""

    def test_actions_set_artifact_failure_does_not_block(self, fake_org, tmp_path, monkeypatch):
        root = tmp_path / "ws"
        root.mkdir()

        def boom(*a, **k):
            raise RuntimeError("contract down")

        monkeypatch.setattr(_actions, "set_artifact", boom)
        ctx = _exec_ctx(root)
        ctx.session.product_intent = _complete_product()
        result = _actions.create_product(ctx)
        assert result.ok  # 引擎不中断
        assert result.status == "ok"
        # 无直写回退: product.json 未落盘 (契约尽力而为, 不绕过契约写)
        assert not (root / "projects" / "scorepocket" / "product.json").exists()

    def test_orchestrator_set_artifact_failure_does_not_block(self, tmp_path, monkeypatch):
        root = tmp_path / "ws"
        root.mkdir()
        _make_project_assets(root)

        def boom(*a, **k):
            raise RuntimeError("contract down")

        monkeypatch.setattr(_orch, "set_artifact", boom)
        orch = _orch.ExecutionOrchestrator(root)

        def ok_fn(task, project_dir, workspace):
            return {"success": True, "artifact": "/tmp/x", "cost": "1"}

        result = orch.execute_project("scorepocket", execute_fn=ok_fn)
        assert result.status in ("user_acceptance", "delivered")  # 引擎照常完成
        assert result.completed_tasks >= 1

    def test_change_control_set_artifact_failure_does_not_block(self, tmp_path, monkeypatch):
        root = tmp_path / "ws"
        root.mkdir()
        _create_product(root)
        ctx = _exec_ctx(root)
        ctx.session.product_intent = _complete_product()
        assert _actions.prepare_project(ctx).ok

        def boom(*a, **k):
            raise RuntimeError("contract down")

        monkeypatch.setattr(_cc, "set_artifact", boom)
        controller = _cc.ChangeController(root)
        proposal = _cc.ChangeProposal(
            id="cp-3", project_slug="scorepocket", request="加导出", reason="需要"
        )
        result = controller.apply(proposal, True)  # 不抛
        assert result["applied"] is True
        assert result["status"] == "approved"


# ================================================================== 直写归零


class TestNoDirectWrites:
    """4 个改造文件无残留直写标准产出物文件名 (读/引用除外)。"""

    _FILES = [
        "factory-console/session/actions.py",
        "factory-console/session/orchestrator.py",
        "factory-console/session/change_control.py",
        "factory-console/service.py",
    ]
    _STANDARD = [
        "product.json",
        "PRD.md",
        "engineering.json",
        "plan.json",
        "tasks.json",
        "execution_plan.json",
        "execution_state.json",
        "validation_result.json",
        "repair_task.json",
    ]
    _WRITE_MARKERS = (
        "write_text",
        "write_bytes",
        "_write_json_file",
        "_write_json(",
        "json.dump",
        ".write(",
        "open(",
    )

    @pytest.mark.parametrize("path", _FILES)
    def test_no_direct_write_of_standard_files(self, path):
        src = Path(path).read_text(encoding="utf-8")
        hits: list[str] = []
        for lineno, line in enumerate(src.splitlines(), 1):
            if any(f in line for f in self._STANDARD) and any(
                m in line for m in self._WRITE_MARKERS
            ):
                hits.append(f"{path}:{lineno}: {line.strip()}")
        assert not hits, "残留直写标准产出物:\n" + "\n".join(hits)

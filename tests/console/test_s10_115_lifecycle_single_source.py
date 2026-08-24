"""tests/console/test_s10_115_lifecycle_single_source.py — S10-115 J-1 生命周期状态单一来源契约测试 (v1.1.83)。

覆盖 (设计 §2 a-h, 仿 test_s10_112 风格):
a. 写点枚举: 静态 AST 扫描 actions/orchestrator/service 直接写 status/lifecycle 的
   JSON 落盘/赋值调用 → 白名单断言 (全部经 set_project_lifecycle 或显式标注例外)
b. 一致性校验器: 漂移 fixture (三处不一致) → board.project_state_consistency 检出;
   一致项目 → 通过
c. 防回退: development 项目重生成 PRD → project.json.status 不变 (仍 development),
   product.json.status 不被降级 (跟随 canonical)
d. 对账修复: 缺 project.json / product.json 回退漂移 → 修复后三处一致 + 快照落盘
e. 词汇映射: project_created→product_defined / prd_ready→engineering_ready /
   未知 → 无法判定跳过 (不臆造)
f. 统一入口单测: 合法写 / 非法词汇错误 / 防回退拒绝 / force 例外 / 失败安全
g. board 读取: canonical 优先 (project.json 存在 → 用之; 缺失 → 回退 product.json)
h. 回归: 全链 (create_product→prepare→approve→execute→accept) 三处一致

basename 全仓库唯一 (test_s10_115_* 前缀, 与读侧 test_s10_115_board_consistency 区分)。
"""

from __future__ import annotations

import ast
import importlib
import json
import re
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

ACT = importlib.import_module("factory-console.session.action")
ACTIONS = importlib.import_module("factory-console.session.actions")
BOARD = importlib.import_module("factory-console.session.board")
CTX = importlib.import_module("factory-console.session.context")
INT = importlib.import_module("factory-console.session.intent")
LS = importlib.import_module("factory-console.session.lifecycle_store")
ORCH = importlib.import_module("factory-console.session.orchestrator")
PIPE = importlib.import_module("factory-console.session.pipeline")
PROD = importlib.import_module("factory-console.session.product")

Lifecycle = LS.Lifecycle


# ------------------------------------------------------------------ 工具


def _ctx(root: Path, slug: str = "") -> ACT.ExecutionContext:
    """tmp workspace ExecutionContext (current_project 可选, 不依赖 org 注册)。"""
    sess = CTX.SessionContext(workspace=str(root))
    if slug:
        sess.current_project = slug
    return ACT.ExecutionContext(workspace=root, session=sess, user="user", project=slug or None)


def _write_product(pdir: Path, *, name: str = "demo", status: str, extra: dict | None = None) -> Path:
    """落盘 product.json (ProductIntent 可读形状)。"""
    data = {
        "name": name,
        "problem": "测试问题",
        "user": "测试用户",
        "platform": "web",
        "core_features": ["f1", "f2"],
        "status": status,
    }
    if extra:
        data.update(extra)
    pf = pdir / "product.json"
    pf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return pf


def _write_project(pdir: Path, *, status: str | None = None, extra: dict | None = None) -> Path:
    """落盘 project.json (name + 可选 status + 可选字段)。"""
    data = {"name": pdir.name}
    if status is not None:
        data["status"] = status
    if extra:
        data.update(extra)
    pj = pdir / "project.json"
    pj.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return pj


def _write_state(pdir: Path, *, lifecycle: str | None = None, tasks: list | None = None) -> Path:
    """落盘 execution_state.json。"""
    data = {"project": pdir.name, "status": lifecycle or "", "lifecycle": lifecycle or ""}
    if tasks is not None:
        data["tasks"] = tasks
    sf = pdir / "execution_state.json"
    sf.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return sf


def _three_tracks(pdir: Path) -> tuple[str, str, str]:
    """三处状态值 (project/product/state; 缺失 → ""), 测试断言辅助。"""
    pj = ""
    if (pdir / "project.json").is_file():
        try:
            pj = str(json.loads((pdir / "project.json").read_text(encoding="utf-8")).get("status") or "")
        except Exception:  # noqa: BLE001
            pj = "<corrupt>"
    pd = ""
    if (pdir / "product.json").is_file():
        try:
            pd = str(json.loads((pdir / "product.json").read_text(encoding="utf-8")).get("status") or "")
        except Exception:  # noqa: BLE001
            pd = "<corrupt>"
    es = ""
    if (pdir / "execution_state.json").is_file():
        try:
            es = str(json.loads((pdir / "execution_state.json").read_text(encoding="utf-8")).get("lifecycle") or "")
        except Exception:  # noqa: BLE001
            es = "<corrupt>"
    return pj, pd, es


# ================================================================== a. 写点枚举 (静态白名单)


def _status_touch_functions(source: str) -> set[str]:
    """AST: 函数内直接写 status/lifecycle (属性/下标赋值 或 JSON 落盘 dict 字面量键)。"""
    tree = ast.parse(source)
    hits: set[str] = set()
    write_names = {"_write_json_file", "_write_json", "write_json", "save", "_save_state"}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        found = False
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign):
                for t in sub.targets:
                    if isinstance(t, ast.Attribute) and t.attr in ("status", "lifecycle"):
                        found = True
                    elif (
                        isinstance(t, ast.Subscript)
                        and isinstance(t.slice, ast.Constant)
                        and t.slice.value in ("status", "lifecycle")
                    ):
                        found = True
            if isinstance(sub, ast.Call):
                fname = ""
                if isinstance(sub.func, ast.Name):
                    fname = sub.func.id
                elif isinstance(sub.func, ast.Attribute):
                    fname = sub.func.attr
                if fname in write_names and _call_payload_has_status_key(sub):
                    found = True
            if found:
                break
        if found:
            hits.add(node.name)
    return hits


def _call_payload_has_status_key(call: ast.Call) -> bool:
    """调用参数中是否有含 status/lifecycle 键的 dict 字面量。"""
    for arg in list(call.args) + [kw.value for kw in call.keywords]:
        if _dict_has_status_key(arg):
            return True
    return False


def _dict_has_status_key(node: ast.AST) -> bool:
    if isinstance(node, ast.Dict):
        for key in node.keys:
            if isinstance(key, ast.Constant) and key.value in ("status", "lifecycle"):
                return True
        return False
    if isinstance(node, ast.Call):
        return any(_dict_has_status_key(kw.value) for kw in node.keywords)
    return False


#: 白名单 — 直接写 status/lifecycle 的显式例外 (设计 §0.3 表 + 写点文档 §1.3)
STATUS_WRITE_WHITELIST = {
    "actions": {
        "create_product",        # W1: product.json 落盘值 product_defined (canonical 由 org/统一入口管理)
        "generate_prd",          # W2: 无 canonical → engineering_ready; canonical 存在 → 不写
        "prepare_project",       # W3: S10-111 架构审批门 gate 值 (非 Lifecycle, 范围外)
        "approve_project_plan",  # W4: rejected 分支保持 gate 值; approved 经 set_project_lifecycle
    },
    "orchestrator": {
        "execute_project",       # W5: state.status/lifecycle 内存 + _save_state (引擎状态机)
        "_m3_execute_rounds",    # W5: 同上
        "_run_queue",            # W5: 同上
        "resume",                # W5: 恢复语义 (仅 execution_state, 范围外)
        "accept_project",        # W5: state 内存 + _save_state; 落盘经 _set_lifecycle
        "_execute_with_retry",   # 任务级状态 (running/completed/failed), 非三轨生命周期
        "_mark_plan_task",       # 任务级状态 (skipped/blocked/split), 非三轨生命周期
    },
    "service": {
        "confirm_project",       # W6: org 镜像 lifecycle=confirmed (status 缺省 → 统一入口补)
        "create_draft_project",  # W6: org Project.lifecycle=DISCOVERY (org 镜像, 非 Lifecycle canonical)
        "update_milestone",      # 管理域 milestone.status (自有数据域, 非三轨)
    },
}


class TestWritePointEnumeration:
    """验收 1: 全写点枚举 — 直接写 status/lifecycle 的调用全部在显式白名单。"""

    def test_actions_status_writes_in_whitelist(self):
        src = (_ROOT / "factory-console" / "session" / "actions.py").read_text(encoding="utf-8")
        hits = _status_touch_functions(src)
        assert hits, "静态扫描未命中任何写点 (扫描失效?)"
        assert hits <= STATUS_WRITE_WHITELIST["actions"], (
            f"actions 直接写 status/lifecycle 未进白名单: {hits - STATUS_WRITE_WHITELIST['actions']}"
        )

    def test_orchestrator_status_writes_in_whitelist(self):
        src = (_ROOT / "factory-console" / "session" / "orchestrator.py").read_text(encoding="utf-8")
        hits = _status_touch_functions(src)
        assert hits <= STATUS_WRITE_WHITELIST["orchestrator"], (
            f"orchestrator 直接写 status/lifecycle 未进白名单: {hits - STATUS_WRITE_WHITELIST['orchestrator']}"
        )

    def test_service_status_writes_in_whitelist(self):
        src = (_ROOT / "factory-console" / "service.py").read_text(encoding="utf-8")
        hits = _status_touch_functions(src)
        assert hits <= STATUS_WRITE_WHITELIST["service"], (
            f"service 直接写 status/lifecycle 未进白名单: {hits - STATUS_WRITE_WHITELIST['service']}"
        )

    def test_set_lifecycle_delegates_to_unified_entry(self, monkeypatch):
        """orchestrator._set_lifecycle 委托 set_project_lifecycle (签名兼容)。"""
        calls: list[tuple] = []

        def fake(project_dir, status, **kw):
            calls.append((str(Path(project_dir)), status, kw))
            return {"status": status, "written": []}

        monkeypatch.setattr(ORCH, "set_project_lifecycle", fake)
        orch = ORCH.ExecutionOrchestrator("/tmp/nowhere")
        orch._set_lifecycle(Path("/tmp/p"), "P-1", Lifecycle.DEVELOPMENT)
        assert calls and calls[0][1] == Lifecycle.DEVELOPMENT
        # 默认 state_file 指向 execution_state.json (执行状态同步)
        assert "state_file" not in calls[0][2]  # 缺省由入口推导

    def test_approve_project_plan_routes_through_unified_entry(self, tmp_path):
        """approve y → 状态推进经 set_project_lifecycle (不再手工双写)。"""
        root = tmp_path / "ws"
        root.mkdir()
        pdir = root / "projects" / "crm"
        pdir.mkdir(parents=True)
        _write_product(pdir, name="CRM", status=Lifecycle.ENGINEERING_READY)
        _write_project(pdir, status="pending_arch_review", extra={"arch_review": {"summary": "s"}})
        ctx = _ctx(root, "crm")
        calls: list[str] = []
        original = LS.set_project_lifecycle

        def spy(*args, **kwargs):
            calls.append((str(Path(args[0])), args[1]))
            return original(*args, **kwargs)

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(ACTIONS, "set_project_lifecycle", spy)
        intent = INT.IntentObject(
            intent_type="approve_project_plan", params={},
            metadata={"confirm_fn": lambda: "y"},
        )
        ctx2 = ACT.ExecutionContext(
            workspace=root, session=ctx.session, user="user", project="crm", intent=intent
        )
        result = ACTIONS.approve_project_plan(ctx2)
        monkeypatch.undo()
        assert result.ok, result.message
        assert any(st == Lifecycle.EXECUTION_READY for _, st in calls), "审批未走统一入口"
        pj, pd, _ = _three_tracks(pdir)
        assert pj == Lifecycle.EXECUTION_READY
        assert pd == Lifecycle.EXECUTION_READY


# ================================================================== b. 一致性校验器


class TestConsistencyValidator:
    def test_drift_detected(self, tmp_path):
        """漂移 fixture (日记实测形态: project=development, product=prd_ready) → 检出。"""
        pdir = tmp_path / "projects" / "riji"
        pdir.mkdir(parents=True)
        _write_project(pdir, status=Lifecycle.DEVELOPMENT)
        _write_product(pdir, name="日记", status="prd_ready")
        _write_state(pdir, lifecycle=Lifecycle.DEVELOPMENT)
        cons = BOARD.project_state_consistency(tmp_path, "riji")
        assert cons["canonical"] == Lifecycle.DEVELOPMENT
        assert cons["drifted"] is True
        assert cons["project"] == Lifecycle.DEVELOPMENT
        assert cons["product"] == "prd_ready"

    def test_consistent_project_passes(self, tmp_path):
        """一致项目 (三处同值) → 校验器通过 (drifted=False)。"""
        pdir = tmp_path / "projects" / "ok"
        pdir.mkdir(parents=True)
        _write_project(pdir, status=Lifecycle.USER_ACCEPTANCE)
        _write_product(pdir, status=Lifecycle.USER_ACCEPTANCE)
        _write_state(pdir, lifecycle=Lifecycle.USER_ACCEPTANCE)
        cons = BOARD.project_state_consistency(tmp_path, "ok")
        assert cons["drifted"] is False
        assert cons["canonical"] == Lifecycle.USER_ACCEPTANCE

    def test_missing_canonical_reported(self, tmp_path):
        """缺 project.json (canonical 缺失) → missing 标记 (不臆造)。"""
        pdir = tmp_path / "projects" / "mojian"
        pdir.mkdir(parents=True)
        _write_product(pdir, name="墨笺", status="prd_ready")
        cons = BOARD.project_state_consistency(tmp_path, "mojian")
        assert "project" in cons["missing"]
        assert cons["canonical"] == "prd_ready"  # 回退 product.json 展示


# ================================================================== c. 防回退


class TestAntiRegression:
    def test_prd_regeneration_does_not_downgrade_development(self, tmp_path):
        """development 项目重生成 PRD → project.json.status 不变, product.json.status 不降级。"""
        root = tmp_path / "ws"
        root.mkdir()
        pdir = root / "projects" / "riji"
        pdir.mkdir(parents=True)
        _write_project(pdir, status=Lifecycle.DEVELOPMENT)
        _write_product(pdir, name="日记", status=Lifecycle.DEVELOPMENT)
        _write_state(pdir, lifecycle=Lifecycle.DEVELOPMENT)
        result = ACTIONS.generate_prd(_ctx(root, "riji"))
        assert result.ok, result.message
        pj, pd, _ = _three_tracks(pdir)
        assert pj == Lifecycle.DEVELOPMENT, "canonical 被 PRD 动作覆盖"
        assert pd == Lifecycle.DEVELOPMENT, "product.json 镜像被降级"
        # 结果上报 canonical (不谎报 prd_ready/engineering_ready)
        assert result.data["status"] == Lifecycle.DEVELOPMENT

    def test_prd_regeneration_keeps_later_state(self, tmp_path):
        """user_acceptance 项目重生成 PRD → 保持 user_acceptance (单调)。"""
        root = tmp_path / "ws"
        root.mkdir()
        pdir = root / "projects" / "late"
        pdir.mkdir(parents=True)
        _write_project(pdir, status=Lifecycle.USER_ACCEPTANCE)
        _write_product(pdir, name="late", status=Lifecycle.USER_ACCEPTANCE)
        _write_state(pdir, lifecycle=Lifecycle.USER_ACCEPTANCE)
        result = ACTIONS.generate_prd(_ctx(root, "late"))
        assert result.ok, result.message
        pj, pd, _ = _three_tracks(pdir)
        assert (pj, pd) == (Lifecycle.USER_ACCEPTANCE, Lifecycle.USER_ACCEPTANCE)

    def test_prd_without_canonical_sets_engineering_ready(self, tmp_path):
        """无 canonical (project.json 缺失) → product.status=engineering_ready (旧 prd_ready 等价)。"""
        root = tmp_path / "ws"
        root.mkdir()
        pdir = root / "projects" / "fresh"
        pdir.mkdir(parents=True)
        _write_product(pdir, name="fresh", status=Lifecycle.PRODUCT_DEFINED)
        result = ACTIONS.generate_prd(_ctx(root, "fresh"))
        assert result.ok, result.message
        _, pd, _ = _three_tracks(pdir)
        assert pd == Lifecycle.ENGINEERING_READY
        assert result.data["status"] == Lifecycle.ENGINEERING_READY


# ================================================================== d. 对账修复


class TestReconcile:
    def test_reconcile_fixes_missing_project_json(self, tmp_path):
        """缺 project.json (product=prd_ready) → 修复建 canonical=engineering_ready + 快照落盘。"""
        pdir = tmp_path / "projects" / "mojian"
        pdir.mkdir(parents=True)
        _write_product(pdir, name="墨笺", status="prd_ready")
        report = LS.reconcile_projects(tmp_path)
        fixed = [f for f in report.fixed if f["slug"] == "mojian"]
        assert fixed and fixed[0]["status"] == Lifecycle.ENGINEERING_READY
        assert fixed[0]["source"] == "product.json.status"
        pj, pd, _ = _three_tracks(pdir)
        assert pj == Lifecycle.ENGINEERING_READY
        assert pd == Lifecycle.ENGINEERING_READY
        assert len(report.snapshots) == 1
        snap = json.loads(Path(report.snapshots[0]).read_text(encoding="utf-8"))
        assert snap["product_json"]["status"] == "prd_ready"  # 三处原值
        assert snap["canonical"] == Lifecycle.ENGINEERING_READY

    def test_reconcile_fixes_product_regression_drift(self, tmp_path):
        """product.json 回退漂移 (project=development, product=prd_ready) → 修复后三处一致。"""
        pdir = tmp_path / "projects" / "riji"
        pdir.mkdir(parents=True)
        _write_project(pdir, status=Lifecycle.DEVELOPMENT)
        _write_product(pdir, name="日记", status="prd_ready")
        _write_state(pdir, lifecycle=Lifecycle.DEVELOPMENT)
        report = LS.reconcile_projects(tmp_path)
        fixed = [f for f in report.fixed if f["slug"] == "riji"]
        assert fixed and fixed[0]["status"] == Lifecycle.DEVELOPMENT
        pj, pd, es = _three_tracks(pdir)
        assert pj == pd == es == Lifecycle.DEVELOPMENT
        assert report.snapshots, "修复前快照未落盘"

    def test_reconcile_skips_consistent_and_undeterminable(self, tmp_path):
        """一致项目 → 跳过 (已一致); 全无状态 → 跳过 (无法判定, 不臆造)。"""
        pdir = tmp_path / "projects" / "ok"
        pdir.mkdir(parents=True)
        _write_project(pdir, status=Lifecycle.EXECUTION_READY)
        _write_product(pdir, status=Lifecycle.EXECUTION_READY)
        ghost = tmp_path / "projects" / "ghost"
        ghost.mkdir()
        (ghost / "random.txt").write_text("x", encoding="utf-8")
        report = LS.reconcile_projects(tmp_path)
        skipped = {s["slug"]: s for s in report.skipped}
        assert skipped["ok"]["reason"] == "已一致"
        assert "无法判定" in skipped["ghost"]["reason"]
        assert not report.fixed
        assert not report.snapshots

    def test_reconcile_dry_run_read_only(self, tmp_path):
        """dry_run → 只读报告 (不写快照/不修复)。"""
        pdir = tmp_path / "projects" / "riji"
        pdir.mkdir(parents=True)
        _write_project(pdir, status=Lifecycle.DEVELOPMENT)
        _write_product(pdir, status="prd_ready")
        report = LS.reconcile_projects(tmp_path, dry_run=True)
        assert report.fixed and report.fixed[0].get("dry_run") is True
        assert not report.snapshots
        pj, pd, _ = _three_tracks(pdir)
        assert pd == "prd_ready"  # 未修复


# ================================================================== e. 词汇映射


class TestLegacyMapping:
    def test_legacy_status_map(self):
        assert LS.LEGACY_STATUS_MAP == {
            "project_created": Lifecycle.PRODUCT_DEFINED,
            "prd_ready": Lifecycle.ENGINEERING_READY,
            "draft": Lifecycle.IDEA,
            "confirmed": Lifecycle.PRODUCT_DEFINED,
        }

    def test_unknown_status_unmappable(self):
        assert LS._as_lifecycle("weird_status") is None
        assert LS._as_lifecycle(None) is None
        assert LS._canonical_index("weird_status") is None

    def test_lifecycle_values_pass_through(self):
        assert LS._as_lifecycle(Lifecycle.DEVELOPMENT) == Lifecycle.DEVELOPMENT
        assert LS._as_lifecycle("prd_ready") == Lifecycle.ENGINEERING_READY
        assert LS._as_lifecycle("project_created") == Lifecycle.PRODUCT_DEFINED

    def test_reconcile_skips_unknown_product_status(self, tmp_path):
        """product.json 未知状态 → 无法判定跳过 (不臆造)。"""
        pdir = tmp_path / "projects" / "weird"
        pdir.mkdir(parents=True)
        _write_product(pdir, status="some_old_gate")
        report = LS.reconcile_projects(tmp_path)
        assert any(s["slug"] == "weird" and "无法判定" in s["reason"] for s in report.skipped)


# ================================================================== f. 统一入口单测


class TestSetProjectLifecycle:
    def test_valid_write_three_tracks(self, tmp_path):
        pdir = tmp_path / "p1"
        pdir.mkdir()
        _write_product(pdir, status="prd_ready")
        _write_state(pdir, lifecycle="idea")
        r = LS.set_project_lifecycle(pdir, Lifecycle.DEVELOPMENT)
        assert r["status"] == Lifecycle.DEVELOPMENT
        pj, pd, es = _three_tracks(pdir)
        assert (pj, pd, es) == (Lifecycle.DEVELOPMENT, Lifecycle.DEVELOPMENT, Lifecycle.DEVELOPMENT)
        assert not r["errors"]

    def test_missing_files_created_or_skipped(self, tmp_path):
        """project.json 缺失 → 新建; product/state 缺失 → 跳过 (存在才同步)。"""
        pdir = tmp_path / "p2"
        pdir.mkdir()
        r = LS.set_project_lifecycle(pdir, Lifecycle.IDEA)
        assert (pdir / "project.json").is_file()
        assert json.loads((pdir / "project.json").read_text(encoding="utf-8"))["status"] == Lifecycle.IDEA
        assert r["product_file"] is None and r["state_file"] is None

    def test_invalid_vocab_raises(self, tmp_path):
        pdir = tmp_path / "p3"
        pdir.mkdir()
        with pytest.raises(ValueError, match="非法生命周期状态"):
            LS.set_project_lifecycle(pdir, "bogus")

    def test_regression_rejected(self, tmp_path):
        pdir = tmp_path / "p4"
        pdir.mkdir()
        LS.set_project_lifecycle(pdir, Lifecycle.DEVELOPMENT)
        with pytest.raises(LS.LifecycleRegressionError, match="生命周期回退拒绝"):
            LS.set_project_lifecycle(pdir, Lifecycle.PRODUCT_DEFINED)
        # canonical 未被降级
        assert json.loads((pdir / "project.json").read_text(encoding="utf-8"))["status"] == Lifecycle.DEVELOPMENT

    def test_force_allows_explicit_exception(self, tmp_path):
        pdir = tmp_path / "p5"
        pdir.mkdir()
        LS.set_project_lifecycle(pdir, Lifecycle.DEVELOPMENT)
        LS.set_project_lifecycle(pdir, Lifecycle.IDEA, force=True)
        assert json.loads((pdir / "project.json").read_text(encoding="utf-8"))["status"] == Lifecycle.IDEA

    def test_legacy_existing_status_not_blocked(self, tmp_path):
        """旧词汇 canonical (prd_ready) → engineering_ready 等价推进不阻断。"""
        pdir = tmp_path / "p6"
        pdir.mkdir()
        _write_project(pdir, status="prd_ready")
        LS.set_project_lifecycle(pdir, Lifecycle.ENGINEERING_READY)
        assert json.loads((pdir / "project.json").read_text(encoding="utf-8"))["status"] == Lifecycle.ENGINEERING_READY

    def test_corrupt_project_json_fail_safe(self, tmp_path):
        """project.json 损坏 → LifecycleStoreError (不覆盖损坏文件, 不臆造)。"""
        pdir = tmp_path / "p7"
        pdir.mkdir()
        (pdir / "project.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(LS.LifecycleStoreError, match="project.json 损坏"):
            LS.set_project_lifecycle(pdir, Lifecycle.DEVELOPMENT)
        assert "{not json" in (pdir / "project.json").read_text(encoding="utf-8")

    def test_corrupt_mirror_fail_safe(self, tmp_path):
        """product.json 损坏 → canonical 仍写 + errors 记录 (镜像跳过不崩)。"""
        pdir = tmp_path / "p8"
        pdir.mkdir()
        (pdir / "product.json").write_text("{bad", encoding="utf-8")
        r = LS.set_project_lifecycle(pdir, Lifecycle.DEVELOPMENT)
        assert r["errors"] and any("product.json" in e for e in r["errors"])
        assert json.loads((pdir / "project.json").read_text(encoding="utf-8"))["status"] == Lifecycle.DEVELOPMENT


# ================================================================== g. board 读取 canonical 优先


class TestBoardCanonicalRead:
    def test_list_prefers_project_json(self, tmp_path):
        """project.json=development + product.json=prd_ready → 列表显示 development。"""
        pdir = tmp_path / "projects" / "riji"
        pdir.mkdir(parents=True)
        _write_project(pdir, status=Lifecycle.DEVELOPMENT)
        _write_product(pdir, name="日记", status="prd_ready")
        rows = BOARD.list_projects(tmp_path)
        row = next(r for r in rows if r["slug"] == "riji")
        assert row["status"] == Lifecycle.DEVELOPMENT

    def test_list_falls_back_to_product_json(self, tmp_path):
        """project.json 缺失 → 回退 product.json.status。"""
        pdir = tmp_path / "projects" / "mojian"
        pdir.mkdir(parents=True)
        _write_product(pdir, name="墨笺", status="prd_ready")
        rows = BOARD.list_projects(tmp_path)
        row = next(r for r in rows if r["slug"] == "mojian")
        assert row["status"] == "prd_ready"

    def test_stage_status_uses_canonical(self, tmp_path):
        """验收阶段判定: canonical=user_acceptance (product 回退值不同) → 验收 ✅。"""
        pdir = tmp_path / "projects" / "acc"
        pdir.mkdir(parents=True)
        _write_project(pdir, status=Lifecycle.USER_ACCEPTANCE)
        _write_product(pdir, status="prd_ready")  # product 漂移回退值
        stages = {s["id"]: s for s in BOARD._project_stage_status(tmp_path, "acc")}
        assert stages["acceptance"]["done"] is True


# ================================================================== h. 回归 (全链三处一致)


class TestLifecycleChainRegression:
    def test_full_chain_three_tracks_consistent(self, tmp_path):
        """create_product → prepare → approve → execute → accept: 每步三处一致。"""
        root = tmp_path / "ws"
        root.mkdir()
        slug = "crm"
        pdir = root / "projects" / slug
        pdir.mkdir(parents=True)
        _write_product(pdir, name="CRM", status=Lifecycle.PRODUCT_DEFINED)
        ctx = _ctx(root, slug)

        # prepare_project → pending_arch_review (gate 值, 双写一致)
        result = ACTIONS.prepare_project(ctx)
        assert result.ok, result.message
        pj, pd, _ = _three_tracks(pdir)
        assert pj == pd == "pending_arch_review"

        # approve → execution_ready (统一入口, 三处一致)
        intent = INT.IntentObject(
            intent_type="approve_project_plan", params={},
            metadata={"confirm_fn": lambda: "y"},
        )
        ctx2 = ACT.ExecutionContext(
            workspace=root, session=ctx.session, user="user", project=slug, intent=intent
        )
        res = ACTIONS.approve_project_plan(ctx2)
        assert res.ok, res.message
        pj, pd, _ = _three_tracks(pdir)
        assert pj == pd == Lifecycle.EXECUTION_READY

        # execute (假 executor 全成功) → user_acceptance (停在待验收, 不自动交付)
        _write_project(pdir, status=Lifecycle.EXECUTION_READY)  # 审批门已过
        (pdir / "execution_plan.json").write_text(
            json.dumps({"tasks": [
                {"id": "t1", "name": "T1", "agent_type": "backend", "agent": "backend-1"},
            ], "count": 1}),
            encoding="utf-8",
        )

        def ok_fn(task, project_dir, workspace):
            return {"success": True, "artifact": f"art-{task.get('id')}", "cost": "0.01"}

        orch = ORCH.ExecutionOrchestrator(root)
        ex = orch.execute_project(slug, execute_fn=ok_fn)
        assert ex.failed_tasks == 0
        pj, pd, es = _three_tracks(pdir)
        assert pj == pd == es == Lifecycle.USER_ACCEPTANCE, (pj, pd, es)

        # accept → delivered (三处一致)
        assert orch.accept_project(slug) is True
        pj, pd, es = _three_tracks(pdir)
        assert pj == pd == es == Lifecycle.DELIVERED, (pj, pd, es)

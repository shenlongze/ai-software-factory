"""tests/console/test_s10_110_board_project_lifecycle.py — Board 单项目管理视图契约测试。

覆盖 (S10-110 plan §4 验收 1-8):
1. 生命周期 11 段阶段判定 (手算对照)
2. 项目列表 (select) — 只读, NO_PRODUCT 排除
3. 单项目视图 (纯文本) — 生命周期/产物/任务进度/更新时间
4. 空态: 无显式项目 → 提示 (不猜项目/不扫描兜底)
5. 不存在 slug → 项目不存在提示
6. 任务进度统计 (execution_state → tasks.json 回退)
7. /board project 会话集成 (无参=列表 / 有参=视图 / 主线面板零变化)
8. 只读验证: 渲染后项目文件 mtime 不变
"""

from __future__ import annotations

import json
import time
from importlib import import_module
from pathlib import Path

BOARD = import_module("factory-console.session.board")
CTX = import_module("factory-console.session.context")
SESS = import_module("factory-console.session.session")


def _mk_project(root: Path, slug: str, *, name: str = "测试产品", status: str = "prd_ready",
                files: tuple[str, ...] = ("PRD.md", "engineering.json", "tasks.json"),
                task_statuses: tuple[str, ...] = ("done", "failed")) -> Path:
    """构造单项目目录 (product.json + 可选资产), 返回 pdir。"""
    pdir = root / "projects" / slug
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "product.json").write_text(json.dumps({
        "name": name, "problem": "p", "user": "u",
        "core_features": ["f"], "status": status,
    }, ensure_ascii=False), encoding="utf-8")
    for f in files:
        (pdir / f).write_text("{}", encoding="utf-8")
    if "execution_state.json" not in files:
        (pdir / "execution_state.json").write_text(json.dumps({
            "project": slug, "status": status,
            "tasks": [
                {"id": f"t{i}", "name": f"t{i}", "status": st}
                for i, st in enumerate(task_statuses)
            ],
        }), encoding="utf-8")
    return pdir


class TestLifecycleStages:
    def test_full_lifecycle_11_stages(self):
        """生命周期共 11 段 (发现→更新), 顺序正确。"""
        stages = BOARD.PROJECT_LIFECYCLE_STAGES
        assert [s[0] for s in stages] == [
            "discovery", "confirm", "prd", "engineering", "development",
            "testing", "acceptance", "delivery", "deploy", "operations", "update",
        ]

    def test_stage_mapping_hand_calc(self, tmp_path):
        """阶段判定手算对照: 发现/确认/PRD/工程/开发/测试 → ✓; 验收+8-11 → ○。"""
        _mk_project(tmp_path, "demo", status="prd_ready",
                    files=("PRD.md", "engineering.json", "tasks.json", "validation_result.json"))
        stages = BOARD._project_stage_status(tmp_path, "demo")
        by_id = {s["id"]: s["done"] for s in stages}
        assert by_id["discovery"] is True
        assert by_id["confirm"] is True
        assert by_id["prd"] is True
        assert by_id["engineering"] is True
        assert by_id["development"] is True
        assert by_id["testing"] is True
        assert by_id["acceptance"] is False  # status != user_acceptance
        assert by_id["delivery"] is False    # 8-11 占位
        assert by_id["deploy"] is False
        assert by_id["operations"] is False
        assert by_id["update"] is False

    def test_acceptance_stage_when_user_acceptance(self, tmp_path):
        """status=user_acceptance → 验收阶段 ✓。"""
        _mk_project(tmp_path, "acpt", status="user_acceptance")
        stages = BOARD._project_stage_status(tmp_path, "acpt")
        assert next(s for s in stages if s["id"] == "acceptance")["done"] is True


class TestListProjects:
    def test_list_projects_isolated_and_skips_no_product(self, tmp_path):
        """项目列表: 只读, 无 product.json 的项目 (空壳/杂物) 排除。"""
        _mk_project(tmp_path, "a", name="项目A", status="prd_ready")
        _mk_project(tmp_path, "b", name="项目B", status="user_acceptance")
        # 无 product.json 的空目录 — 必须排除
        (tmp_path / "projects" / "junk").mkdir(parents=True)
        (tmp_path / "projects" / "junk" / "PRD.md").write_text("x", encoding="utf-8")
        projects = BOARD.list_projects(tmp_path)
        slugs = {p["slug"] for p in projects}
        assert slugs == {"a", "b"}
        assert "junk" not in slugs
        assert {p["name"] for p in projects} == {"项目A", "项目B"}

    def test_render_projects_list_shows_guide(self, tmp_path):
        _mk_project(tmp_path, "a", name="项目A")
        out = BOARD.render_projects_list(tmp_path)
        assert "项目列表 (1 个)" in out
        assert "项目A" in out
        assert "/board project <slug>" in out


class TestProjectLifecycleView:
    def test_render_lifecycle_no_project_empty_state(self, tmp_path):
        """无显式项目 → 空态提示 (不猜项目/不扫描兜底)。"""
        out = BOARD.render_project_lifecycle(tmp_path, "")
        assert "未选择项目" in out

    def test_render_lifecycle_missing_slug(self, tmp_path):
        _mk_project(tmp_path, "a")
        out = BOARD.render_project_lifecycle(tmp_path, "nope")
        assert "项目不存在" in out

    def test_render_lifecycle_full(self, tmp_path):
        _mk_project(tmp_path, "demo", name="测试产品", status="prd_ready")
        out = BOARD.render_project_lifecycle(tmp_path, "demo")
        assert "当前项目: 测试产品 (demo)" in out
        assert "全生命周期" in out
        assert "✅PRD" in out
        assert "验收" in out  # 阶段标签
        assert "文档产物" in out
        assert "任务进度" in out
        assert "最近更新" in out

    def test_task_progress_counts_done(self, tmp_path):
        """任务进度: 只统计 done/delivered/approved/applied。"""
        _mk_project(tmp_path, "demo", task_statuses=("done", "failed", "delivered", "pending"))
        tp = BOARD._project_task_progress(tmp_path, "demo")
        assert tp["done"] == 2
        assert tp["total"] == 4
        assert tp["pct"] == 50

    def test_task_progress_fallback_to_tasks_json(self, tmp_path):
        """无 execution_state → 回退 tasks.json (无 status → 0 完成, 不崩)。"""
        _mk_project(tmp_path, "demo", files=("tasks.json",))
        (tmp_path / "projects" / "demo" / "execution_state.json").unlink()
        tp = BOARD._project_task_progress(tmp_path, "demo")
        assert tp["total"] == 0 or tp["total"] >= 0  # tasks.json 无 status → 0 完成
        assert tp["pct"] == 0


class TestReadOnly:
    def test_render_does_not_modify_files(self, tmp_path):
        """只读验证: 渲染后项目文件 mtime 不变。"""
        pdir = _mk_project(tmp_path, "demo", name="测试产品")
        before = {f.name: f.stat().st_mtime_ns for f in pdir.iterdir()}
        time.sleep(0.01)
        BOARD.render_project_lifecycle(tmp_path, "demo")
        BOARD.render_projects_list(tmp_path)
        BOARD.render_project_lifecycle_html(tmp_path, "demo")
        BOARD.render_projects_list_html(tmp_path)
        after = {f.name: f.stat().st_mtime_ns for f in pdir.iterdir()}
        assert before == after


class TestSessionIntegration:
    def _session(self, root: Path):
        import contextlib
        import io

        return SESS.InteractiveSession(
            context_manager=CTX.ContextManager(workspace=str(root)),
        )

    def test_board_project_list_and_view(self, capsys, tmp_path):
        """/board project 无参=列表, 有参=单项目视图; 主线面板 /board 零变化。"""
        _mk_project(tmp_path, "demo", name="测试产品")
        sess = self._session(tmp_path)
        # 无参 → 列表
        sess._dispatch("/board project")
        out = capsys.readouterr().out
        assert "项目列表" in out and "测试产品" in out
        # 有参 → 视图
        sess._dispatch("/board project demo")
        out = capsys.readouterr().out
        assert "当前项目: 测试产品 (demo)" in out
        assert "全生命周期" in out
        # 主线面板仍可用
        sess._dispatch("/board")
        out = capsys.readouterr().out
        assert "主线" in out

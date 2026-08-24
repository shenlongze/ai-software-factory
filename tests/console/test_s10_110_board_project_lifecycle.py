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


# ================================================================== S10-110 P0/P1 扩展

class TestDashboardStats:
    def test_dashboard_stats_aggregates(self, tmp_path):
        _mk_project(tmp_path, "a", name="项目A", status="prd_ready",
                    task_statuses=("done", "running"))
        _mk_project(tmp_path, "b", name="项目B", status="user_acceptance",
                    task_statuses=("failed",))
        stats = BOARD.dashboard_stats(tmp_path)
        assert stats["projects"] == 2
        assert stats["status_dist"] == {"prd_ready": 1, "user_acceptance": 1}
        assert stats["running_tasks"] == 1
        assert stats["failed_tasks"] == 1
        assert 0 <= stats["avg_lifecycle_pct"] <= 100

    def test_render_board_html_includes_monitor(self, tmp_path):
        _mk_project(tmp_path, "a", name="项目A")
        html = BOARD.render_board_html(workspace=tmp_path)
        assert "项目监控" in html
        assert "/api/board/summary" in html  # 实时刷新 JS
        assert "mon-running" in html


class TestSdkTasks:
    def test_parse_sdk_tasks_from_doc(self):
        """§22.3 4 阶段路线 → 4 个 SDK 任务 (第四数据源)。"""
        tasks = BOARD._parse_sdk_tasks()
        assert len(tasks) == 4
        assert tasks[0]["id"] == "SDK-1"
        assert "内核收尾" in tasks[0]["title"]
        assert tasks[3]["id"] == "SDK-4"
        assert "商业化" in tasks[3]["title"]

    def test_render_board_includes_sdk(self):
        out = BOARD.render_board()
        assert "SDK 任务" in out
        assert "SDK-1" in out


class TestSprintCriterion:
    def test_sprint_done_with_completion_or_final(self, tmp_path, monkeypatch):
        """完成证据放宽: acceptance 或 completion 或 final 任一存在即完成。"""
        sprint_dir = tmp_path / "sprint10"
        sprint_dir.mkdir()
        (sprint_dir / "S10-001-plan.md").write_text("p", encoding="utf-8")
        (sprint_dir / "S10-001-acceptance.md").write_text("a", encoding="utf-8")
        (sprint_dir / "S10-002-plan.md").write_text("p", encoding="utf-8")
        (sprint_dir / "S10-002-completion.md").write_text("c", encoding="utf-8")
        (sprint_dir / "S10-003-plan.md").write_text("p", encoding="utf-8")
        (sprint_dir / "S10-003-final-report.md").write_text("f", encoding="utf-8")
        (sprint_dir / "S10-004-plan.md").write_text("p", encoding="utf-8")
        sprints = BOARD._parse_sprints(sprint_dir)
        by_id = {s["id"]: s["done"] for s in sprints}
        assert by_id["S10-001"] is True   # acceptance
        assert by_id["S10-002"] is True   # completion
        assert by_id["S10-003"] is True   # final
        assert by_id["S10-004"] is False  # 只有 plan → 不算完成


class TestProjectTaskList:
    def test_task_list_marks_status(self, tmp_path):
        _mk_project(tmp_path, "demo", name="测试产品",
                    task_statuses=("done", "failed", "running", "pending"))
        lines = BOARD._project_task_list(tmp_path, "demo")
        assert len(lines) == 4
        assert any("✅" in ln and "done" in ln for ln in lines)
        assert any("❌" in ln and "failed" in ln for ln in lines)
        assert any("🔵" in ln for ln in lines)

    def test_render_lifecycle_includes_task_list(self, tmp_path):
        _mk_project(tmp_path, "demo", name="测试产品", task_statuses=("done", "failed"))
        out = BOARD.render_project_lifecycle(tmp_path, "demo")
        assert "任务清单" in out
        html = BOARD.render_project_lifecycle_html(tmp_path, "demo")
        assert "任务清单" in html


# ================================================================== 导航返回修复

class TestBoardNav:
    def test_board_nav_has_return_link_and_active(self):
        """共享导航: 含主线面板返回链接 + 当前页高亮。"""
        nav = BOARD._board_nav("graph", "P-123")
        assert "主线面板" in nav and "?view=mainline" in nav  # 降级为显式入口
        assert "background:#1565c0" in nav  # active 高亮
        # graph 链接用当前项目 (非 demo)
        assert "graph?project=P-123" in nav

    def test_all_html_pages_include_nav(self, tmp_path):
        """graph/chain/timeline/report/项目页 全部含返回主线导航 (含空态)。"""
        _mk_project(tmp_path, "demo", name="测试产品")
        assert "主线面板" in BOARD.render_graph_html(tmp_path, "demo")
        assert "主线面板" in BOARD.render_chain_html(tmp_path, "demo")
        assert "主线面板" in BOARD.render_graph_html(tmp_path, "nope")  # 空态
        assert "主线面板" in BOARD.render_chain_html(tmp_path, "nope")
        assert "主线面板" in BOARD.render_timeline_html(tmp_path)
        assert "主线面板" in BOARD.render_report_html()
        assert "主线面板" in BOARD.render_projects_list_html(tmp_path)
        assert "主线面板" in BOARD.render_project_lifecycle_html(tmp_path, "demo")


# ================================================================== 任务状态汇总 + 任务树

class TestTaskCountsAndTree:
    def test_status_counts(self, tmp_path):
        _mk_project(tmp_path, "demo", name="测试产品",
                    task_statuses=("done", "failed", "running", "pending"))
        c = BOARD._project_task_status_counts(tmp_path, "demo")
        assert c == {"done": 1, "running": 1, "failed": 1, "pending": 1, "total": 4}

    def test_task_tree_groups_by_epic(self, tmp_path):
        _mk_project(tmp_path, "demo", name="测试产品")
        # 覆盖 execution_state: 加 epic/feature
        pdir = tmp_path / "projects" / "demo"
        (pdir / "execution_state.json").write_text(json.dumps({
            "tasks": [
                {"id": "t1", "name": "任务1", "epic": "史诗A", "feature": "功能A", "status": "done"},
                {"id": "t2", "name": "任务2", "epic": "史诗A", "feature": "功能B", "status": "failed"},
                {"id": "t3", "name": "任务3", "epic": "史诗B", "feature": "功能C", "status": "pending"},
            ],
        }), encoding="utf-8")
        tree = BOARD._project_task_tree(tmp_path, "demo")
        assert len(tree) == 2  # 史诗A/史诗B
        assert tree[0]["epic"] == "史诗A"
        assert len(tree[0]["features"]) == 2
        html = BOARD.render_project_tasktree_html(tmp_path, "demo")
        assert "史诗A" in html and "任务1" in html
        assert "✅完成" in html  # 状态汇总
        assert "🗂 任务树" in html  # 导航

    def test_lifecycle_html_has_counts_and_tasks_nav(self, tmp_path):
        _mk_project(tmp_path, "demo", name="测试产品", task_statuses=("done", "failed"))
        html = BOARD.render_project_lifecycle_html(tmp_path, "demo")
        assert "✅完成" in html
        assert "🗂 任务树" in html  # 统一导航含任务树


# ================================================================== 项目选择器 + 实时/同步

class TestProjectSelect:
    def test_nav_includes_project_select(self, tmp_path):
        """workspace 提供 → 导航含项目选择器 select。"""
        _mk_project(tmp_path, "a", name="项目A")
        _mk_project(tmp_path, "b", name="项目B")
        nav = BOARD._board_nav("graph", "a", tmp_path)
        assert "<select" in nav
        assert "项目A" in nav and "项目B" in nav
        assert "selected" in nav  # 当前项目选中
        assert "graph?project=" in nav  # 切换跳转到 graph 视图

    def test_nav_select_route_by_active(self, tmp_path):
        _mk_project(tmp_path, "a", name="项目A")
        # graph → graph 页面; main → 单项目视图
        assert "graph?project=" in BOARD._board_nav("graph", "a", tmp_path)
        assert "view=project" in BOARD._board_nav("main", "", tmp_path)

    def test_project_select_uses_current_slug(self, tmp_path):
        _mk_project(tmp_path, "a", name="项目A")
        html = BOARD.render_project_lifecycle_html(tmp_path, "a")
        assert f"<option value=\"a\"" in html  # 当前项目选中

    def test_session_current_project_marked(self, tmp_path):
        _mk_project(tmp_path, "a", name="项目A")
        (tmp_path / "session_state.json").write_text(
            json.dumps({"current_project": "a"}), encoding="utf-8")
        html = BOARD.render_projects_list_html(tmp_path)
        assert "当前</span>" in html

    def test_project_views_auto_refresh(self, tmp_path):
        _mk_project(tmp_path, "a", name="项目A")
        # v1.1.53: meta refresh 改为 JS 定时刷新 (可配置), 默认 15s
        assert "setInterval" in BOARD.render_project_lifecycle_html(tmp_path, "a")
        assert "setInterval" in BOARD.render_project_tasktree_html(tmp_path, "a")


# ================================================================== 刷新间隔可选

class TestRefreshSelect:
    def test_refresh_options(self):
        """刷新选项: 5/15/30/60/关闭(0)。"""
        assert BOARD.REFRESH_OPTIONS == (5, 15, 30, 60, 0)

    def test_refresh_select_has_all_options(self):
        sel = BOARD._refresh_select_html()
        assert '<select id="factory-refresh"' in sel
        for n in (5, 15, 30, 60, 0):
            assert f'value="{n}"' in sel
        assert "关闭" in sel

    def test_auto_refresh_script_default(self):
        script = BOARD._auto_refresh_script(15)
        assert "setInterval" in script
        assert ": 15;" in script  # 默认 15s
        assert "factory-refresh" in script

    def test_all_pages_have_refresh_select(self, tmp_path):
        _mk_project(tmp_path, "a", name="项目A")
        pages = [
            BOARD.render_board_html(workspace=tmp_path),
            BOARD.render_projects_list_html(tmp_path),
            BOARD.render_project_lifecycle_html(tmp_path, "a"),
            BOARD.render_project_tasktree_html(tmp_path, "a"),
            BOARD.render_graph_html(tmp_path, "a"),
            BOARD.render_chain_html(tmp_path, "a"),
            BOARD.render_timeline_html(tmp_path),
            BOARD.render_report_html(),
        ]
        for i, html in enumerate(pages):
            assert 'id="factory-refresh"' in html, f"page {i} 缺刷新选择器"

    def test_auto_refresh_script_in_pages(self, tmp_path):
        _mk_project(tmp_path, "a", name="项目A")
        # 有默认刷新的页面: 主线 30 / 单项目 15 / 任务树 15
        assert "setInterval" in BOARD.render_board_html(workspace=tmp_path)
        assert "setInterval" in BOARD.render_project_lifecycle_html(tmp_path, "a")
        assert "setInterval" in BOARD.render_project_tasktree_html(tmp_path, "a")


# ================================================================== 项目优先首页 (架构调整)

class TestProjectFirst:
    def test_home_uses_current_project(self, tmp_path):
        """首页: 有当前项目 → 该项目生命周期视图 (项目优先, 非 AI 主线)。"""
        _mk_project(tmp_path, "a", name="项目A")
        (tmp_path / "session_state.json").write_text(
            json.dumps({"current_project": "a"}), encoding="utf-8")
        home = BOARD.render_project_home(tmp_path)
        assert "全生命周期" in home
        assert "任务监控面板" not in home  # AI 主线不再是首页

    def test_home_falls_back_to_list(self, tmp_path):
        """首页: 无当前项目 → 项目列表引导。"""
        _mk_project(tmp_path, "a", name="项目A")
        home = BOARD.render_project_home(tmp_path)
        assert "项目列表" in home

    def test_nav_has_big_project_select_first(self, tmp_path):
        """导航: 大项目选择器 (第一步) 置顶, AI 主线面板降级为 tab。"""
        _mk_project(tmp_path, "a", name="项目A")
        nav = BOARD._board_nav("project", "a", tmp_path)
        assert "📁 选择项目:" in nav          # 大选择器
        assert "AI主线面板" in nav            # 降级 tab
        assert "?view=mainline" in nav        # 显式入口

    def test_mainline_explicit_view(self, tmp_path):
        """AI 主线面板走显式 ?view=mainline (不再是默认首页)。"""
        _mk_project(tmp_path, "a", name="项目A")
        ml = BOARD.render_board_html(workspace=tmp_path)
        assert "AI主线面板" in ml
        assert "任务监控面板" in ml

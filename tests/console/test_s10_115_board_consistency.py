"""tests/console/test_s10_115_board_consistency.py — Board 状态一致性对账契约测试 (J-1 可见化)。

覆盖:
1. 三轨一致 → not drifted
2. 漂移检出: product.json != project.json → drifted (日记实测场景)
3. project.json 缺失 → missing 标记, canonical 回退 product.json
4. 损坏文件 → 失败安全 (视为缺失, 不崩)
5. canonical 优先级: project.json.status 优先于 product.json.status
6. dashboard_stats 一致性聚合 (drifted/missing_project_json)
7. 只读验证: 对账后文件 mtime 不变
"""

from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path

BOARD = import_module("factory-console.session.board")


def _mk(root: Path, slug: str, *, project: str | None = None,
        product: str | None = None, exec_state: str | None = None,
        name: str = "测试产品") -> Path:
    """构造项目目录 (按需写三轨状态文件)。"""
    pdir = root / "projects" / slug
    pdir.mkdir(parents=True, exist_ok=True)
    if product is not None:
        (pdir / "product.json").write_text(json.dumps(
            {"name": name, "status": product}, ensure_ascii=False), encoding="utf-8")
    if project is not None:
        (pdir / "project.json").write_text(json.dumps(
            {"name": name, "status": project}, ensure_ascii=False), encoding="utf-8")
    if exec_state is not None:
        (pdir / "execution_state.json").write_text(json.dumps(
            {"status": exec_state, "lifecycle": exec_state}), encoding="utf-8")
    return pdir


class TestProjectStateConsistency:
    def test_all_consistent(self, tmp_path):
        """三轨一致 → not drifted, canonical=project.json。"""
        _mk(tmp_path, "ok", project="development", product="development", exec_state="development")
        c = BOARD.project_state_consistency(tmp_path, "ok")
        assert c["canonical"] == "development"
        assert c["drifted"] is False
        assert c["missing"] == []

    def test_drift_detected(self, tmp_path):
        """漂移检出: product.json=prd_ready vs project.json=development (日记实测场景)。"""
        _mk(tmp_path, "drift", project="development", product="prd_ready", exec_state="development")
        c = BOARD.project_state_consistency(tmp_path, "drift")
        assert c["canonical"] == "development"
        assert c["product"] == "prd_ready"
        assert c["drifted"] is True

    def test_missing_project_json_fallback(self, tmp_path):
        """project.json 缺失 → missing 标记, canonical 回退 product.json (墨笺实测场景)。"""
        _mk(tmp_path, "nopj", product="prd_ready")
        c = BOARD.project_state_consistency(tmp_path, "nopj")
        assert "project" in c["missing"]
        assert c["canonical"] == "prd_ready"
        assert c["drifted"] is False

    def test_canonical_precedence(self, tmp_path):
        """canonical 优先级: project.json 存在时覆盖 product.json。"""
        _mk(tmp_path, "prec", project="execution_ready", product="prd_ready")
        c = BOARD.project_state_consistency(tmp_path, "prec")
        assert c["canonical"] == "execution_ready"
        assert c["drifted"] is True

    def test_damaged_files_failure_safe(self, tmp_path):
        """损坏文件 → 视为缺失 (不崩, 不臆造)。"""
        pdir = _mk(tmp_path, "bad", project="development", product="prd_ready")
        (pdir / "product.json").write_text("{ not json !!", encoding="utf-8")
        (pdir / "execution_state.json").write_text("@@@", encoding="utf-8")
        c = BOARD.project_state_consistency(tmp_path, "bad")
        assert "product" in c["missing"]
        assert "exec" in c["missing"]
        assert c["drifted"] is False  # 无法判定 → 不误标

    def test_no_state_files(self, tmp_path):
        """无任何状态文件 → canonical 空, 不崩。"""
        _mk(tmp_path, "empty")
        c = BOARD.project_state_consistency(tmp_path, "empty")
        assert c["canonical"] == ""
        assert c["drifted"] is False
        assert sorted(c["missing"]) == ["exec", "product", "project"]


class TestDashboardConsistency:
    def test_dashboard_stats_aggregate(self, tmp_path):
        """dashboard_stats 一致性聚合: 漂移数与缺 project.json 数准确。"""
        _mk(tmp_path, "drift", project="development", product="prd_ready")
        _mk(tmp_path, "nopj", product="prd_ready")
        _mk(tmp_path, "ok", project="development", product="development")
        s = BOARD.dashboard_stats(tmp_path)
        assert s["consistency"]["checked"] == 3
        assert s["consistency"]["drifted"] == 1
        assert s["consistency"]["missing_project_json"] == 1
        assert len(s["drifted_projects"]) == 1
        assert s["drifted_projects"][0]["slug"] == "drift"

    def test_status_dist_uses_canonical(self, tmp_path):
        """状态分布读 canonical (project.json 优先), 而非 product.json。"""
        _mk(tmp_path, "drift", project="development", product="prd_ready")
        _mk(tmp_path, "ok", project="execution_ready", product="execution_ready")
        s = BOARD.dashboard_stats(tmp_path)
        assert s["status_dist"].get("development") == 1
        assert s["status_dist"].get("prd_ready") is None  # canonical 覆盖漂移值
        assert s["status_dist"].get("execution_ready") == 1

    def test_read_only_no_mtime_change(self, tmp_path):
        """只读验证: 对账/渲染后文件 mtime 不变。"""
        pdir = _mk(tmp_path, "ro", project="development", product="prd_ready")
        files = [pdir / "project.json", pdir / "product.json"]
        before = [f.stat().st_mtime_ns for f in files]
        BOARD.project_state_consistency(tmp_path, "ro")
        BOARD.dashboard_stats(tmp_path)
        BOARD.render_project_lifecycle_html(tmp_path, "ro")
        after = [f.stat().st_mtime_ns for f in files]
        assert before == after

    def test_project_view_shows_consistency_card(self, tmp_path):
        """项目视图含状态一致性卡 (漂移可见, J-1 可见化)。"""
        _mk(tmp_path, "drift", project="development", product="prd_ready", exec_state="development")
        html = BOARD.render_project_lifecycle_html(tmp_path, "drift")
        assert "状态一致性" in html
        assert "状态漂移" in html
        assert "prd_ready" in html

    def test_mainline_shows_drift_warning(self, tmp_path):
        """主线监控面板显示漂移警告与明细。"""
        _mk(tmp_path, "drift", project="development", product="prd_ready", name="漂移项目")
        html = BOARD.render_board_html(workspace=tmp_path)
        assert "状态一致性" in html
        assert "漂移" in html
        assert "漂移项目" in html


class TestListProjectsCanonical:
    def test_list_projects_uses_canonical(self, tmp_path):
        """项目列表状态读 canonical (project.json 优先), 列表页不显示漂移值。"""
        _mk(tmp_path, "drift", project="development", product="prd_ready", name="漂移项目")
        projects = BOARD.list_projects(tmp_path)
        assert projects[0]["status"] == "development"
        assert projects[0]["name"] == "漂移项目"

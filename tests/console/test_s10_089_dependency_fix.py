"""S10-089 — 依赖修复中文句式 + 版本升级回归测试。

覆盖:
1. "升级 requests 到 2.32.0" → 解析 + 生成升级 patch (中文句式)
2. 同名但版本升级 → 更新 (非幂等误判)
3. 完全等于目标 → 幂等
4. 无法解析 → skipped (诚实)
"""

from __future__ import annotations

from importlib import import_module

BS = import_module("factory-console.session.workloads.backlog_sweeper")


def _sweep(requirements: str, title: str, issue_type: str = "dependency"):
    import json
    import tempfile
    from pathlib import Path

    ws = Path(tempfile.mkdtemp())
    proj = ws / "repo"
    proj.mkdir()
    (proj / "requirements.txt").write_text(requirements, encoding="utf-8")
    (proj / "issues.json").write_text(
        json.dumps([{"id": "ISS-1", "title": title, "type": issue_type}]),
        encoding="utf-8",
    )
    report = BS.BacklogSweeper(ws).sweep(proj)
    return report, proj


class TestChineseUpgrade:
    def test_upgrade_with_version_cn(self):
        """'升级 requests 到 2.32.0' → fixed + patch 含新版本。"""
        report, proj = _sweep("requests==2.31.0\n", "升级 requests 到 2.32.0")
        assert report.fixed == 1, report.summary_text()
        # 证据包落盘在 ws/projects/repo/evidence/ (EvidenceStore 路径)
        import json
        ws_ev = proj.parent / "projects" / "repo" / "evidence"
        evs = list(ws_ev.glob("ev-*.json"))
        assert evs, "证据包未生成"
        bundle = json.loads(evs[0].read_text(encoding="utf-8"))
        assert "2.32.0" in (bundle.get("diff") or "")

    def test_same_name_version_upgrade(self):
        """同名但版本低 → 更新 (非幂等误判)。"""
        report, _ = _sweep("requests==2.31.0\n", "升级 requests 到 2.32.0")
        assert report.fixed == 1

    def test_already_satisfied_idempotent(self):
        """已完全等于目标 → 幂等 (无变更, 非 failed)。"""
        report, _ = _sweep("requests==2.32.0\n", "升级 requests 到 2.32.0")
        assert report.fixed == 0
        assert report.skipped == 1

    def test_unparseable_skipped_honest(self):
        """无法解析 → skipped (诚实, 非 stub)。"""
        report, _ = _sweep("flask==2.0.0\n", "把那个啥弄一下")
        assert report.skipped == 1
        assert report.failed == 0

    def test_cn_no_version_pins(self):
        """'升级 requests' 无版本 → pin (>=默认)。"""
        report, _ = _sweep("requests\n", "升级 requests")
        assert report.fixed == 1 or report.skipped == 1  # pin 或已满足均合法

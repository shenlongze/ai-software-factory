"""tests/console/test_s10_116_campaign_plan.py — 战役规划 (K 系列) 契约测试。

覆盖:
1. 待办清单 K 系列分组可被 board 解析 (K-1~K-10, 全部未完成)
2. 战役规划文档存在且含总览/验收标准
3. board 主线面板渲染战役卡片
4. K 系列与旧编号映射不丢失 (A~J + M 仍可解析)
"""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

BOARD = import_module("factory-console.session.board")

ROOT = Path(__file__).resolve().parents[2]
BACKLOG = ROOT / "docs" / "sprint10" / "待办清单-已发现未落地.md"
CAMPAIGN_DOC = ROOT / "docs" / "战役规划-统一路线.md"


class TestCampaignBacklog:
    def test_k_series_parsed(self):
        """K-1~K-10 全部解析; K-1 已交付 ✅, K-2~K-10 未完成 (实事求是)。"""
        groups = BOARD._parse_backlog(BACKLOG)
        g = next((x for x in groups if x["id"] == "战役规划"), None)
        assert g is not None, "待办清单缺战役规划分组"
        ids = [t["id"] for t in g["tasks"]]
        assert ids == [f"K-{i}" for i in range(1, 11)]
        by_id = {t["id"]: t for t in g["tasks"]}
        # S10-116 (v1.1.85): K-1 能力路由+员工管理已交付
        # S10-117 (v1.1.86): K-2 执行质量分+优选已交付
        assert by_id["K-1"]["done"] is True
        assert by_id["K-2"]["done"] is True
        assert all(by_id[f"K-{i}"]["done"] is False for i in range(3, 11))

    def test_campaign_doc_exists_with_acceptance(self):
        """战役规划文档存在, 含总览 + 每战役验收标准。"""
        text = CAMPAIGN_DOC.read_text(encoding="utf-8")
        assert "## 1. 战役总览" in text
        assert "验收" in text
        assert "K-1" in text and "K-10" in text

    def test_old_ids_still_parsed(self):
        """合并不丢失旧编号: A~J/M 系列仍可解析 (可追溯)。"""
        groups = BOARD._parse_backlog(BACKLOG)
        all_ids = [t["id"] for g in groups for t in g["tasks"]]
        for sample in ("M4-1", "B-1", "A-2", "J-2", "P0-1"):
            assert sample in all_ids, f"{sample} 从待办清单丢失"

    def test_board_html_renders_campaign_card(self):
        """board 主线面板渲染战役卡片 (10 项, 未完成)。"""
        html = BOARD.render_board_html(path=BACKLOG)
        assert "战役规划" in html
        assert "K-1" in html
        assert "K-10" in html

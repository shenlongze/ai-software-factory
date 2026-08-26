"""tests/console/test_docs_with_status.py — 文档完成状态查询 (v1.1.145)。

Founder 实测: 会话问 "dosc/products 完成的怎么样了" 全是"未查询到"。
修复验证 (board.list_docs_with_status + query_engine 触发/子路径):
- list_docs_with_status: 子目录过滤 (docs/products) + 解析 md 头部 "状态:" 行
- dosc→docs 宽容拼写; 无状态行 → "" (诚实不臆造)
- query_engine: docs/dosc/products 触发 project_docs; 子路径提取
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

_board = importlib.import_module("factory-console.session.board")
_qe = importlib.import_module("factory-console.session.query_engine")

DOCS_ROOT_HEADER = "> 版本: 0.1 (可立项) | 日期: 2026-08-24 | 状态: {status}\n"


def _setup(tmp_path: Path, slug: str = "p-docs") -> Path:
    """建 workspace + docs_config(dirs=docsroot) + docs/products/*.md (带状态行)。"""
    workspace = tmp_path / "workspace"
    pdir = workspace / "projects" / slug
    pdir.mkdir(parents=True, exist_ok=True)
    docsroot = tmp_path / "repo"
    (docsroot / "docs" / "products").mkdir(parents=True)
    specs = {
        "agent-orchestration-product-spec.md": "内核已实现（M2/M3）",
        "backlog-sweeper-product-spec.md": "MVP 内核已实现（M1b）",
        "channel-platform-product-spec.md": "设计完整, 实现 0（P2）",
        "no-status-doc.md": "",
    }
    for name, status in specs.items():
        (docsroot / "docs" / "products" / name).write_text(
            DOCS_ROOT_HEADER.format(status=status) + "\n# 规格\n", encoding="utf-8"
        )
    (docsroot / "docs" / "other.md").write_text("# 其他\n", encoding="utf-8")
    (pdir / "docs_config.json").write_text(
        json.dumps({"dirs": [str(docsroot)], "exts": [".md"]}), encoding="utf-8"
    )
    return workspace


class TestListDocsWithStatus:
    def test_subpath_filter_and_status(self, tmp_path):
        ws = _setup(tmp_path)
        docs = _board.list_docs_with_status(ws, "p-docs", subpath="docs/products")
        names = {d["name"]: d["status"] for d in docs}
        assert "docs/products/agent-orchestration-product-spec.md" in names
        assert names["docs/products/agent-orchestration-product-spec.md"] == "内核已实现（M2/M3）"
        assert names["docs/products/backlog-sweeper-product-spec.md"] == "MVP 内核已实现（M1b）"
        # 无状态行 → "" (诚实)
        assert names["docs/products/no-status-doc.md"] == ""
        # 目录外文档不过滤进来
        assert not any("other.md" in n for n in names)

    def test_dosc_typo_tolerated(self, tmp_path):
        ws = _setup(tmp_path)
        docs = _board.list_docs_with_status(ws, "p-docs", subpath="dosc/products")
        assert len(docs) == 4  # 8→4 (docs/products 4 个)

    def test_no_subpath_returns_all(self, tmp_path):
        ws = _setup(tmp_path)
        docs = _board.list_docs_with_status(ws, "p-docs")
        assert len(docs) == 5  # docs/products 4 + docs/other.md 1


class TestQueryEngineDocs:
    def test_trigger_words(self):
        for q in ("看看 docs", "dosc/products 状态", "products 文档", "有哪些文档"):
            assert _qe.parse_intent(q)["intent"] == "project_docs", q

    def test_subpath_extraction(self):
        assert _qe._docs_subpath("我想看看 每一个独立的 dosc/products，现在完成的怎么样了") == "docs/products"
        assert _qe._docs_subpath("docs/products 状态") == "docs/products"
        assert _qe._docs_subpath("有哪些文档") == ""

"""tests/console/test_s10_123_k6_rag.py — S10-123 K-6 项目级 RAG 契约测试 (≥10)。

覆盖 (设计 §2 契约 1-10 + 实测面):
1. KnowledgeStore 入库: 索引独立目录 .factory_rag, 零污染项目文件
2. 检索命中: 文件+片段可解释 (reason 含关键词/文件)
3. 三级分档: raw/summary/knowledge 各 ≥1 命中
4. 问答 CLI: factory rag query 确定性片段 + 引用源
5. 增量更新: mtime 变更 → 只重扫变更文件 (旧块移除, 未变更保留)
6. 外挂适配器: Protocol + Mock (search/ping) + 注册表; 未配置 → 空不崩
7. E-5: RAG_QUERY 审计事件带 trace_id (K-4 contextvar)
8. 失败安全: 损坏文档/二进制 → 跳过 + 不中断
9. 注册表门禁: factory rag 子命令在 build_parser; API 路由存在
10. 排序确定性: 同输入同输出 (词频打分稳定)
11. API 实测: POST /api/rag/query + GET /api/rag/sources (TestClient)
12. rag_query 外部源合并: tier=external + source 诚实标注

装配: importlib (factory-console 包名含连字符) + tmp_path hermetic;
fastapi/httpx 未安装 → API 类跳过 (同既有 console API 测试模式)。
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:  # factory-console/ 的父目录 (含连字符包名)
    sys.path.insert(0, str(_ROOT))
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))

KS = importlib.import_module("factory-console.retrieval.knowledge_store")
EXT = importlib.import_module("factory-console.retrieval.external_source")
TRACE = importlib.import_module("factory-console.audit.trace_context")
EMITTER = importlib.import_module("factory-console.audit.audit_emitter")
EVENT = importlib.import_module("factory-console.audit.audit_event")
CLI = importlib.import_module("factory-console.cli_factory")
CFG = importlib.import_module("factory-console.config")

try:
    from fastapi.testclient import TestClient  # noqa: E402

    _HAS_FASTAPI = True
except Exception:  # noqa: BLE001
    TestClient = None  # type: ignore[assignment,misc]
    _HAS_FASTAPI = False

requires_fastapi = pytest.mark.skipif(
    not _HAS_FASTAPI, reason="fastapi/httpx 未安装 (console 侧 venv 需安装)"
)


# ================================================================== fixture 装配


def _write(path: Path, content: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")


def make_project(ws: Path, slug: str = "demo") -> Path:
    """三级分档 fixture 项目: raw (README/PRD 段落) + summary (标题行) +
    knowledge (json/经验)。"""
    pdir = ws / "projects" / slug
    _write(pdir / "product.json", json.dumps(
        {"name": "Demo 项目", "problem": "支付系统稳定性问题"}, ensure_ascii=False))
    _write(pdir / "README.md",
           "# Demo 项目\n\n安装依赖后运行 python main.py 启动支付网关\n\n部署指南见 docs。\n")
    _write(pdir / "PRD.md",
           "# 需求文档\n\n## 支付流程\n\n用户提交订单后进入支付流程。\n")
    _write(pdir / "engineering.json", json.dumps(
        {"技术栈": ["python", "fastapi"], "架构": "微服务", "部署": "容器化部署"},
        ensure_ascii=False))
    _write(pdir / "docs" / "lessons.md",
           "# 经验\n\n经验: 支付系统超时重试三次。\n")
    return pdir


def make_cli(tmp_path: Path, data_dir: Path):
    """hermetic FactoryCLI: config.json 指向 data_dir, 零环境依赖 (同 cli_structure)。"""
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps({"core": {"data_dir": str(data_dir)}}), encoding="utf-8"
    )
    config = CFG.ConfigProvider(
        user_config_file=cfg_file, env_file=tmp_path / ".env", environ={}
    )
    root = tmp_path / "repo"
    root.mkdir()
    return CLI.FactoryCLI(config, root=root)


class _ConfigShim:
    """极简 config shim (providers.external_rag 配置注入测试)。"""

    def __init__(self, external_rag: object = None) -> None:
        self._external_rag = external_rag

    def get(self, section: str, key: str, default=None):
        if section == "providers" and key == "external_rag":
            return self._external_rag
        return default


# ================================================================== 契约 1-2: 入库 + 检索命中


class TestIngestAndQuery:
    def test_ingest_creates_index_zero_pollution(self, tmp_path):
        """契约 1: 入库 → 索引独立目录 .factory_rag; 项目目录零污染。"""
        ws = tmp_path / "ws"
        pdir = make_project(ws)
        store = KS.KnowledgeStore(ws, "demo")
        result = store.ingest()
        assert result.files_scanned >= 5
        assert result.chunks_indexed > 0
        assert store.index_path.is_file(), "索引应生成于 workspace/.factory_rag/<slug>/index.json"
        assert not (pdir / ".factory_rag").exists(), "项目文件零污染 (索引不在项目内)"
        assert ".factory_rag" in str(store.index_path)
        index = json.loads(store.index_path.read_text(encoding="utf-8"))
        assert index["slug"] == "demo"
        assert index["version"] == 1
        assert index["chunks"]

    def test_query_hits_file_and_fragment_explainable(self, tmp_path):
        """契约 2: 查询 → 命中 文件+片段, reason 含关键词/文件 (可解释)。"""
        ws = tmp_path / "ws"
        make_project(ws)
        store = KS.KnowledgeStore(ws, "demo")
        store.ingest()
        hits = store.query("支付网关", top_k=5)
        assert hits, "应命中支付网关相关片段"
        hit = hits[0]
        assert hit.file and hit.fragment
        assert hit.chunk_id
        assert 0.0 < hit.score <= 1.0
        assert "文件" in hit.reason and "关键词" in hit.reason
        assert hit.file in hit.reason

    def test_query_empty_question_returns_empty(self, tmp_path):
        """空问题 → 空命中 (不崩)。"""
        ws = tmp_path / "ws"
        make_project(ws)
        store = KS.KnowledgeStore(ws, "demo")
        store.ingest()
        assert store.query("") == []
        assert store.query("   ") == []

    def test_query_no_index_returns_empty(self, tmp_path):
        """未入库 → 空命中 (提示先 index, 不崩)。"""
        ws = tmp_path / "ws"
        make_project(ws)
        store = KS.KnowledgeStore(ws, "demo")
        assert store.query("支付") == []


# ================================================================== 契约 3: 三级分档


class TestTiers:
    def _store(self, tmp_path):
        ws = tmp_path / "ws"
        make_project(ws)
        store = KS.KnowledgeStore(ws, "demo")
        store.ingest()
        return store

    def test_tiers_each_at_least_one_hit(self, tmp_path):
        """契约 3: raw/summary/knowledge 三级各 ≥1 命中。"""
        store = self._store(tmp_path)
        raw = store.query("支付网关", tiers=["raw"], top_k=5)
        summary = store.query("支付流程", tiers=["summary"], top_k=5)
        knowledge = store.query("技术栈", tiers=["knowledge"], top_k=5)
        assert raw, "raw 分档应命中 (README/PRD 段落)"
        assert summary, "summary 分档应命中 (PRD 标题行)"
        assert knowledge, "knowledge 分档应命中 (engineering.json / lessons.md)"
        assert {h.tier for h in raw} == {"raw"}
        assert {h.tier for h in summary} == {"summary"}
        assert {h.tier for h in knowledge} == {"knowledge"}

    def test_tier_filter_excludes_other_tiers(self, tmp_path):
        """tiers 过滤: 只查指定分档 (其余分档同问题也可能命中, 但被过滤)。"""
        store = self._store(tmp_path)
        raw_only = store.query("支付", tiers=["raw"], top_k=20)
        assert all(h.tier == "raw" for h in raw_only)
        all_tiers = store.query("支付", top_k=20)
        assert {h.tier for h in all_tiers} >= {"raw", "summary"}

    def test_lessons_doc_is_knowledge_tier(self, tmp_path):
        """经验文档 (lessons.md) 段落 → knowledge 分档 (F-11 知识沉淀)。"""
        store = self._store(tmp_path)
        hits = store.query("超时重试", tiers=["knowledge"], top_k=5)
        assert any("lessons.md" in h.file for h in hits)


# ================================================================== 契约 4: 问答 CLI


class TestCliQuery:
    def test_rag_query_cli_deterministic_output(self, tmp_path, capsys):
        """契约 4: factory rag query → 确定性片段 + 引用源 (文件+片段+score+reason)。"""
        data_dir = tmp_path / "data"
        make_project(data_dir)
        cli = make_cli(tmp_path, data_dir)
        assert cli.run(CLI.build_parser().parse_args(["rag", "index", "demo"])) == 0
        rc = cli.run(CLI.build_parser().parse_args(
            ["rag", "query", "demo", "支付网关", "--top-k", "3"]))
        out = capsys.readouterr().out
        assert rc == 0
        assert "RAG 查询" in out
        assert "文件:" in out
        assert "片段:" in out
        assert "score=" in out
        assert "reason:" in out
        assert "支付网关" in out

    def test_rag_query_cli_requires_project_and_question(self, tmp_path, capsys):
        """缺项目/问题 → rc 2 明确用法 (不崩)。"""
        data_dir = tmp_path / "data"
        make_project(data_dir)
        cli = make_cli(tmp_path, data_dir)
        rc = cli.run(CLI.build_parser().parse_args(["rag", "query", "", ""]))
        out = capsys.readouterr().out
        assert rc == 2
        assert "用法" in out

    def test_rag_query_cli_unknown_project_rc1(self, tmp_path, capsys):
        """项目不存在 → rc 1 明确提示。"""
        data_dir = tmp_path / "data"
        cli = make_cli(tmp_path, data_dir)
        rc = cli.run(CLI.build_parser().parse_args(["rag", "query", "ghost", "支付"]))
        out = capsys.readouterr().out
        assert rc == 1
        assert "项目不存在" in out

    def test_rag_index_cli(self, tmp_path, capsys):
        """factory rag index → 入库输出 (扫描/块/分档/索引路径)。"""
        data_dir = tmp_path / "data"
        make_project(data_dir)
        cli = make_cli(tmp_path, data_dir)
        rc = cli.run(CLI.build_parser().parse_args(["rag", "index", "demo"]))
        out = capsys.readouterr().out
        assert rc == 0
        assert "RAG 索引" in out
        assert "索引块" in out
        assert ".factory_rag" in out
        assert (data_dir / ".factory_rag" / "demo" / "index.json").is_file()

    def test_rag_sources_cli_empty_not_crash(self, tmp_path, capsys):
        """factory rag sources 未配置/未注册 → 空不崩。"""
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)
        cli = make_cli(tmp_path, data_dir)
        rc = cli.run(CLI.build_parser().parse_args(["rag", "sources"]))
        out = capsys.readouterr().out
        assert rc == 0
        assert "外部知识源" in out
        assert "未配置" in out or "无已注册" in out


# ================================================================== 契约 5: 增量更新


class TestIncremental:
    def test_incremental_only_rescans_changed(self, tmp_path):
        """契约 5: mtime 变更文件 → 只重扫变更 (旧块移除, 未变更保留, 无变更空)。"""
        ws = tmp_path / "ws"
        pdir = make_project(ws)
        store = KS.KnowledgeStore(ws, "demo")
        first = store.ingest()
        assert first.chunks_indexed > 0

        # 无变更 → changed_files 空 (不重扫)
        noop = store.incremental_ingest()
        assert noop.changed_files == []
        assert noop.chunks_indexed == first.chunks_indexed

        # 变更 README → 只重扫 README
        readme = pdir / "README.md"
        readme.write_text("# Demo 项目\n\n新的部署说明: 使用 docker compose 启动支付网关。\n",
                          encoding="utf-8")
        inc = store.incremental_ingest()
        assert inc.changed_files == ["README.md"], f"只应重扫 README: {inc.changed_files}"
        assert inc.removed_files == []

        # README 旧块移除 + 新块保留; 其他文件块未动
        index = store._load_index()
        readme_chunks = [c for c in index["chunks"] if c["file"] == "README.md"]
        assert all("安装依赖后运行" not in c["fragment"] for c in readme_chunks), "旧 README 块应移除"
        assert any("docker compose" in c["fragment"] for c in readme_chunks), "新 README 块应保留"
        assert any(c["file"] == "docs/lessons.md" for c in index["chunks"])

    def test_incremental_removed_file_chunks_dropped(self, tmp_path):
        """删除文件 → 增量后其块移除。"""
        ws = tmp_path / "ws"
        pdir = make_project(ws)
        store = KS.KnowledgeStore(ws, "demo")
        store.ingest()
        (pdir / "README.md").unlink()
        inc = store.incremental_ingest()
        assert inc.removed_files == ["README.md"]
        index = store._load_index()
        assert all(c["file"] != "README.md" for c in index["chunks"])

    def test_incremental_no_index_falls_back_full(self, tmp_path):
        """索引缺失 → 增量退化为全量 (失败安全)。"""
        ws = tmp_path / "ws"
        make_project(ws)
        store = KS.KnowledgeStore(ws, "demo")
        result = store.incremental_ingest()
        assert result.incremental is True
        assert result.chunks_indexed > 0
        assert store.index_path.is_file()


# ================================================================== 契约 6: 外挂适配器


class TestExternalSource:
    def setup_method(self):
        EXT.clear_external_sources()

    def teardown_method(self):
        EXT.clear_external_sources()

    def test_mock_protocol_search_and_ping(self):
        """契约 6a: MockExternalSource search/ping 可跑 (确定性)。"""
        src = EXT.MockExternalSource(name="mock", corpus={"部署": "部署方式: make deploy"})
        hits = src.search("部署", top_k=5)
        assert hits and hits[0]["content"] == "部署方式: make deploy"
        assert hits[0]["source"] == "部署"
        assert hits[0]["score"] == 0.9
        assert src.search("部署", top_k=5) == src.search("部署", top_k=5)  # 确定性
        assert src.ping() is True
        assert EXT.MockExternalSource(alive=False).ping() is False

    def test_register_and_get_sources(self):
        """契约 6b: 注册表 register/get (按 name 排序, 后注册覆盖)。"""
        EXT.register_external_source(EXT.MockExternalSource(name="b", corpus={}))
        EXT.register_external_source(EXT.MockExternalSource(name="a", corpus={}))
        names = [s.name for s in EXT.get_external_sources()]
        assert names == ["a", "b"]

    def test_unconfigured_returns_empty_not_crash(self):
        """契约 6c: 未配置 providers.external_rag → 空不崩。"""
        assert EXT.configured_external_sources(None) == []
        assert EXT.configured_external_sources(_ConfigShim(external_rag=None)) == []

    def test_configured_filters_registered(self):
        """配置 providers.external_rag → 只返回已注册且命中的源。"""
        EXT.register_external_source(EXT.MockExternalSource(name="pg", corpus={}))
        EXT.register_external_source(EXT.MockExternalSource(name="vector", corpus={}))
        configured = EXT.configured_external_sources(_ConfigShim(external_rag=["pg"]))
        assert [s.name for s in configured] == ["pg"]
        assert EXT.configured_external_sources(_ConfigShim(external_rag="pg,missing"))[0].name == "pg"


# ================================================================== 契约 7: E-5 检索回路


class TestAuditTrace:
    def test_rag_query_emits_audit_event_with_trace_id(self, tmp_path):
        """契约 7: RAG_QUERY 审计事件带 trace_id (K-4 contextvar 自动填充)。"""
        ws = tmp_path / "ws"
        make_project(ws)
        KS.KnowledgeStore(ws, "demo").ingest()
        assert "RAG_QUERY" in EVENT.EVENT_TYPES, "RAG_QUERY 应在 EVENT_TYPES 注册"
        with TRACE.trace_context("trace-rag-123"):
            hits, stats = KS.rag_query(ws, "demo", "支付网关", top_k=3)
        assert hits
        audit_file = ws / "audit" / "audit_events.json"
        assert audit_file.is_file(), "RAG_QUERY 应落盘 audit_events.json"
        events = json.loads(audit_file.read_text(encoding="utf-8"))
        rag_events = [e for e in events if e.get("event_type") == "RAG_QUERY"]
        assert rag_events, "应存在 RAG_QUERY 事件"
        assert rag_events[-1]["trace_id"] == "trace-rag-123"
        assert rag_events[-1]["project_id"] == "demo"

    def test_rag_query_audit_failure_safe(self, tmp_path):
        """审计发射异常 → 检索结果不受影响 (失败安全)。"""
        ws = tmp_path / "ws"
        make_project(ws)
        KS.KnowledgeStore(ws, "demo").ingest()

        class _BrokenEmitter:
            def emit(self, *a, **k):
                raise RuntimeError("audit broken")

        hits, stats = KS.rag_query(ws, "demo", "支付网关", top_k=3, emitter=_BrokenEmitter())
        assert hits, "审计故障不阻断检索"


# ================================================================== 契约 8: 失败安全


class TestFailSafe:
    def test_bad_document_skipped_not_abort(self, tmp_path):
        """契约 8: 损坏文档/二进制 → 跳过 + 记录, 不中断其余入库。"""
        ws = tmp_path / "ws"
        pdir = make_project(ws)
        _write(pdir / "docs" / "broken.md", b"\xff\xfe\x00 broken bytes \xff")
        _write(pdir / "docs" / "manual.docx", b"PK\x03\x04 fake binary docx")
        store = KS.KnowledgeStore(ws, "demo")
        result = store.ingest()  # 不应抛
        assert result.skipped, "损坏文档应记录 skipped"
        reasons = {s["file"]: s["reason"] for s in result.skipped}
        assert "docs/broken.md" in reasons
        assert "docs/manual.docx" in reasons
        assert result.chunks_indexed > 0, "其余文档正常入库"
        # 正常文件仍可检索
        hits = store.query("支付网关", top_k=3)
        assert hits


# ================================================================== 契约 9: 注册表门禁


class TestRegistry:
    def test_rag_subcommands_in_build_parser(self):
        """契约 9a: factory rag + query/index/sources 在 build_parser。"""
        parser = CLI.build_parser()
        args = parser.parse_args(["rag", "query", "demo", "q"])
        assert args.command == "rag"
        assert args.rag_action == "query"
        assert parser.parse_args(["rag", "index", "demo"]).rag_action == "index"
        assert parser.parse_args(["rag", "sources"]).rag_action == "sources"
        # --help 退出 0
        with pytest.raises(SystemExit) as exc:
            parser.parse_args(["rag", "--help"])
        assert exc.value.code == 0

    @requires_fastapi
    def test_api_rag_routes_registered(self, tmp_path):
        """契约 9b: API 路由 /api/rag/query + /api/rag/sources 存在。"""
        adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")
        root = tmp_path / "factory"
        root.mkdir()
        from events.logger import EventLogger
        from events.store import EventStore

        logger = EventLogger(EventStore(root / "events.db"))
        service = adapter.build_console_service(root, event_logger=logger)
        app = adapter.build_app(service, event_logger=logger, factory_root=root)
        paths = {r.path for r in app.routes}
        assert "/api/rag/query" in paths
        assert "/api/rag/sources" in paths


# ================================================================== 契约 10: 排序确定性


class TestDeterminism:
    def test_same_input_same_output(self, tmp_path):
        """契约 10: 同输入同输出 (词频打分稳定, 排序稳定)。"""
        ws = tmp_path / "ws"
        make_project(ws)
        store = KS.KnowledgeStore(ws, "demo")
        store.ingest()
        a = [h.to_dict() for h in store.query("支付网关 超时重试", top_k=10)]
        b = [h.to_dict() for h in store.query("支付网关 超时重试", top_k=10)]
        assert a == b
        assert a == sorted(a, key=lambda h: (-h["score"], h["file"], h["chunk_id"]))
        scores = [h["score"] for h in a]
        assert scores == sorted(scores, reverse=True), "score 降序"

    def test_score_monotonic_with_term_frequency(self):
        """词频单调: 更多命中词 → 更高 score (确定性)。"""
        s1, _, _ = KS._tf_score("部署支付系统", "部署支付")
        s2, _, _ = KS._tf_score("部署部署部署 支付支付 系统", "部署支付")
        assert s2 > s1 > 0


# ================================================================== 契约 11-12: API 实测 + 外部源合并


@requires_fastapi
class TestApiEndpoints:
    def _client(self, tmp_path):
        adapter = importlib.import_module("factory-console.web.backend.fastapi_adapter")
        root = tmp_path / "factory"
        make_project(root)
        from events.logger import EventLogger
        from events.store import EventStore

        logger = EventLogger(EventStore(root / "events.db"))
        service = adapter.build_console_service(root, event_logger=logger)
        app = adapter.build_app(service, event_logger=logger, factory_root=root)
        return TestClient(app)

    def test_api_rag_query_endpoint(self, tmp_path):
        """POST /api/rag/query: 入库后查询 → 命中片段 + 引用源。"""
        with self._client(tmp_path) as client:
            # 先入库
            from importlib import import_module as _im
            KS2 = _im("factory-console.retrieval.knowledge_store")
            KS2.KnowledgeStore(tmp_path / "factory", "demo").ingest()
            resp = client.post("/api/rag/query", json={
                "project": "demo", "question": "支付网关", "top_k": 3})
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert data["hits"], "应命中"
            hit = data["hits"][0]
            assert hit["file"] and hit["fragment"] and hit["reason"]
            assert data["stats"]["local_hits"] >= 1
            # 未入库项目 → 空命中不崩
            resp2 = client.post("/api/rag/query", json={
                "project": "ghost", "question": "支付"})
            assert resp2.status_code == 200
            assert resp2.json()["hits"] == []

    def test_api_rag_query_validation(self, tmp_path):
        """POST /api/rag/query: 缺 project/question → 400。"""
        with self._client(tmp_path) as client:
            assert client.post("/api/rag/query", json={"question": "x"}).status_code == 400
            assert client.post("/api/rag/query", json={"project": "demo"}).status_code == 400

    def test_api_rag_sources_endpoint(self, tmp_path):
        """GET /api/rag/sources: 未配置 → 空不崩 (ok + configured=[])。"""
        with self._client(tmp_path) as client:
            resp = client.get("/api/rag/sources")
            assert resp.status_code == 200
            data = resp.json()
            assert data["ok"] is True
            assert data["configured"] == []
            assert "sources" in data


class TestRagQueryExternal:
    def test_rag_query_merges_external_source(self, tmp_path):
        """rag_query 外部源合并: tier=external + source 诚实标注 (M5-3)。"""
        ws = tmp_path / "ws"
        make_project(ws)
        src = EXT.MockExternalSource(name="mock", corpus={"部署": "部署方式: make deploy"})
        hits, stats = KS.rag_query(ws, "demo", "部署", top_k=5, external_sources=[src])
        assert stats["external_hits"] >= 1
        ext = [h for h in hits if h.tier == "external"]
        assert ext, "外部源命中应合并进结果"
        assert ext[0].source == "external:mock"
        assert "外部源 mock 命中" in ext[0].reason
        assert ext[0].file.startswith("external:mock:")

    def test_external_source_failure_safe(self, tmp_path):
        """外部源 search 抛异常 → 跳过, 本地检索不受影响 (失败安全)。"""
        ws = tmp_path / "ws"
        make_project(ws)
        KS.KnowledgeStore(ws, "demo").ingest()

        class _BrokenSource:
            name = "broken"

            def search(self, query, top_k):
                raise RuntimeError("external broken")

            def ping(self):
                return False

        hits, stats = KS.rag_query(ws, "demo", "支付网关", top_k=5, external_sources=[_BrokenSource()])
        assert hits
        assert stats["external_hits"] == 0

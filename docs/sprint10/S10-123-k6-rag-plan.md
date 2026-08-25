# S10-123 — K-6 项目级 RAG：设计文档 + 实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-25 | 前置: v1.1.95 · K-1~K-5 ✅ (战役第六战役)
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-123 提示词（K-6: M5-2/3 + B-8 + F-11 + E-5）

---

## 0. 现状审计（CTO 独立复核）

| 资产 | 现状 | K-6 用途 |
|---|---|---|
| board 文档管理 | read_docs_config (docs_config: dirs+exts) + render_project_docs_html ✅ | KnowledgeStore 扫描复用, 不重造 |
| retrieval 编排 | retriever.py (Retriever 协议 + Experience/Audit/ProjectRetriever) + unified.py (RetrievalOrchestrator: Policy/Dedup/Rank/Top-K/Budget) ✅ | RAG 检索复用编排语义 |
| RetrievalSource | models.py EXTERNAL_RAG 预留扩展点 ✅ | M5-3 外挂适配器挂点 |
| 向量库 | 无自建向量/embedding ❌ | M5-2 自建 (渐进: 规则优先) |
| 问答入口 | 无 CLI/API ❌ | factory rag query + API |
| 经验检索 | ExperienceStore + retrieve_experience (K-3) ✅ | RAG 复用 (跨来源编排) |

版本: 1.1.95 → 目标 1.1.96 (HEAD+1; K-7b 先行消耗则顺延)。

## 1. 架构决策

### 1.1 M5-2/B-8 KnowledgeStore（核心, 新模块 `factory-console/retrieval/knowledge_store.py`）

```python
class KnowledgeStore:
    def __init__(self, workspace, slug): ...
    def ingest(self) -> IngestResult:
        # 复用 board read_docs_config (dirs + exts) 扫描项目文档
        # (README/docs/PRD/engineering/质量/经验 → 片段分块 (按段落/标题)
        # → 索引: {chunk_id, file, start, content, tier} — 索引存独立目录
        #   (workspace/.factory_rag/<slug>/index.json) — 零污染项目文件
        # 失败安全: 单个文件损坏 → 跳过 + 记录, 不中断
    def incremental_ingest(self) -> IngestResult:
        # mtime 变更文件 → 增量重建 (只重扫变更文件)
    def query(self, question: str, *, tiers=None, top_k=5) -> list[KnowledgeHit]:
        # 确定性检索: 词频/TF-IDF 打分 (纯规则, 零外部依赖)
        # → 三级分档命中 (raw 原始文档片段 / summary 摘要 / knowledge 知识条目)
        # → KnowledgeHit{chunk_id, file, fragment, score, tier, reason}
        # reason 可解释: "命中关键词 X (tf=3) in file Y 片段 Z"
class KnowledgeHit:  # 引用源可解释
    chunk_id, file, fragment, score, tier, reason
```

- RAG 分档: 一级=原始文档 (片段) · 二级=摘要/索引 (目录/章节摘要) · 三级=知识条目 (跨文档沉淀)
- embedding/LLM 可选: 接入真实 embedding → 诚实标注; 规则检索始终可用 (降级不崩)

### 1.2 M5-3 外挂适配器（接口先行, 新模块 `factory-console/retrieval/external_source.py`）

```python
class ExternalKnowledgeSource(Protocol):
    name: str
    def search(self, query: str, top_k: int) -> list[dict]   # {content, source, score}
    def ping(self) -> bool

class MockExternalSource(ExternalKnowledgeSource):
    # 确定性 Mock — 可跑可断言; 真实接入 (Postgres/向量库) 后续, 诚实标注

def register_external_source(source) -> None    # 注册表
def get_external_sources() -> list[...]          # 可配置 (config providers)
```

- 复用 RetrievalSource.EXTERNAL_RAG (models.py 预留挂点)
- 配置: config providers.external_rag = [...] — 未配置 → 空 (不崩)

### 1.3 问答入口

- CLI: `factory rag query <项目> <问题> [--tiers raw,summary,knowledge] [--top-k N]`
  - 确定性输出: 命中片段 + 引用源 (文件+片段+score) + reason
  - `factory rag index <项目>` — 显式入库/增量重建
  - `factory rag sources` — 查看已注册外部源 (接口就绪状态)
- API: POST /api/rag/query (复用已有 fastapi 路由风格) + GET /api/rag/sources
- board 文档页搜索增强: 可选 (与 K-7b 前端并行 — 只做后端 API, 不碰 web/frontend)

### 1.4 E-5 检索回路（可溯源）

- KnowledgeStore.query / 外部源检索动作 → 审计事件 (RAG_QUERY) 带 trace_id (K-4 contextvar)

### 1.5 注册表门禁（P0-10/11）

- `factory rag` 子命令 → build_parser 同步; 新 API 路由 → 注册表核对

## 2. 契约测试（tests/console/test_s10_123_k6_rag.py, ≥10）

1. **KnowledgeStore 入库**: fixture 项目文档 → 索引生成 (独立目录, 零污染项目文件)
2. **检索命中**: 查询 → 命中 文件+片段 (可解释, reason 含文件/关键词)
3. **分档**: raw/summary/knowledge 三级各 ≥1 命中 (fixture 构造三档内容)
4. **问答 CLI**: factory rag query 返回确定性片段 + 引用源
5. **增量更新**: 文档变更 → incremental_ingest 只重扫变更 (mtime fixture)
6. **外挂适配器**: 接口 + 注册 + Mock 可跑 (search/ping); 未配置 → 空不崩
7. **E-5**: 检索动作审计事件带 trace_id
8. **失败安全**: 损坏文档 → 跳过 + 不中断
9. **注册表**: factory rag 在 build_parser; API 路由存在
10. **排序确定性**: 同输入同输出 (词频打分稳定)
11. 全量回归 0 新增失败

## 3. 版本与发布

- pyproject `1.1.95` → `1.1.96`; CHANGELOG v1.1.96; 版本断言同步; docs/FEATURES.md;
  docs/sprint10/待办清单-已发现未落地.md: K-6 L22 ✅ + M5-2 L73 ✅ + M5-3 L74 ✅ + B-8 L137 ✅ +
  F-11 L198 ✅ + E-5 L179 ✅

## 4. Codex 实施范围

**Allowed/Files**:
- NEW `factory-console/retrieval/knowledge_store.py` (KnowledgeStore + KnowledgeHit + 三级分档 + 词频检索 + 增量)
- NEW `factory-console/retrieval/external_source.py` (ExternalKnowledgeSource + Mock + 注册表)
- MOD `factory-console/cli_factory.py` (factory rag query|index|sources — 注册表同步)
- MOD `factory-console/web/backend/fastapi_adapter.py` (POST /api/rag/query + GET /api/rag/sources)
- MOD `factory-console/retrieval/unified.py` 或 models.py (ExternalSource 接入 RetrievalOrchestrator 可选 — 接口打通)
- MOD `factory-console/audit/audit_event.py` (RAG_QUERY 事件类型, 若缺) — E-5 检索回路
- NEW `tests/console/test_s10_123_k6_rag.py`（≥10 契约: 设计 §2 的 1-10）
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / docs/FEATURES.md / docs/sprint10/待办清单-已发现未落地.md

**Forbidden（硬边界）**:
- 只动后端 (factory-console/retrieval|memory + cli + api + tests); **禁碰 web/frontend** (K-7b 并行)
- 纯规则确定性为主; LLM/embedding 仅可选且诚实标注 (规则检索始终可用)
- 复用 board 文档管理扫描 (read_docs_config) + retrieval 编排, 不重造
- 索引独立目录 (.factory_rag), 不污染项目文件; 不调 LLM 做唯一检索依据
- 禁 git add -A; 禁新增第三方依赖 (TF-IDF/词频手写)

**Validation**:
- `pytest tests/console/test_s10_123_k6_rag.py -q` 全绿
- env -u 聚焦 (retrieval/cli/api + 既有 retrieval/board 测试) 全绿
- env -u 全量 console+api 0 新增失败 (并发 K-7b 未提交改动隔离验证)
- 实测: 入库 → 查询命中 (文件+片段) → 三级分档 → 增量 → 外部源 Mock → trace 溯源
- commit: `feat(S10-123): K-6 项目级RAG — KnowledgeStore三级分档+确定性检索+factory rag问答+外部源接口+E-5溯源, v1.1.96`

## 5. 验收标准（Hermes 独立验证）

- [ ] 1. KnowledgeStore 入库 → 检索命中 文件+片段 (可解释)
- [ ] 2. 三级分档各 ≥1 fixture
- [ ] 3. factory rag query 返回确定性片段 + 引用源
- [ ] 4. 外挂适配器: 接口 + 配置 + Mock 可跑 (真实接入如实标注)
- [ ] 5. E-5: 检索动作带 trace_id
- [ ] 6. 增量更新 fixture
- [ ] 7. 契约测试 ≥10 全绿
- [ ] 8. 全量回归 0 新增失败
- [ ] 9. v1.1.96 + K-6/M5-2/3/B-8/F-11/E-5 ✅
- [ ] 10. 设计文档落盘

## 6. 诚实记录要求

- embedding/外挂真实接入未做 → 如实标注 (接口就绪, 真实待后续)
- 无法确定性检索的文档类型 → 如实标注
- 与 K-7b 前端零冲突 (只动后端文件)

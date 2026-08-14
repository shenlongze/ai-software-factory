# S10-028 Task 005 — Project RAG Architecture Research

> 日期:2026-08-14 | Sprint: S10-028 Platform Architecture Freeze | 架构研究,未实现
> 目标:设计 AI Factory 自动创建项目级 RAG 的完整架构

---

## 1. 目标

用户导入项目 → AI Factory 自动分析 → 自动生成 embedding pipeline / vector index / metadata schema / retrieval strategy → 用户选择内置或外部向量库。

## 2. 核心流程

```
用户导入项目 (git repo / 目录)
    ↓
① Project Analyzer (自动分析)
    ├── repo structure (目录树/包结构)
    ├── language (语言检测: py/ts/js/java/go...)
    ├── docs (文档: README/API/设计)
    ├── code (代码: 函数/类/模块)
    ├── dependency (依赖: requirements/package.json/pom...)
    └── issue (Issue/需求历史, 可选)
    ↓
② Index Planner (自动规划)
    ├── embedding pipeline (分块策略/embedding 模型)
    ├── vector index (schema/collection)
    ├── metadata schema (语言/路径/类型/依赖)
    └── retrieval strategy (检索策略: 语义/关键词/混合)
    ↓
③ Storage Choice (用户选择)
    ├── Factory Managed RAG (内置, 零依赖)
    └── External: Chroma / Qdrant / Milvus / Pinecone / Weaviate
    ↓
④ Ingestion (索引构建)
    ↓
⑤ Query (检索服务 /api/rag/query)
```

## 3. Project Analyzer(自动分析)

### 3.1 分析输出(ProjectProfile)

```python
class ProjectProfile:
    project_id: str
    languages: dict[str, float]          # {python: 0.6, js: 0.3, ...} 按文件占比
    structure: dict[str, Any]            # 目录树摘要 (深度受限)
    entry_points: list[str]              # 入口文件 (main/__init__/index)
    doc_files: list[str]                 # 文档文件清单
    dependency_files: list[str]          # 依赖清单文件
    dependencies: dict[str, str]         # 解析后的依赖 {name: version}
    domain: str | None                   # 领域猜测 (可选, 后续)
```

### 3.2 检测规则(确定性,非 AI)

| 维度 | 检测方式 |
|---|---|
| language | 扩展名统计(可复用 repo_index.py 已有能力) |
| structure | 目录树遍历(深度限制,忽略 .git/node_modules/venv) |
| entry_points | 常见入口模式(main.py/index.js/go.mod...) |
| docs | 文档文件(md/rst/adoc/ipynb) |
| dependency | requirements.txt/package.json/pom.xml/go.mod/Cargo.toml 解析 |
| issue | 可选:导入 issue 导出文件 |

## 4. Index Planner(自动规划)

### 4.1 分块策略(按语言/文件类型)

| 文件类型 | 分块策略 |
|---|---|
| 代码 (.py/.ts/.js...) | 按函数/类/模块边界分块(比固定 token 好) |
| 文档 (.md/.rst) | 按标题层级分块 |
| 配置 (.json/.yaml) | 小文件整块;大文件按顶层键 |
| 混合 | 默认: 代码按 AST 边界, 文档按标题 |

### 4.2 向量索引 schema

```python
class RAGIndexSchema:
    collection: str              # af_project_<project_id>
    embedding_model: str         # 默认 text-embedding-3-small (可换)
    chunk_size: int              # 默认 512
    chunk_overlap: int           # 默认 64
    metadata_fields: list[str]   # [language, file_path, file_type, chunk_type, dependencies]
    vector_dim: int              # 由 embedding model 决定
```

### 4.3 检索策略(默认 + 可配置)

```
默认: 混合检索 (语义 70% + 关键词 30%, 按 project 过滤)
  - 语义: vector search (embedding 相似度)
  - 关键词: metadata filter (language/file_type/路径前缀)
可选: 纯语义 / 纯关键词 / RRF 融合
```

## 5. Storage Choice(内置 vs 外部)

### 5.1 Factory Managed RAG(内置,零依赖)

```python
class ManagedVectorStore:
    """内置向量库: SQLite + numpy (零外部依赖, 适合中小项目)。"""
    # 数据: ~/.factory/rag/<project_id>/
    #   chunks.json   (文本块 + metadata)
    #   vectors.npy   (embedding 矩阵)
    #   index.sqlite  (检索索引)
    # 能力: upsert / query(k, filter) / delete
    # 限制: 单机, 内存加载 (项目 < ~100MB 文本)
```

**内置选型理由**:v1 零依赖(符合"不引入无必要依赖");中小项目足够;外部库留给进阶用户。

### 5.2 External Vector DB(用户选择)

| 引擎 | 部署 | 适合 | 集成方式 |
|---|---|---|---|
| Chroma | 本地嵌入 | 开发/小型 | HTTP / 嵌入式 Python |
| Qdrant | 本地/容器 | 中大型 | REST API |
| Milvus | 集群 | 大规模 | gRPC |
| Pinecone | 云托管 | 生产无运维 | REST API |
| Weaviate | 本地/云 | 语义搜索 | REST API |

```python
# 统一适配器 (Extension Contract — Task 003 RAGExtension)
class VectorStoreAdapter(Protocol):
    def upsert(self, chunks: list[Chunk]) -> None: ...
    def query(self, vector: list[float], k: int,
              filters: dict) -> list[ScoreChunk]: ...
    def delete(self, project_id: str) -> None: ...
    def info(self) -> dict: ...   # 集合/维度/计数
```

## 6. 模块架构(未来)

```
factory-console/rag/               # 或独立 factory-rag 包
├── analyzer.py        Project Analyzer (结构/语言/依赖检测)
├── planner.py         Index Planner (分块/embedding/schema 规划)
├── chunker.py         分块器 (代码 AST / 文档标题)
├── embedder.py        Embedding 封装 (OpenAI/本地模型)
├── store.py           Vector Store 选择 + 适配器工厂
├── stores/
│   ├── managed.py     Factory Managed (SQLite+numpy)
│   └── chroma.py / qdrant.py / ... (外部适配器, 可选依赖)
├── retriever.py       检索策略 (混合/语义/关键词)
└── service.py         RAG 服务 (CLI + API)
```

## 7. 与 Kernel 的衔接

| 衔接点 | 设计 |
|---|---|
| 身份 | RAG 索引按 project_id 隔离(af://project/<id>) |
| 配置 | rag.yaml(embedding 模型/分块/存储选择) |
| 事件 | rag.indexed / rag.queried 审计事件 |
| 扩展 | RAGExtension 契约(Task 003)— 存储/embedding/retriever 可插拔 |
| 入口 | CLI factory rag index/query + API /api/rag/* |

## 8. 实现路径(分阶段)

```
Phase 1 (最小): Managed RAG 内置
  - analyzer (语言/结构/文档) + chunker + embedder + managed store
  - CLI: factory rag index <project> / factory rag query
  - 依赖: 仅 numpy + 一个 embedding client

Phase 2 (外部库): 适配器层
  - VectorStoreAdapter 契约 + Chroma/Qdrant 适配器
  - rag.yaml 存储选择

Phase 3 (增强): 检索优化
  - 混合检索 / metadata 过滤 / RRF
  - issue/需求导入

Phase 4 (产品): Enterprise Knowledge
  - 跨项目检索 / 权限集成 (Governance) / 审计
```

## 9. 关键设计决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | v1 用 Factory Managed(内置),外部库第二阶段 | 零依赖铁律;中小项目足够 |
| D2 | 分块按代码 AST/文档标题,非固定 token | 检索质量(代码边界语义好) |
| D3 | 默认混合检索(语义+关键词) | 代码检索中精确标识符很重要(纯语义漏精确匹配) |
| D4 | 统一 VectorStoreAdapter 契约 | 外部库可换,符合 Extension Contract |
| D5 | embedding 模型可配置(默认 OpenAI 兼容) | 与 LLM 基础设施一致(ControlPlane 风格) |
| D6 | 审计事件 rag.* | 与 Kernel Event 一致(可回放/治理) |

## 10. 结论

**Project RAG 架构完整**:自动分析 → 自动规划 → 存储选择(内置/外部)→ 索引 → 检索。
- v1 零依赖(Managed RAG),外部向量库第二阶段
- 与 Kernel/Extension Contract 对齐(rag.yaml/rag.* 事件/RAGExtension)
- 实现路径清晰(4 阶段),但**本 Sprint 不实现**(远期产品,排在 Router/Governance 之后)

---

> Task 005 完毕 | Project RAG 架构研究完成 | 只设计,未实现

# S10-123 · K-6 项目级 RAG（M5-2/M5-3 + B-8 + F-11 + E-5）— Hermes 提示词（2026-08-26）

> 战役: K-6（docs/战役规划-统一路线.md §2 K-6）· 目标版本 v1.1.96（当前 HEAD v1.1.95）
> 交付后: 待办清单 K-6/M5-2/M5-3/B-8/F-11/E-5 ✅ · 战役规划状态追踪 K-6 ✅
> 注意: 与 K-7b（5180 前端）并行 — 双方不碰同一批文件（K-6 后端 / K-7b 前端）

---

请作为 Hermes 派发 Sprint 任务给 Codex，遵守既有纪律（pre-flight → plan → dispatch → verify → acceptance → report）。

【任务】S10-123 · K-6 项目级 RAG（战役规划第六战役）
版本目标：v1.1.96（从实际 HEAD +1；若 K-7b 先行消耗则顺延）

【背景（K-6 是什么）】
项目知识可检索、可复用 — "问得深但不懂项目"→ 项目文档问答。
合并项: M5-2 KnowledgeStore + 自建 DB/向量 + RAG 分档 · M5-3 外挂适配器（企业 Postgres/向量库/知识库）·
B-8 项目级 RAG · F-11 项目知识沉淀 · E-5 检索回路。

【现状（实事求是，pre-flight 必须核对，不限于此）】
1. board 文档管理 ✅: 多目录 + 扩展名配置 + 文件树 + 搜索（docs_config.json + render_project_docs_html 已交付）
2. 检索编排 ✅: retrieval/retriever.py Retriever 协议（ExperienceRetriever/AuditRetriever/ProjectRetriever 摘要级）+
   retrieval/unified.py RetrievalOrchestrator（Policy/Dedup/Rank/Top-K/Budget）; ExternalRAGRetriever 是预留扩展点
3. 向量库 ❌: 无自建向量/embedding（M5-2 待做）
4. 问答入口 ❌: 无 CLI/API 项目文档问答
5. 经验检索 ✅: memory/experience_store + retrieve_experience（K-3 已交付）— RAG 可复用其编排语义

【设计与实现要求（先出设计文档 docs/sprint10/S10-123-k6-rag-plan.md，批准后再实现）】
1. M5-2/B-8 KnowledgeStore（核心）:
   - 项目文档入库: README/docs/PRD/工程/质量/经验 → 索引（文件路径 + 片段 + 元数据）;
     复用 board 文档管理扫描（docs_config 目录/扩展名）, 不重造
   - 索引独立目录存储（不污染项目文件）; 文档变更 → 增量重建（失败安全）
   - RAG 分档: 三级（原始文档 → 摘要/索引 → 知识条目）, 命中返回引用源（文件+片段, 可解释）
2. 自建向量/检索（渐进）:
   - 确定性优先: 词频/TF-IDF 或 hash 分桶（无外部依赖, 纯规则可断言）
   - embedding/LLM 可选: 若接真实 embedding, 必须诚实标注 + 规则检索始终可用（降级不崩）
3. M5-3 外挂适配器（接口先行）:
   - 可配置外部向量库/知识库（接口 + 配置 + Mock; 真实接入可选, 诚实标注）
   - 复用 RetrievalSource.EXTERNAL_RAG 预留扩展点
4. 问答入口: `factory rag query <项目> <问题>` + API + board 文档页搜索增强（可解释: 引用源文件+片段）
5. F-11 知识沉淀: 项目文档知识 → 可复用资产（PRD/工程/经验入索引, 跨项目检索可选）
6. E-5 检索回路: 检索引用可溯源（K-4 trace_id 带检索动作）
7. 注册表门禁（P0-10/11）: 新 CLI 命令/意图/API 必须同步注册表

【硬边界】
- 渐进: 先自建索引 + 分档检索 + 问答（核心）; 外挂适配器接口先行（真实接入可选）
- 纯规则确定性为主; LLM/embedding 仅可选且诚实标注（规则检索始终可用）
- 复用 board 文档管理扫描 + retrieval 编排, 不重造
- 不污染项目文件（索引独立目录）; 不调 LLM 做唯一检索依据
- 与 K-7b 前端并行: 只动后端（factory-console/retrieval|memory + cli + api + 测试）, 不碰 web/frontend

【验收标准（独立可验证，非 Codex 自报告）】
1. KnowledgeStore: 项目文档入库 → 检索命中返回 文件+片段（可解释, fixture 断言）
2. 分档: 三级检索可命中（原始/摘要/知识条目, 各 ≥1 fixture）
3. 问答: `factory rag query <项目> <问题>` 返回确定性片段 + 引用源
4. 外挂适配器: 接口 + 配置可注册（Mock 可跑, 真实/未接入如实标注）
5. E-5: 检索动作带 trace_id（可溯源）
6. 增量更新: 文档变更后索引更新（fixture）
7. 契约测试 ≥10
8. 全量回归 0 新增失败（环境性失败如实标注, 与 HEAD 基线对照）
9. 版本 v1.1.96（pyproject + CHANGELOG + FEATURES + 版本断言 + 待办清单 K-6/M5-2/3/B-8/F-11/E-5 ✅ 同步）
10. 设计文档落盘 docs/sprint10/S10-123-k6-rag-plan.md

【诚实记录】embedding/外挂真实接入若未做 → 如实标注（接口就绪, 真实待后续）;
无法确定性检索的文档类型 → 如实标注; 与 K-7b 前端改动零冲突（只动后端文件）

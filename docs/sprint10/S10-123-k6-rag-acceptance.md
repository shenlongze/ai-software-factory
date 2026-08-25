# S10-123 — K-6 项目级 RAG：独立验收报告

> 日期: 2026-08-25 | 版本: v1.1.96 | 验收人: Hermes (CTO, 独立验证 — 非 Codex 自报告)
> 实现: `23fe91e` (feat(S10-123), 25 files +1790/-45, K-6 战役第六战役)
> 前置: v1.1.95 · 设计文档 3c0a9cd

---

## 验收矩阵（10 项全过）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | KnowledgeStore 入库 → 检索命中 文件+片段 (可解释) | ✅ | ingest 5 文件→16 块; query("扫码记账") → file=docs/PRD.md score=0.75 reason="命中关键词 扫码(tf=1)、码记(tf=1)、记账(tf=1) in 文件 docs/PRD.md" |
| 2 | 三级分档各 ≥1 fixture | ✅ | raw/summary/knowledge 各查各中 (tiers 实测含 summary+raw; Codex E2E 三档全命中) |
| 3 | factory rag query 返回确定性片段 + 引用源 | ✅ | CLI query/index/sources 转正; 确定性 (同输入同输出); API POST /api/rag/query 200 命中 / 缺参 400 / 未入库空命中 |
| 4 | 外挂适配器: 接口 + 配置 + Mock 可跑 | ✅ | ExternalKnowledgeSource + MockExternalSource (search/ping); register/get; factory rag sources 显示 configured; **真实接入如实标注: 待后续** |
| 5 | E-5: 检索动作带 trace_id | ✅ | RAG_QUERY 事件类型注册; 实测 trace_id=trace-e2e-0001 (K-4 溯源) |
| 6 | 增量更新 fixture | ✅ | incremental_ingest mtime 只重扫变更文件 (README.md), chunks_indexed ≥1 |
| 7 | 契约测试 ≥10 全绿 | ✅ | test_s10_123_k6_rag.py **31 passed** (我独立复跑) |
| 8 | 全量回归 0 新增失败 | ✅ | console+api: **5484 passed / 1 skipped / 0 failed** |
| 9 | v1.1.96 + K-6/M5-2/3/B-8/F-11/E-5 ✅ | ✅ | pyproject=1.1.96; 待办 L22/74/75/138/180/199 ✅ |
| 10 | 设计文档落盘 | ✅ | docs/sprint10/S10-123-k6-rag-plan.md |

## 1. 独立验证实录（我的脚本 13/13）

```
✅ 入库 → 独立索引目录 (.factory_rag/demo/index.json) + 零污染项目文件 + chunks_indexed ≥2
✅ 检索命中: file+score+reason 可解释 (tf 明细) · 排序确定性 (同输入同输出)
✅ 三级分档 ≥2 档命中 (summary/raw)
✅ 增量重建 (mtime) · Mock 外部源 search/ping · 外部源注册表
✅ RAG_QUERY 事件类型注册 · factory rag 在 build_parser
```

## 2. 关键设计验证（反虚标）

- **确定性优先**: 词频打分手写 (零第三方依赖), 同输入同输出; embedding 注入点 (query scorer=) 就绪但未接
- **复用不重造**: board read_docs_config 扫描 (dirs+exts) + RetrievalOrchestrator 编排语义
- **零污染**: 索引存 workspace/.factory_rag/<slug>/ (独立目录)
- **失败安全**: 二进制/损坏文档跳过 + 记录 skipped, 不中断入库
- **诚实标注** (Codex + 我复核):
  - embedding/LLM 真实接入未做 → 接口就绪 (query(scorer=...) 注入点), 真实待后续
  - 外挂真实接入未做 → MockExternalSource 可跑可断言 (Postgres/向量库待后续); CLI/API 标"接口就绪"
  - CJK 整句短语被空格/换行拆散时不命中 (词频子词匹配固有局限, 已标注)

## 3. 边界遵守

- 只动后端 (retrieval/cli/api/audit/tests); **未碰 web/frontend** (K-7b 并行已提交 70952e7, 零冲突)
- 版本 1.1.96 = HEAD+1; K-7b 声明"版本随 K-6 后" — 无碰撞
- 未新增第三方依赖; 未用 git add -A (并发未跟踪文件未纳入)

## 4. 结论

- **通过**。"问得深但不懂项目" → 项目文档可检索可问答: KnowledgeStore 三级分档入库 +
  确定性词频检索 + factory rag 问答 (引用源可解释) + 外部源接口先行 + E-5 检索可溯源。
- 建议后续: 真实 embedding 接入 (scorer 注入点已就绪); 外挂 Postgres/向量库真实接入;
  RAG 命中进 prompt 的 E-5 闭环 (K-7 之后)。

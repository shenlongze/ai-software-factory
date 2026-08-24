# Memory / RAG / Retrieval 全链路审计

> 代码事实扫描 (2026-08-17)

## 一、当前有几个 Memory / Retrieval?

| 资产 | 位置 | 类型 | 用途 |
|---|---|---|---|
| ExperienceStore | memory/experience_store.json | 经验 Memory | 成功/失败/调试/规划经验 (S10-067) |
| LearningTrace | memory/learning_trace.json | 学习审计 | 学习过程记录 |
| PlanningTrace | projects/<slug>/planning_trace.json | 规划轨迹 | LLM 规划决策 (S10-062) |
| DebugTrace | debug_trace.json | Debug 审计 | Debug 决策 (S10-068) |
| DebugSession | debug_sessions.json | Debug 会话 | Debug 状态 |
| AuditStore | audit/audit_events.json | 审计 | 统一事件 (S10-069) |
| CostLedger | cost/cost_records.json | 成本 | Cost 聚合 |

**Memory 主体: 1 个 ExperienceStore (✅ 无重复存储)**

## 二、Retrieval 现状

| Retriever | 位置 | 生产使用? |
|---|---|---|
| ExperienceRetriever | memory/retrieval.py | ✅ (memory_search) |
| DebugExperienceRetriever | session/debug/debug_memory.py | ✅ (DebugEngine) |
| RetrievalOrchestrator | retrieval/orchestrator.py | ❌ 仅测试 |
| AuditRetriever | retrieval/retriever.py | ❌ 仅测试 |
| ProjectRetriever | retrieval/retriever.py | ❌ 仅测试 |

**重复检索: ⚠️ 3 个 Retriever, Orchestrator 未统一生产使用**

## 三、统一链路逐环节检查

```
User Task → Task Understanding → Retrieval Orchestrator → Candidate Sources
→ Ranking → Dedup → Top-K → Context Budget → LLM → Decision → Action
→ Result → Experience → Learning → Memory
```

| 环节 | 状态 | 证据 |
|---|---|---|
| Task Understanding | ✅ | DebugCase/上下文构建 |
| Retrieval Orchestrator | ⚠️ 已建未用 | 仅测试 |
| Candidate Sources | ⚠️ 3 来源实现 | 未统一调度 |
| Ranking | ⚠️ 各 Retriever 自己排 | 无统一 score |
| Dedup | ✅ Orchestrator 内 | 仅测试路径 |
| Top-K | ✅ 参数化 | 无动态调整 |
| Context Budget | ❌ 未接 LLM | ContextLedger 无生产使用 |
| LLM | ✅ | DeepSeek 真实调用 |
| Decision → Action | ✅ | 治理/执行链 |
| Result → Experience | ⚠️ 手动 | AutoLearner 未接生产 |
| Learning → Memory | ✅ | PatternLearner |

## 四、23 问回答 (核心)

1. **几个 Memory?** 1 个 ExperienceStore (+ 各 Trace 审计, 职责不同)
2. **几个 Retrieval?** 3 个 (Experience/Debug/Audit-Project), Orchestrator 未统一
3. **重复检索?** ⚠️ Debug 用 DebugExperienceRetriever, memory_search 用 ExperienceRetriever — 两套
4. **重复数据?** ❌ 无 (经验唯一存储)
5. **多个 Store?** 1 个 ExperienceStore + 各 Trace (职责分离)
6. **统一 Orchestrator?** ✅ 已建 (S10-070), ❌ 未生产接入
7. **Top-K?** 固定参数 (3-5), 无动态
8. **Score?** confidence 降序 (经验) / 关键词匹配 (Audit) — 无统一
9. **动态 Top-K?** ❌
10. **Context Budget 动态裁剪?** ❌ (ContextLedger 未接)
11. **Dedup?** ✅ (Orchestrator 内, source_type+source_id)
12. **Rerank?** ❌ (仅一次排序)
13. **Discarded 记录?** ✅ (stats.candidates/selected/discarded)
14. **Retrieval cost?** ❌ (无检索成本核算)
15. **外部 RAG 冲突?** 接口预留 (RetrievalSource.EXTERNAL_RAG) — 未接入无冲突
16. **优先级?** 排序规则有 (项目>conf>新鲜>成功), 无显式 Memory/RAG 优先级
17. **项目隔离?** ⚠️ ProjectRetriever 有 project_id 过滤, 未全链
18. **记忆膨胀?** ⚠️ 无衰减/合并 (P2)
19. **过期经验?** ⚠️ 无时间衰减 (P2)
20. **错误经验污染?** ⚠️ 无反馈修正 (P2)
21. **置信度衰减?** ❌
22. **Consolidation?** ❌
23. **闭环?** ⚠️ 部分: 失败→Debug→经验✅; 生产→自动学习❌

## 结论

Memory 存储健康 (1 Store); Retrieval **架构已就位但生产未统一** (最大 P1 风险)。

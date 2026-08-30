# Intelligence Plane Proposal — Memory / Context / Learning / Promotion

> 日期: 2026-08-29 | 设计文档 (S34 交付, 实现于 S35+)

## 1. Evidence / Experience / Memory / Learning 定义 (冻结)
```
Evidence  = Fact (ProductionRun/Verification/Evaluation/Classification — 真实不可变)
Experience = Interpreted Production Lesson (S14/S15 已有: meta sidecar + lineage)
Memory    = Retrievable Knowledge (S35+ 建立: Node/Agent/Workforce/Project/Org/Global scope)
Learning  = Improvement Process (S37+ 建立: Pattern → Candidate → Evaluation → Promotion)
禁止混为一个模型 — 四层严格区分
```

## 2. Memory Contract (S35)
```
Source of Truth = Production Evidence → Experience → Memory (非 Conversation → Memory)
Scope = Query Dimension (非继承树):
  node/agent/workforce/project/organization/global — 查询时显式指定
  Node 不得自动继承上层 Memory (scope 是过滤维度, 非继承)
Memory 必须 Plugin 化:
  Memory Contract (Core) ← Local/Mem0/Letta/Vector/Graph/Enterprise (Plugin)
  Core 管: Scope/Permission/Policy/Governance/Lifecycle/Lineage/Budget
  Plugin 管: Storage/Extraction/Retrieval/Ranking/Compression/Indexing
```

## 3. Context Control Plane (S35 核心)
```
Node → Context Request → Scope Filter → Permission → Policy
→ Retrieval → Ranking → Evidence/Confidence → Temporal/Entity/Semantic signals
→ Token Budget → Compression → Context → LLM
Budget Contract: max_input/memory/artifact/history/tool/output_tokens + estimated_cost
禁止无限 Context; 禁止 get_all_memory
Progressive/JIT Context: Node 判断 Context 是否足够 → 不够 → 请求 Resolver → 增量补充
Context Utility = Expected Decision Value / Token Cost (最大化每 token 有用信息)
```

## 4. Learning Contract (S37)
```
Production Evidence → Experience → Pattern Detection → Learning Candidate
Candidate 类型: Skill/Workflow/Prompt/Context Strategy/Agent Composition/
  Model Routing/Plugin/Policy Candidate/Repair Strategy
Learning 不得直接修改 Production
```

## 5. Promotion Lifecycle (S38, 统一)
```
Candidate → Sandbox → Replay → Evaluation → Experiment → Cost Analysis
→ Safety/Governance → Approval/Policy → Canary → Promotion → Production
Self-Improvement ≠ Uncontrolled Self-Modification
```

## 6. Cost Control (S36 起一级指标)
```
NodeRun 记录: LLM Cost/Input/Output Tokens/Memory Retrieval/Context/Tool/
  Runtime/Recovery/Latency
Quality/Reliability/Cost/Latency/Risk 统一优化框架
目标: Maximize verified outcome per unit cost (非只追成功率)
```

## 7. Sprint 拆分建议 (防返工)
```
S35: Memory Contract + Context Control Plane + Budget (先 Context 后 Memory 的存储实现)
S36: Memory Plugins (Local 首个) + Cost 一级指标
S37: Learning (Pattern → Candidate) + JIT Context
S38: Promotion Lifecycle + Canary
S39: Self-Healing 闭环 (Production 失败 → Learning → Promotion → 修复策略)
S40: Self-Optimization (Experiment-driven workforce 调整)
```
理由: Context Budget 是所有下游 (Memory 检索/LLM 调用) 的约束; 先定 Contract 再实现存储, 避免返工。

# S10-072 — Repository Reality Audit & Capability Gap Matrix

> 日期: 2026-08-17 | Phase 0/1: 先找 Gap, 不假设 Gap
> 方法: 代码事实扫描 (未修改任何代码)

---

## 一、桩/伪成功扫描结果

```
❌ 无新增桩 (S10-071 后):
  - debug_pipeline.py:84 'deterministic repair applied' = 显式测试 seam (生产默认已真实)
  - gap_analyzer.py:220 'not implemented' = 信号词 (预期)
```

## 二、Retrieval Bypass Audit

### 真实调用点 (排除 re.search 误报)

| # | 调用点 | 检索什么 | 经 Orchestrator? | 状态 |
|---|--------|----------|------------------|------|
| 1 | session/actions.py:2036 (memory_search action) | 经验 | ❌ 直接 ExperienceRetriever | **BYPASS** |
| 2 | api/memory.py:132 (memory_search API) | 经验 | ❌ 直接 ExperienceRetriever | **BYPASS** |
| 3 | memory/recommendation.py:43,67,89 | 项目经验推荐 | ❌ 直接 ExperienceRetriever | **BYPASS** |
| 4 | session/debug/debug_pipeline.py:185,269 (DebugRetrievalPolicy) | Debug 经验 | ❌ 直接底层 (S10-071 只统一了 debug_memory) | **BYPASS** |
| 5 | session/debug/debug_memory.py (S10-071 已改) | Debug 经验 | ✅ RetrievalOrchestrator | ✅ 统一 |

**结论**: 生产检索入口 5 处, 仅 1 处经统一 Orchestrator。4 处 BYPASS (3 个生产入口 + 1 个 Debug 内部)。

### Source Selection 现状

- 存在: session/debug/retrieval_policy.py (DebugRetrievalPolicy — 查询构建/来源/排序)
- 缺失: 全局 Retrieval Policy / Source Selection (每次查全部? 实际当前各入口只查自己来源 — 无"全量查询"问题, 但无统一决策)

## 三、Audit 自动覆盖 (7/16 阶段)

| 阶段 | 自动事件 | 状态 |
|------|----------|------|
| IDEA/DISCOVERY | 无 | ❌ |
| PRODUCT | PRODUCT_CREATED | ✅ |
| INTELLIGENCE | PRODUCT_INTELLIGENCE | ✅ |
| PLAN | 无 | ❌ |
| AGENT | 无 | ❌ |
| TASK | TASK_COMPLETED/TASK_FAILED | ✅ (orchestrator) |
| EXECUTION | 无 | ❌ |
| TOOL | 无 | ❌ |
| CODE | 无 | ❌ |
| TEST | 无 | ❌ |
| DEBUG | DEBUG_STARTED | ✅ |
| REPAIR | 无 | ❌ |
| GOVERNANCE | 无 | ❌ |
| REVIEW | REVIEW_APPROVED | ✅ |
| MEMORY | MEMORY_LEARNED | ✅ |
| DELIVERY | PROJECT_DELIVERED | ✅ |

**缺口**: 9/16 阶段无自动事件 (Discovery/Plan/Agent/Execution/Tool/Code/Test/Repair/Governance)

## 四、Memory 自动沉淀

```
✅ execute_project 完成 → AutoLearner (S10-071)
❌ Debug 修复成功/失败 → 自动经验
❌ 重规划 → 自动经验
❌ Delivery → 自动经验
❌ 失败路径 → 自动失败经验
```

## 五、Mock Risk Inventory (初步)

```
105 测试文件含 mock/patch — 需分类:
  A-E (unit/LLM/time/infra mock): 保留 ✅
  F-G (executor/validator mock): S10-071 已治理 (生产默认真实, mock 仅测试 seam)
  H-J (fake success/fake pipeline): 未发现生产路径假成功 (S10-071 已移除)
```

## 六、Capability Gap Matrix (本 Sprint 范围)

| Priority | Gap | Current | Target | Complexity |
|----------|-----|---------|--------|------------|
| P0-A | Retrieval 统一: memory_search (action+API) 经 Orchestrator | BYPASS | 统一入口 | 低 |
| P0-B | Retrieval 统一: recommend 经 Orchestrator | BYPASS | 统一入口 | 低 |
| P0-C | Retrieval 统一: DebugPipeline 经 Orchestrator | BYPASS | 统一入口 | 低 |
| P0-D | Audit 自动: Plan/Task 执行/Agent 级事件 | 缺 9 阶段 | 生产链自动 | 中 |
| P0-E | Memory 自动: Debug 修复/失败路径 | 仅 execute_project | 扩展 | 低 |
| P1 | Audit Decision Chain 全链 E2E 验证 | 无 | 真实链 | 中 |
| P1 | Memory Learning Loop E2E (Run A→B) | 无 | 真实闭环 | 中 |
| P1 | Mock Risk Inventory 完整分类 | 初步 | 文档 | 低 |

## 七、未发现更严重 P0 (执行/安全/治理真实)

- 执行链: 真实 (Agent Runtime + 真实代码 + 治理预检)
- 安全: Audit 脱敏 ✅ + 测试零泄漏
- Governance: 真实约束 + RepairSafety
- 状态一致性: S10-065 UserLifecycle 映射层

## 八、结论

本 Sprint 聚焦: **Retrieval 全统一 (P0-A/B/C) + Audit 生产链自动 (P0-D) + Memory 自动扩展 (P0-E)**。
不进入 Deployment (用户明确禁止)。

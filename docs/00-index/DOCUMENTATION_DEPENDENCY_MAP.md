# DOCUMENTATION DEPENDENCY MAP (STEP11.0)
> 引用关系 (谁引用谁; 冲突; 旧概念污染)

## READ FIRST 链 (新 AI 读取顺序)
```
README.md → 00-index/README → CURRENT_SYSTEM_TRUTH → STEP10 Contract
→ MASTER_STATUS_TABLE → DEVELOPMENT/OPERATIONS (根 docs)
```

## Canonical 依赖
```
STEP10 Contract (T0) ← CURRENT_SYSTEM_TRUTH (汇总) ← README (导航)
orchestration-contract (T0) + data-governance (T0) = 代码契约的文档化
CURRENT_SYSTEM_TRUTH 引用: 代码 + 运行时 + STEP10 (权威)
```

## 冲突区 (Documentation Parallel Truth 风险)
| 主题 | 可能多份文档 | Canonical |
|------|-------------|-----------|
| 架构 | docs/architecture/ 81 份 + audit 大量 | STEP10 + orchestration/data-governance |
| Task/执行模型 | sprint10/s7-s9/design 大量旧模型 | STEP10 (Task 分层) + CURRENT_SYSTEM_TRUTH §4 |
| Agent | design + products + exec docs | CURRENT_SYSTEM_TRUTH §7 |
| LLM Router | LLM智能路由设计说明.md (根) + design | CURRENT_SYSTEM_TRUTH §8 (消费 0 事实) |
| 产品定位 | 方案书 (愿景) + 历史 | CURRENT_SYSTEM_TRUTH §1 |

## 旧概念污染清单 (历史文档中存在, 非当前)
execution_plan / exec T00x 平行 Task / 旧 "AI Employee" 定位 / 旧模块边界 /
旧 sprint 号 (S7-S10) / 旧成熟度 (STEP7 前评分) / 旧 SSOT 定义 (data-governance 前)

## 处理规则
- 历史文档旧术语 = 允许 (标注历史), 不修改
- 新文档一律用 STEP10 术语
- BROKEN_REFERENCE: 旧文档引用已不存在符号 → 若为历史文档, 不修 (标注); 若为 Canonical 新文档, 必修

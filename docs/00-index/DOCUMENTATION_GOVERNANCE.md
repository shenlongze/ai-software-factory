# DOCUMENTATION GOVERNANCE (STEP11.0, 2026-09-02)

## 1. Canonical Document 定义
= 声称描述"当前"系统且被授权为真相来源的文档 (Truth Level T0-T2)。
列表见 00-index/README (Canonical 段)。仅这些可被当作当前真相。

## 2. 谁可以修改
- STEP10 Contract (product-system-baseline/): 仅人工批准后可改 (AI 不得自行修改冻结决策)
- CURRENT_SYSTEM_TRUTH: 经 governance 流程 (代码/运行时事实变化时)
- 历史文档 (sprint*/design/adr/audit 其余): 只读归档, 不修改 (可追加新报告)
- 根 README: 维护人/AI 按 README 规则更新

## 3. 何时必须更新
- STEP10 Contract 改变 → 同步 00-index/README + CURRENT_SYSTEM_TRUTH + MATRIX
- 生产代码架构变化 (新 Domain/SSOT/关系) → CURRENT_SYSTEM_TRUTH §3-6
- 能力状态变化 (M 级变动) → MASTER_STATUS_TABLE
- API/CLI 变化 → 对应生产文档 (若引用旧端点=BROKEN_REFERENCE 标记)

## 4. Architecture Contract 改变时同步清单
STEP10 文件 → 00-index README → CURRENT_SYSTEM_TRUTH → DOCUMENTATION_MATRIX
→ 受影响生产文档 (orchestration-* / data-governance 若涉及)

## 5. Code change 后检查
改 Domain/SSOT/执行链 → 检查 CURRENT_SYSTEM_TRUTH §4-6 是否过期
改 Agent/LLM 路由 → §7-8 | 新增能力 → MASTER_STATUS_TABLE + PROJECT_REALITY

## 6. Historical documents
docs/sprint*/phase*/S10-*/design/adr 大部分 = HISTORICAL (T4/T6)。
保留证明演化, 不删不改为"当前"。引用时必须标 Historical。

## 7. Future proposal
标记 T5 (proposal)。不得写成已实现。产品自标 M3/M4 能力 = FUTURE 非缺陷 (STEP9 §13)。

## 8. 防止 Documentation Parallel Truth
> 文档本身也不得形成 Parallel Truth。

同一主题只允许一个 Canonical Owner:
| 主题 | Canonical Owner |
|------|----------------|
| 系统事实 | CURRENT_SYSTEM_TRUTH.md |
| 架构决策 | product-system-baseline/STEP10_DOMAIN_FREEZE.md |
| 编排契约 | orchestration-contract.md |
| 数据治理 | data-governance.md |
| 能力状态 | MASTER_STATUS_TABLE.md |
| Fix 设计 | fix-sprint-design/ (待批准) |

冲突处理: 两文档冲突 → 查 MATRIX 确定 Canonical; 无法定 → NEEDS HUMAN DECISION (不猜)。

# 绞杀线收尾（STRANGLER CLOSED）

> 日期: 2026-09-12 | 性质: **收尾声明**（无代码改动）

## 1. 绞杀已切部分（保留）

| 功能 | 状态 | 位置 |
|------|------|------|
| `approval list` | ✅ 已切（新实现） | `services/approval_runtime/` |
| `approval decide` | ✅ 已切（新实现） | `services/approval_runtime/decide.py` |

commits：`02727f62`（S1 list）· `843a0a98`（S1.5 decide）· `f7484cb6`（ruff）

## 2. apply 状态：**不切，保持旧实现**

**理由（一句话）**：apply 的语义是「把批准的 patch 落到用户真实项目」（`git apply` 真实写入），与 2.2 要求的"沙箱写入"**语义不可调和**——沙箱版 apply 无法真正应用；且方向已转向认知，无需收尾。

→ `factory approval apply` 保持走 `factory-exec/exec/approval.py`（未改动）。

## 3. 不再有第二个绞杀目标

**声明**：不再指定第二个绞杀目标（不切 evidence / trace / 任何其他功能）。
绞杀脚手架（`services/approval_runtime/` + 等价性测试）**方法成立，已跑通**，作为示范保留。

## 4. services/approval_runtime 的定性

**示范，非产品**：
- 它证明"新旧等价 + 可 fallback"的切换方法可行
- 它**不是**产品的一部分，也不是必须维护的模块
- 保留原因：作为"新骨架怎么写"的参照样本

## 5. 后续方向

任何**新**功能、新能力、新模块 → 走新骨架（`kernel/ services/ extensions/ projections/`），
遵守 `CLAUDE.md` 三条铁律（factory-core 冻结 / 新功能只写新骨架 / factory-core 改动需审批）。

**factory-core 不归档、不搬家、不删除。**

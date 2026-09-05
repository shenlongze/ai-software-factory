# 08 — RELEASE / LEARNING BOUNDARY (P2-A CONTRACT, 2026-09-06)

## 1. Release 是 Production Outcome fact

RELEASE-* (含 gate 结果: ver/evidence/approval) = 未来 Learning 的**重要
outcome 输入** (success/failure/时间/成本 — 从 release 记录 + ver/evidence FK
可提取)。

## 2. 本阶段边界

- P2-A 不实现 Learning
- Release→Experience: CONTRACT ONLY (未来 P2-C/D: exp 提取加 release_id FK)
- Release 记录本身即 outcome fact (无需即时学习)

## 3. 未来桥 (不实现)

```
RELEASE-* (outcome)
  + ver-* / EVD-* (质量证据)
  + repair/recovery 记录
  → Experience (P2-C)
  → Learning (P2-D)
  → 下一次生产
```

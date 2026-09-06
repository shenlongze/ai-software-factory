# 04 — LIFECYCLE CONTRACT (P2-C CONTRACT, 2026-09-06)

## 1. 冻结: Experience 无复杂生命周期 (最简)

```
CREATED (落盘即创建; 不可变 provenance)
```

- 创建后 **immutable**: 核心 (provenance + 提取内容) 不原地修改
- Learning consumption **不改变 exp** (只读消费; 未来 P2-D 的 profile 是
  派生物, 非 exp 修改)
- 无删除 API (保留历史; 修正 = 新 exp + source_id 区分)
- 无 version (type 变化 = 新 source_id 语义; 不 version 旧)

## 2. 理由

exp 是生产事实的派生快照 — 无 workflow 生命周期需求; 复杂状态机会
(created→validated→consumed) 在 P2-C 无消费端, 不加。

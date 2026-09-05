# 02 — ARTIFACT ID LEDGER (P0-F4 AUDIT, 2026-09-05, READ-ONLY)

> 四套 Artifact ID 对照 — 互不相连

---

## 1. ID 形态对照

| 账本 | ID 示例 | 前缀 | 生成器 | 前缀含义 | 域 |
|---|---|---|---|---|---|
| S2 | art-1a2b3c4d5e6f | art- | uuid4.hex[:12] | Artifact | factory-console (S1/S2 workflow) |
| exec | ART-00d12545 | ART- | uuid4.hex[:8] | Artifact | factory-exec agent_runtime |
| org | P-17ef31e5-R1788175215875-CODE | P-…R…-TYPE | project_id + run_ms + type | 项目产物 | factory-org ArtifactRegistry |
| EXS patch | EXS-7cf1a212.patch | EXS- | execution id | 外置产物 | external executor |

## 2. 各套 ID 无法互转

- art-* ↔ ART-*: 无映射代码 (不同生成器/不同 store)
- ART-* ↔ P-…-CODE: 无映射
- 无任何 id 转换函数 (grep 确认零转换代码 — 非隐式映射缺失而是设计缺失)

## 3. 与 canonical 链的 FK 现状

```
TASK-* (backlog) ── task_id ──► ?  (exec ART task_id=T001/exec; org task_id 空)
run-* (NodeRun)  ── node_run_id ─► S2 art-* (唯一有字段, 0 真实数据)
EXS-*            ── path 文件名 ─► EXS patch (隐式); ART event_refs (隐式)
ver-* (F3)       ── ?           ─► 无 Artifact 引用
ev-* (M3)        ── artifacts[] ─► 空 (9 条全空)
```

## 4. 结论

四套 Artifact ID 体系 + 零 canonical 锚 = ID ledger 完全断裂。

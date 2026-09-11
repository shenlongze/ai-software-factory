# 09 — ARTIFACT / VERIFICATION CLOSURE PLAN (STEP11)

## 目标 (D-6, INV-006/007)
```
Task → Run → {ExecutionRecord, Artifact, Verification}
Task 经 Run 间接可达 Artifact/Verification (不在 Task 建第二份 SSOT)
```

## 当前
- exec 域: Run/Record → ART-* (patch/test_result, event_refs) — 已按目标形态 (M2)
- 会话链: backlog Task → ExecState → gateway — Run 存在但 Artifact 未挂载

## Fix 边界 (FX-04)
1. 会话链 Run (gateway 记录) 增加 artifact_ref/verify_ref 引用能力 (设计: 回写时可选)
2. Task 查询 Artifact 经 Run 间接 (API 层 join, 非 Task 字段)
不做: Task 上存 Artifact SSOT / 统一 exec+会话链存储

## 验收
- 会话链执行产生 Run → (若有产物) 可查 artifact
- Task→Run→Artifact 审计链可追踪
- 无 Task 级 Artifact 字段

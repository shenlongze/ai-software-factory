# 03 — ARTIFACT CALL GRAPH (P0-F4 AUDIT, 2026-09-05, READ-ONLY)

> 真实调用链 (writer/reader/persistence)

---

## 1. S2 art-* (workflow 域)

```
create_artifact (artifact_lifecycle.py:106)
  ← node_runtime.execute_node_run (:433) — 每次尝试产新 Artifact (I10)
  ← rollback_service (:274) — rollback 新产物
  → _artifacts_dir/xx/art-*.json (GENERATED)
  → _record_transition → audit (artifact.CREATED/…)
读: get_artifact (governance/health/agent_kernel/workforce/release/recovery/rollback)
  transition_artifact/apply/approve (release_service, approval gates)
```

## 2. exec ART-* (AgentRuntime 域)

```
AgentRuntime.execute → _write_artifact_file (patches/EXS-*.patch / .report.md / .test.txt)
  → exec/artifacts.json 记录 {ART-*, task_id=T001/…, path}
读: exec store 查询 / execution_records 溯源 (T-9 通过 path)
```

## 3. org ArtifactRegistry (M3/S14 项目域)

```
ArtifactRegistry.create (org/artifact.py:331) → org/artifacts.json
  (project/stage 绑定; API: /api/artifacts, /api/projects/{id}/artifacts)
读: org API (S9-002/003), workflow 状态
```

## 4. EXS patch 文件 (external executor)

```
record_invocation → 同时写 patches/EXS-*.patch? (75 文件)
  → execution_records.json {EXS-*: …} (patch_text 不落记录, 外置)
读: T-9 溯源 evidence 段 (report/test 文件探测)
```

## 5. 关键调用图结论

- 唯一"生命周期化" Artifact 创建点 = execute_node_run (S2, workflow 域)
- 真实数据 (exec ART/org/patches) 全在**非 lifecycle** 路径
- 无代码把 exec ART-*/org/patches → S2 art-* (零迁移/零桥)
- Verification (ver-*, F3) 无任何 → Artifact 引用 (创建于 node_runtime, 与 art 并行但
  artifact 创建在 verification 前同函数内 — 有顺序无 FK)

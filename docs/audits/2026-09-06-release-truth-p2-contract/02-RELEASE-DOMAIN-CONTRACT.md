# 02 — RELEASE DOMAIN CONTRACT (P2-A CONTRACT, 2026-09-06)

## 1. Canonical Release Entity

**Option B 选定: RELEASE-{hex8}** (新 ID)

| 项 | 值 |
|---|---|
| ID | RELEASE-{hex8} |
| SSOT | <root>/releases/releases.json (现有路径复用 — 但记录为 RELEASE-*, 与 rel-* 分区) |
| Writer | ReleaseService (唯一) — create/inspect/list/transition |
| 性质 | 不可变事实核心 + 状态流转 (同 P0 模式: 幂等 + 原子写 + history) |

## 2. 字段 (最小)

```
release_id        RELEASE-{hex8}
version           1 (或由 package version 提供)
status            (见 03)
created_at/updated_at
actor             release_engineer / system
task_id           TASK-*            (P1/P0 FK)
task_run_id       run-*             (P0 FK)
exs_id            EXS-*             (P0 FK, 可多)
artifact_ids      [art-*]           (P0 FK, 可多)
verification_ids  [ver-*]           (P0 FK, gate 消费 — 非空!)
evidence_ids      [EVD-*]           (P0 FK, gate 消费)
release_type      (见 manifest)
reason            (release 原因)
metadata          (可扩展: git_commit/tag 等 external ref)
manifest          (产物清单快照)
history           (状态流转不可变记录)
```

**Git tag ≠ Release Truth**: git ref 只入 metadata (external reference)。

## 3. Cardinality

| 关系 | Cardinality | 语义 |
|---|---|---|
| TaskRun → Release | 1:N | 一个 run 可产多个 candidate (re-verify/re-approve) |
| Task → Release | 1:N | 一 Task 多次 Release (迭代) |
| Artifact → Release | N:M | Release 打包多个 art; art 可进多 Release |
| Verification → Release | N:1 (per gate) | 多个 ver-* 共同 gate 一个 Release (candidate 重新验证 = 新 ver) |
| Evidence → Release | N:1 (经 ver) | EVD 支撑 ver, ver gate release; EVD 不直接挂 release |
| Release → Task | 反查: task_ids[] | 多 TaskRun 可组一 Release (若未来多 run 发布) |

## 4. P0/P1 consume-only

Release 字段全为 P0/P1 FK (只读消费); 零 reverse-write。

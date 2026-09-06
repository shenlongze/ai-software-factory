# 03 — PROVENANCE CONTRACT (P2-C CONTRACT, 2026-09-06)

## Model B — Anchor provenance (选定)

```
Experience
 ├─ task_run_id   run-*     (anchor — 必有)
 ├─ exs_id        EXS-*     (anchor — 必有)
 └─ release_id    RELEASE-* (anchor — 执行经验可空; release 决策经验必有)
```

其余 (art/ver/EVD/task/plan/prd/req/disc/idea) **不复制** — 经 canonical
reverse_trace 获取:

```
exp.exs_id → EXS → (run → task → plan → prd → req → disc → idea)
           → art (exs 关联) → ver → EVD (经 ver)
```

## 2. 逐 FK 决策

| FK | 必须? | 理由 |
|---|---|---|
| task_run_id | MUST | exp 的执行锚点 |
| exs_id | MUST | 结果锚点 (确定性) |
| release_id | OPT (execution) / MUST (release decision) | 发布锚点 |
| artifact_ids[] | NO (derived) | 经 EXS reverse 可达 |
| verification_ids[] | NO (derived) | 经 EXS→run→ver 可达 |
| evidence_ids[] | NO (derived) | 经 ver 可达 |
| task_id | NO (derived 字符串化) | 经 run.task_id 可达 |

## 3. 原则

**不复制已存在的事实** (任务书 §8): EXS→art→ver→EVD→RELEASE 已可可靠追溯,
exp 只存 anchor 3 字段。

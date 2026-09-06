# 01 — REALITY AUDIT (P2-C CONTRACT, 2026-09-06)

## 1. 当前 Experience Reality (代码 + 真实数据)

| 项 | Reality |
|---|---|
| entity | ExperienceRecord (memory/experience.py, exp-{hex12}) |
| store | memory/experience_store.json (workspace/memory/) |
| id | exp-{hex12} (随机 — 非来源确定性) |
| schema | id/type/source/success/task/project/agent/role/problem/action/result/confidence/context/created_at |
| writer | ExperienceStore.add (同 id 覆盖幂等) — 被 AutoLearner/extraction 调 (M3) |
| 84 条分类 | source: execution_records 55 / repair_task 18 / replanning 3 / validation 3 / gap 2 |
| type | SUCCESS_PATTERN 48 / DEBUG 21 / FAILURE_PATTERN 10 / PLANNING 5 |
| FK | run/ver/release = 0; task = 字符串 (79 条, 含 T003/INSERT_TASK 等 M3 痕迹) |
| provenance | 无结构化 canonical FK |
| CLI | factory experience list/get/retrieve/extract (存在) |
| API | /api/experience + /api/experiences/search (存在) |
| WebUI | 展示型 (无业务写) |

## 2. 关键判断

- Experience 已有真实 store + CLI/API + 84 条真实数据 (55 来自 EXS 提取 — 桥真)
- 但 FK 全缺 (task 是字符串, 无 run/exs/ver/release id)
- M3 痕迹明显 (agent=backend-1, task=T003) — 历史 M3 域产物
- 无 canonical 生产 (P0 链) 产生的 exp

## 3. 无第二 Experience SSOT

memory/experience_store.json 唯一; learning_trace (审计), intelligence/experiences
(空壳 1) 非 exp SSOT。

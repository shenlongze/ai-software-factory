# 07 — LEGACY BOUNDARY (P0-F3, 2026-09-04)

> Legacy 隔离 — 不迁移历史 verification

---

## 1. 分类 (F3 后)

| 对象 | 分类 | F3 后状态 |
|---|---|---|
| EXR-* / TASK-GW-* / task-e1-* / T-* / task-chg-* | LEGACY/ADAPTER | 未触碰 (F0/F1/F2 边界保持) |
| 历史 EXS.verify (pass/fail/unknown 小写) | 旧元数据 | 保留; 无 ver-* 物化 (不 retroactive) |
| 历史 NodeRun.verification (内嵌 dict, 大写) | 旧数据 | 保留原状; 无迁移 (F3 只影响新物化) |
| release verification checks | 独立域 | 未并入 (F3 范围外) |
| 历史 session_exec | ORCHESTRATION STATE | 未触碰 |

## 2. 新数据 vs 历史数据

- 新执行 (chain/workflow) → ver-* 物化 (attempt=0/1+, 引用挂 run)
- 历史执行 → 无 ver-* (store 空) — UNKNOWN/absent, 诚实不伪造
- 代码读取兼容: production_evaluation 等读 `fv.get("status") or fv.get("result")`
  — 新引用 dict 读 status; 旧内嵌 dict 读 result; 都兼容

## 3. 零迁移确认

无批量改写 execution_records / runs / verifications / audit。
新 verifications.json 是全新事实文件 (旧数据不存在于此 store)。

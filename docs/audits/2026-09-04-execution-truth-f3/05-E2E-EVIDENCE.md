# 05 — E2E EVIDENCE (P0-F3, 2026-09-04)

> 真实 E2E — 真实验证器 (pytest subprocess), 隔离 tmp, 非 mock

---

## 1. 复跑结果 (2026-09-04)

```
=== E2E-1: EXS SUCCESS + Verification PASS ===
TaskRun=run-8527f3d4b6d7 state=COMPLETED | EXS=EXS-c01a5441 | verifier=PASS
ver-*=ver-f28311ff3f PASS (task_run_id 锚 + exs_id 锚)
E2E-1 PASS

=== E2E-2: EXS SUCCESS + Verification FAIL (Case B — F3 核心证明) ===
TaskRun=run-2a8c389709de state=COMPLETED (execution COMPLETED)
verifier=FAIL | ver-*=ver-c94cbf40b5 FAIL
E2E-2 PASS (EXS SUCCESS + Verification FAIL 合法 — 质量事实独立于执行结果)

=== E2E-3: 重复 verification → 单 canonical (同 type+attempt) ===
同 pytest type+attempt → 同一 ver-* (不双写)
跨 type (task_run_execution vs pytest) → 独立事实合法共存
E2E-3 PASS

=== E2E-4: recovery — TaskRun-1 FAIL → TaskRun-2 PASS ===
total ver-*: 4 | 唯一 id | ver-1→run1, ver-2→run2 (identity 不串)
E2E-4 PASS

=== ALL F3 REAL E2E PASS ===
```

## 2. E2E 方法 (无 Fake 确认)

- 隔离 tmp 数据根 (不碰 ~/.factory)
- 真实外部执行模拟: record_invocation 写真实 EXS (唯一 EXS 写者, 非 mock)
- finalize_node_run: 真实生产函数 (非 bypass)
- 真实验证器: verification.verify_pytest (subprocess pytest -q) —
  通过项目 (test_ok.py) / 失败项目 (test_fail.py)
- materialize_verification: 真实唯一写入口
- 断言: 真实持久化文件 (verifications.json + runs/*.json + execution_records.json)

## 3. 真实数据 CLI 验证

```
factory verification list → Verifications (4): PASS/FAIL/UNKNOWN 挂 run-* (rc=0)
```

## 4. 非 Fake 项确认

手工改 JSON ✗ | 手工构造 ver-* ✗ | 复制历史 verification ✗ | 伪造 audit ✗ |
mock verifier ✗ (真 pytest) | bypass repository ✗ (经 materialize 唯一入口)

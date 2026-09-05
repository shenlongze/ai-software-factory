# 06 — E2E EVIDENCE (P0-F4 IMPL, 2026-09-05)

> 真实 E2E — 真实 record_invocation (EXS) + 真实 pytest verifier, 隔离 tmp, 非 mock

---

## 1. 结果 (复跑 2026-09-05)

```
=== E2E-1: SUCCESS chain (real pytest PASS) ===
  TASK=TASK-f4e1 run=run-25c37620b1ed EXS=EXS-ccf5e6c5
  art=art-baf9daf15564 state=GENERATED exs=EXS-ccf5e6c5
  ver=ver-b12a1a8564 PASS art_refs=['art-baf9daf15564']
  EVD=EVD-115c4cc084 type=verifier_output content='.' (真实 pytest)
  → 全 ID 反查 PASS

=== E2E-2: EXS SUCCESS + real verifier FAIL → ver FAIL ===
  EXS result=success | verifier=FAIL | ver=FAIL
  → 不自动 PASS (F4 §12/§13) PASS

=== E2E-3: 重复 finalize → 单 art/单 ver/单 EVD ===
  art 1→1 | ver 1→1 | EVD 1
  → 幂等 PASS

=== E2E-4: TaskRun-1 FAIL → TaskRun-2 PASS ===
  run2: art=art-43f3af6c90fa ver=ver-6567924699 FAIL
  run3: art=art-b9a0adcdf91e ver=ver-c15c05925a PASS
  → attempt 隔离, 旧不覆盖 PASS

=== ALL F4 REAL E2E PASS ===
```

## 2. 方法 (无 Fake 确认)

- 真实 EXS: record_invocation (唯一 EXS 写者, 非 mock)
- 真实执行: 生产函数 finalize_node_run (含 I8 收纳 + ver 物化 + EVD attach)
- 真实 verifier: verification.verify_pytest (subprocess pytest -q) —
  通过项目 (test_ok) / 失败项目 (test_fail)
- 隔离 tmp 数据根 (不碰 ~/.factory)
- 断言真实持久化文件 (artifacts/*/art-*.json + verifications.json +
  evidence/EVD-*.json + execution_records.json)

## 3. 非 Fake 项确认

手工改 JSON ✗ | 手工写 ID ✗ | 复制历史 ✗ | mock verifier ✗ | mock 执行 ✗ |
audit reconstruction ✗ | 事后补登记 art ✗ (收纳在 finalize pipeline 内)

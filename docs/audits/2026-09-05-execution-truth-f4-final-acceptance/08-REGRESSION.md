# 08 — REGRESSION (P0-F4 ACCEPTANCE, 2026-09-05)

> 测试回归 + attribution

---

## 1. F1-F4 测试

| 套件 | 结果 |
|---|---|
| F1 identity relations | 16/16 PASS |
| F2 writeback | 8/8 PASS |
| F3 verification | 17/17 PASS |
| F4 artifact/evidence | 14/14 PASS |
| **TOTAL** | **55/55 PASS** (fresh 2026-09-05) |

## 2. 大范围回归 (fresh)

- F4 相关全套件 + org + exec: 2363 passed, 0 failed (单命令)
- llm 全量: 829 passed, 6 skipped, 0 failed
- 真实 E2E: 4/4 PASS (fresh 复跑)

## 3. F4 attributable regression = 0 (stash 对照, 决定性)

9 个 console 套件 (s10_121/workflow_start/s10_112/m3c_scheduler/
lifecycle_acceptance/s10_119/s10_116/s10_109/release_packaging) 21 failed:
**F4 改动 stash 前后 diff = 零差异** → 全部预存。

## 4. 预存/偶发 (非 F4, 未修改)

- test_agent_loop 11 failed (历轮一致, F0-F3 已有)
- 大并发批量偶发失败 (多进程时序; 单独跑通过)

## 5. 结论

**F1/F2/F3 regression PASS | F4 14/14 PASS | F4 attributable regression = 0**

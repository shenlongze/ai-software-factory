# 12 — REGRESSION (P1 IMPL, 2026-09-05)

## 1. P1 测试

test_p1_product_truth.py 15/15 PASS (identity/lifecycle/FK/reverse/PRD boundary/
legacy/idempotency)

## 2. 回归

- F1-F4 + P1: 70/70 PASS
- 相关套件 + org + exec: 2286 passed, 0 failed
- console + llm 大范围: 6690 passed / 50 failed

## 3. P1 attributable = 0 (stash 对照决定性)

50 failed 中 test_agent_loop 11 + s10 系 22 + test_console_cli 15 +
test_console_events 3 等 — stash P1 改动前后 **33=33 零差异** (同套件对照),
全部预存。test_console_cli 命令集断言过期 (含 strategy/ct 等更早新增,
非 P1 引入 — 对照证实)。

## 4. 未改预存测试 (纪律)

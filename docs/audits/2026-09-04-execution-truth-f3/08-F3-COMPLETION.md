# 08 — F3 COMPLETION (2026-09-04)

> Sprint: P0-F3 Verification SSOT | Status: PASS
> 基线: d849a108 (F0/F1/F2 committed)
> 架构决策: 方案 1 (语义 A 升级为 SSOT) — 用户批准

---

## 1. Objective

Verification = 独立、持久、可追踪、可审计的领域事实 (ver-* SSOT),
挂 TaskRun/EXS, 与 TaskRun/EXS/Task 状态机分离, 唯一写者, 真实执行路径。

## 2. Before

- verification.py (S5) = 真实执行器但返回即弃 (ver-* id 不落盘)
- NodeRun.verification = 内嵌 dict (F2, 大写 PASS/FAIL) — 与 EXS.verify (小写) 词汇/事实双轨
- 4 处 verification-like 事实源, 无 SSOT

## 3. Root Cause (GAP)

Verification 有执行器无 domain; 多事实源语义不统一 (大写 vs 小写 vs 4 态 vs 3 态)。

## 4. Changes

- 新: factory-console/verification_domain.py (ver-* SSOT: materialize/list/get/count/emit_audit,
  原子写, 幂等, 状态规范化)
- 改: node_runtime.py — _materialize_verify (verify metadata → ver-* 单向物化;
  兼容 result/status 字段; 缺省→UNKNOWN 禁 PASS); finalize/execute → run.verification 引用
- 改: fastapi_adapter.py — T-9 溯源 EXS 命中时投影 ver-* (只读)
- 改: cli_factory.py — factory verification list|get
- 更新: node_runtime/node_artifact_e2e/repair_loop/production_entry/recovery_control/
  F2 writeback 测试 (内嵌→引用断言)
- 新: tests/console/test_p0_f3_verification.py (17)

## 5. SSOT / Ownership

见 04-VERIFICATION-SSOT.md + 03-STATE-OWNERSHIP.md

## 6. F2 metadata 冲突解决 (方案 1)

F2 verify dict → _materialize_verify → ver-* (唯一 canonical);
NodeRun.verification = {verification_id, status, method} 引用 (非第二事实源)。
attempts 内嵌保留历史审计 (含 verification_id 交叉引用)。

## 7. Real E2E (4/4 PASS)

E2E-1 EXS SUCCESS + ver PASS | E2E-2 EXS SUCCESS + ver FAIL (Case B) |
E2E-3 幂等 | E2E-4 recovery 身份不串 — 全部真实 pytest subprocess, 隔离 tmp。

## 8. Tests

- F3: 17/17 | F1: 16/16 | F2: 8/8
- 全量回归 (org/exec/llm/benchmark/console 相关): **3081 passed, 6 skipped, 0 failed**
  (test_agent_loop 11 failed = 预存; test_concurrency 偶发 = 预存, 均已对照)
- 修复的 F3 引入失败: production_experience/guided_production/production_evaluation 31
  (根因: _materialize_verify 只读 result 字段, 未兼容 verify_code_with_pytest 的 status 字段)

## 9. API/CLI

- CLI: factory verification list|get (实测 rc=0, 4 条真实 ver-*)
- API: T-9 trace 含 verifications 投影 (EXS→task_run_id→ver-*)
- WebUI: 保持投影 (无本地 verification 状态)

## 10. Remaining Gaps (P2/P1, 非阻塞)

- P2: release 域验证独立 (未并入 TaskRun 级 ver-*) — F3 范围外, F4 再议
- P2: attempts 内嵌 verification 与 ver-* 并存 (历史审计 vs canonical) — 已定义引用关系
- P2: E2E 用 verify_pytest 独立物化 vs finalize 自动物化 — 生产链尚未在真实运行中
  验证两者时序 (代码路径已通, 真实运行需有项目目录委派场景)

## 11. F4 Readiness

- ver-* 已含 evidence_ref 预留 (空 list) — F4 Evidence 可直接挂
- Verification → Artifact → Evidence 链: 当前 Artifact 挂 run (S1), ver-* 挂 run —
  F4 需桥接 ver-*.evidence_ref → artifact_id 语义
- T-9 溯源已含 EXS→ver-* 投影, F4 可扩展 evidence

## 12. Working Tree (F3)

modified: node_runtime.py / fastapi_adapter.py / cli_factory.py
          + tests (node_runtime/node_artifact_e2e/repair_loop/production_entry/
          recovery_control/F2 writeback)
new: verification_domain.py / test_p0_f3_verification.py
docs: docs/audits/2026-09-04-execution-truth-f3/ (00-08)
未提交 (F3 Git 纪律: DO NOT COMMIT, DO NOT PUSH)

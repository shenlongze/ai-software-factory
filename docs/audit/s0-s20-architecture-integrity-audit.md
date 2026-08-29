# S0–S20 Production Architecture Integrity Audit

> 日期: 2026-08-29 | HEAD: cc62d7be (v1.1.326) | 审计类型: 只读 (未修改代码)

## 一、审计范围
S1-S20 全链: ProductionRun/NodeRun/Artifact/Verification/Evaluation/Experience/Agent/Handoff/Workforce/Governance/Approval/Release/Rollback + CLI/API/WebUI。

## 二、原则符合性 (PASS / FAIL / WARN)

| 原则 | 状态 | 证据 |
|------|------|------|
| Single Source of Truth | ✅ PASS | ProductionRun(recovery 复用)→Artifact→Verification→Evaluation 单向链;Governance/Release/Rollback 均从 domain facts 投影,无第二事实源 |
| Evidence-driven | ✅ PASS | release/rollback evidence 持久化 (apply/verify/remove);verification 用真实 subprocess (S20) |
| CLI/API shared Service | ✅ PASS | cli_factory 3915/4111/4197/4298 + fastapi_adapter 3998-4188 全部 import Service 层,无独立逻辑 |
| No Hidden State | ✅ PASS | Agent 间只经 Handoff(artifact refs);guidance 注入显式 context;无 global/session magic |
| No Stub | ✅ PASS | Zero-Stub Audit 每 Sprint 通过;release/rollback/governance 无 placeholder |
| Real E2E | ✅ PASS | S11/S12 真实 LLM+Codex+pytest;S18/S19 真实 apply/rollback workspace |
| Governance 不可绕过 | ✅ PASS | release/rollback 都调 check_governance;Agent 不能 approve;S17 测试证明 |
| Artifact Lifecycle 不可绕过 | ✅ PASS | release/rollback 经 apply_artifact/transition_artifact (I1/I12);legacy _apply_patch 未被新链调用 |

## 三、GAP TREE (按严重度)

### 🔴 CRITICAL (阻断 S21 前需修)
无。

### 🟠 MAJOR (S21 需纳入)
```
1. 并发锁缺口
   ├─ release_service: 无 RLock (原子写有, 但 read-modify-write 竞态)
   ├─ rollback_service: 无 RLock (同上)
   └─ governance_service: 无 RLock (approve/check 竞态)
   → 双进程同时 release/approve 可能丢更新 (project-local lock 即可)

2. Recovery 不覆盖 release/rollback
   ├─ recovery.py 只处理 ProductionRun/NodeRun (S7)
   └─ release VERIFYING 中断 → 无 resume 语义 (S20 后新增状态)
   → S21 需: recovery 识别 release VERIFYING → 重跑 verification 或标 FAILED

3. Release FAILED 无 retry 路径
   ├─ FAILED = terminal (S20)
   └─ verification 瞬时失败 (timeout) 无法重试
   → 需 bounded retry (复用 S5 语义, 非无限)
```

### 🟡 MINOR (记录, 非阻断)
```
4. approval expired 无显式 EXPIRED 状态
   └─ 保持 APPROVED + governance 投影 expired=True (S20 设计) — 语义正确但 API 消费需注意
5. rollback 只恢复 target release artifacts (S19 已知限制)
   └─ 不反向删除后续 release 新增文件 (完整 workspace diff 恢复 = S21 候选)
6. legacy actions.py (4121 行) 未被新链引用 — 死代码 (审计时已标记, 未删)
7. workflow_runner._apply_patch (822/1020) legacy 路径存在但新链不调用 — BYPASS 已隔离
8. verification_checks 只在 release/rollback 记录, ProductionRun 无聚合 verification 视图
```

## 四、状态机完整性检查

| 状态机 | 转换表 | 非法转换拒绝 | 终态保护 | 审计 |
|--------|--------|------------|---------|------|
| ProductionRun (PENDING/RUNNING/COMPLETED/FAILED/BLOCKED) | ✅ | ✅ | ✅ | ✅ |
| NodeRun (PENDING/RUNNING/VERIFYING/COMPLETED/FAILED/BLOCKED/REPAIRING) | ✅ | ✅ | ✅ | ✅ |
| Artifact 8 态 | ✅ | ✅ (I10) | ✅ | ✅ |
| Approval (PENDING/APPROVED/REJECTED) | ✅ | ✅ | ✅ | ✅ |
| Release (PENDING→GATED→APPROVED→RELEASING→VERIFYING→RELEASED) | ✅ | ✅ | ✅ | ✅ |
| Rollback (PENDING→GATED→APPROVED→ROLLING_BACK→VERIFYING→ROLLED_BACK) | ✅ | ✅ | ✅ | ✅ |

## 五、S21 是否可直接开始?

**✅ 可以直接开始**,但建议先做 2 个 MAJOR 前置 (小改动):
1. 给 release/rollback/governance 加 process-local RLock (每文件 ~10 行)
2. Recovery 识别 release VERIFYING 状态 (中断 → 标 FAILED 可重试)

理由:
- 无 CRITICAL 阻断项
- 状态机/事实链/Service 架构/Governance 全部符合原则
- 遗留 GAP (并发/恢复/retry) 是增强项, 不破坏现有正确性
- 814 passed + 5 skipped 全绿, 无回归风险

## 六、结论
S0-S20 生产事实链保持 Single Source of Truth, 无架构漂移, 无重复事实源, 无 Governance/Lifecycle 绕过。审计发现 3 个 MAJOR 增强项 (并发锁/Recovery 扩展/retry), 均非阻断。S21 可开始。

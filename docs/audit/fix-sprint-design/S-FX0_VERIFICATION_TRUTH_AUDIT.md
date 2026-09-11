# S-FX0 VERIFICATION TRUTH & SSOT AUDIT (2026-09-02)

> Fix Sprint 第一阶段 — 只读审计。零代码/零 Contract 修改/零 Fix。

## 1. Executive Summary

Verification 在系统中以**三处独立产生**、无统一冻结 SSOT、downstream 未闭环的形式存在:

```
A. exec 域: test_result artifact (75 个, 挂 EXS-* Run, task_id=T00x) — 真实持久化事实
B. console 域: verification.py 真实验证器 (verify_pytest/verify_python_syntax),
   被 5+ 服务调用, 返回 dict (PASS/FAIL/INCONCLUSIVE/BLOCKED), 无统一持久化
C. 会话质量: session/quality.py (Validator/ValidationResult/ReviewResult) — S10-053 质量环
判定: VERIFICATION SSOT = MULTIPLE TRUTH (exec 有事实, console 无统一记录, 会话链无关联)
```

## 2. Verification Candidate Inventory

| Candidate | 位置 | 角色 |
|-----------|------|------|
| verification.py | factory-console/verification.py | 真实验证器 (pytest/syntax subprocess) |
| ValidationResult/Validator | session/quality.py:62/101 | 会话质量环 (S10-053) |
| validation.py | factory-exec/exec/validation.py | 沙箱验证 (只检查无执行权) |
| test_result artifact | exec/results.json | 执行产物验证 (75 个) |
| ExecState task verify | session_exec/*.json | 会话链执行 verify 信息 |
| verify_* 消费方 | effectiveness/health/release/recovery/professional_workflow | 服务内验证 |

## 3. Entity Forensics

- console/verification.py:24 verify_python_syntax / :51 verify_pytest (subprocess 真实)
  → VerificationResult 概念: {verification_id: ver-*, status(PASS/FAIL/INCONCLUSIVE/BLOCKED), exit_code, stdout, evidence}
  → **ver-* id 运行时仅 skills.json 出现 1 次 — 无独立 Verification 记录库**
- exec/validation.py: syntax_check/run_command → passed bool + output (门禁用)
- exec results test_result: ART-b97e1a72 (type=test_result, task_id=T002, agent_id=backend-1, path=EXS-*.test.txt)

## 4. Writer Forensics

| Writer | 写入 | 存储 | ID |
|--------|------|------|-----|
| exec 执行 (agent_runtime) | test_result artifact | exec/results.json (result.artifacts[]) | ART-* |
| console services (effectiveness:142/health:113/release:301/recovery:136/professional_workflow:367) | 调用 verify_* | 调用方各自处理 (无统一落点) | ver-* (未持久化) |
| quality.Validator | ValidationResult | quality store? | UNKNOWN |

## 5. Reader Forensics

| Reader | 读取 | 生产? |
|--------|------|-------|
| exec results (查询 API) | test_result artifact | 生产 (数据存在) |
| effectiveness/recovery/release services | verify_* 返回值 | 生产 (服务内即时决策) |
| **统一 Verification reader (SSOT 查询)** | **无** | **ABSENT** |

## 6. Storage / Persistence

- exec test_result: exec/results.json (持久化 ✅, 85 result / 75 test_result)
- console verify 结果: 无独立持久化 (返回 dict, 调用方即时消费)
- 无 verification_*.json / 无 ver-* 记录库 (唯一 ver- 出现在 skills.json 偶然)

## 7. Run Relationship

- exec 域: Run(EXS-*) → result → test_result artifact — **关系存在** (EXS-002f56f0 → ART-b97e1a72)
- console 域 (gateway Run): Run → verification 无持久化关联
- 会话链: ExecState 任务 verify 字段 (exec_fn 返回) — 部分

## 8. Artifact Relationship

- exec: test_result 是 Artifact 的一种 type (patch/test_result/report 并列)
  → Verification 以 Artifact 形式存在 (非独立实体)
- 无 Artifact.verification_id 反向引用 (同 result 下并列, 非互引)

## 9. Task Relationship

- exec: test_result.task_id = T00x (exec 域任务)
- backlog Task (TASK-*): 无 verification_id/test_result 字段 — **会话链 Task 不持 Verification** (与 STEP10 INV-007 一致: Task 经 Run 间接)
- 但 exec T00x ≠ backlog TASK-* (映射未建, FX-01) → exec verification 无法从 backlog Task 到达

## 10. Execution Truth Relationship

```
backlog TASK-*     — 无 verification 关联
exec T00x          — test_result (T00x 域) ✅ 唯一完整 Verification 事实
execution_plan T-* — 无 verification 记录
Run (console)      — 无持久化 verify
→ Verification 事实只完整存在于 exec 域, 且与主链 Task (TASK-*) 隔离
```

## 11. Production Evidence (~/.factory)

- exec results: 85 条 (75 test_result + 75 patch + 75 report)
- test_result path: EXS-*.test.txt (真实产物文件)
- 时间: 2026-08-15 (早于本轮; exec 域真实运行产生)
- console verify 运行痕迹: 无独立记录 (services 调用但结果未落统一库)

## 12. E2E Evidence

- exec 域: Run → test_result artifact 完整 (数据级)
- 完整链 (Task→Run→Verification→审批→Task): exec 域 T00x 级有 (ART→EXS→approval), 主链无
- **E2E NOT PROVEN (主链): backlog Task → Run → Verification 无闭环**

## 13. SSOT Determination

| 域 | Verification 事实 | SSOT 状态 |
|----|-------------------|-----------|
| exec | test_result artifact | CONFIRMED (exec results 内) |
| console | verify_* 返回 | 无持久化 (ABSENT 独立记录) |
| 会话链 | ExecState.verify | PROJECTION |
| 全局 | — | **MULTIPLE TRUTH (exec 持久 vs console 无记录 vs 质量环独立)** |

## 14. Contract Alignment

- STEP10 INV-006/007 (Verification 归属 Run/Record, Task 经 Run 间接): exec 域 ✅ 符合
  (test_result 挂 EXS result); 会话链 ❌ 无 Run 级验证持久化
- STEP10 Verification Domain: PARTIAL (exec 域有事实; 全局 SSOT 未冻结 — 支持 STEP11 FX-08)

## 15. Evidence Index

| 结论 | 证据 |
|------|------|
| console 真实验证器存在 | verification.py:24/51 (verify_python_syntax/verify_pytest subprocess) |
| 5+ 服务消费 | effectiveness_service.py:142 / health_service.py:113 / release_service.py:301 / recovery_service.py:136 / professional_workflow.py:367 |
| exec test_result 事实 | exec/results.json (ART-b97e1a72: type=test_result, task_id=T002) |
| 无 ver-* 主记录 | grep ver-[a-f0-9] ~/.factory → 仅 skills.json 1 次 |
| exec Run→Verification | EXS-002f56f0 → artifacts[] (test_result + patch + report) |
| 会话链无关联 | backlog Task 无 verification 字段 (STEP9 MASTER 确认) |
| 质量环独立 | quality.py:62/101/239/272 (ValidationResult/Validator/ReviewResult/RepairManager) |

## 16. Unknowns

- quality.py ValidationResult 的持久化位置 (UNKNOWN — 未追踪到独立 store)
- effectiveness/recovery 调 verify 后结果写哪 (各 service 内部, 未穷尽)
- exec test_result 内容的实际判定语义 (test.txt 是否被解析为 PASS/FAIL 决策 — 未验证)
- Verification 是否驱动审批 (approval) 的证据 — 未在本 Sprint 穷尽

## 最终判断

```
VERIFICATION SSOT = MULTIPLE TRUTH
  - exec 域: test_result artifact (CONFIRMED, 但只覆盖 exec/员工执行)
  - console 域: verify_* 真实验证器 (无统一持久化)
  - 会话链: 无 Run 级 Verification 事实
  - 质量环: quality.py 独立

Production Code Changes = 0
Contract Changes = 0
Fixes = 0
Migration = 0
Commit = NO
Push = NO

STATUS = STOP / WAIT FOR HUMAN APPROVAL
```

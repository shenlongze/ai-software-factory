# 01 — VERIFICATION CONTRACT (P0-F3, 2026-09-04) — FROZEN

> 状态: FROZEN (方案 1 经架构决策批准: 语义 A 升级为 SSOT)
> 基线: d849a108 | 架构决策: 用户选方案 1

---

## 1. 决策记录

GAP AUDIT 发现两套 verification 语义 (S2 NodeRun 内嵌 vs S5 ver-* 执行器)。
用户批准 **方案 1: 语义 A 升级为 SSOT** —
NodeRun.verification 从内嵌 dict 改为 ver-* 引用, ver-* 独立落盘 canonical。

## 2. Verification 对象 (冻结)

| 字段 | 语义 |
|---|---|
| verification_id | ver-{hex10} (canonical ID) |
| task_run_id | run-* (显式 FK → NodeRun) |
| exs_id | EXS-* (若存在; 显式 FK → Execution Result) |
| status | PASS / FAIL / UNKNOWN / INCONCLUSIVE / BLOCKED (5 态兼容) |
| verification_type | task_run_execution / pytest / syntax / ... |
| method | pytest -q / ast.parse / verify_hook / ... |
| result | 原因/细节文本 (≤500) |
| evidence_ref | list[str] (F4 预留, 空) |
| attempt | int (同 run 多次验证) |
| detail | {source_meta: {score/reason/source}} |
| actor | 写者 (session-chain / node-exec / verification) |
| created_at / completed_at | ISO |

## 3. 状态语义 (冻结)

```
PASS      = 真实验证通过
FAIL      = 真实验证失败
UNKNOWN   = 无 verifier / 无法运行 / 超时 / 结果不可确定 (诚实; ≠PASS)
INCONCLUSIVE = pytest 返回非 0/1/2 退出码 (兼容 verification.py S5)
BLOCKED   = 验证被阻塞 (兼容 S5)
RUNNING   = 不需要 (当前为同步验证)

铁律:
  禁止 "无验证 → PASS" (materialize status 空 → ValueError)
  EXS SUCCESS + Verification FAIL = 合法终态 (E2E-2 实证)
  EXS SUCCESS + Verification UNKNOWN = 合法终态
  小写 pass/fail/unknown → 大写规范化 (gateway 词汇兼容)
```

## 4. 关系 (冻结)

```
Verification(ver-*).task_run_id → run-* (NodeRun)
Verification(ver-*).exs_id      → EXS-*
溯源: ver-* → task_run_id → run-* → task_id (run.task_id=TASK-*) → Task
不经 task_id/exec_ref/audit/filename 隐式关系
```

## 5. F2 metadata 冲突解决 (冻结)

```
F2 finalize/execute verify metadata (gateway/executor 返回)
    ↓ 单向 materialization (_materialize_verify → materialize_verification)
    ↓
ver-* SSOT (唯一 canonical)
    ↓
NodeRun.verification = {verification_id, status, method} 引用 (只读快照, 非第二事实源)
```

原则: **Verification 只有一个 canonical fact source (verifications.json)**;
NodeRun 内嵌字段降级为引用; attempts 内嵌 verification 保留为不可变历史审计
(含 verification_id 交叉引用)。

## 6. Writer (冻结)

唯一写入口: `verification_domain.materialize_verification` (加锁 + 原子写)。
node_runtime 的 _materialize_verify 是唯一适配器 (finalize/execute 共用)。
禁止: WebUI 直接写 / audit 直接写 / EXS.result 冒充 Verification / release 另维护 /
session_exec 自维护。

## 7. 幂等 (冻结)

同 (task_run_id, attempt, verification_type) → 返回已有 ver-* (单 canonical)。
不同 attempt → 各自 ver-* (attempt 字段区分, 不覆盖历史)。
不同 verification_type → 独立事实 (执行验证 vs pytest 深度验证), 合法共存非双真。

# 03 — STATE OWNERSHIP (P0-F3, 2026-09-04)

> 最终 ownership — Verification 单一 owner

---

## 1. Matrix

| Object | Canonical ID | Store | Writer | Not Canonical |
|---|---|---|---|---|
| Verification | ver-* | verifications/verifications.json | materialize_verification (唯一) | EXS.verify / NodeRun.verification 内嵌 / release checks / attempts 内嵌 |
| NodeRun.verification | (引用) | nodes/runs/*.json | node_runtime (写入引用) | 独立事实源 (降级为引用快照) |
| TaskRun attempts 内嵌 verification | (历史) | nodes/runs/*.json | execute_node_run | 不可变历史审计 (含 verification_id 引用) |
| EXS.verify | (元数据) | execution_records.json | verify_invocation (gateway) | 执行验证元数据 (materialization 输入) |
| release verification | (域内) | releases/*.json | release_service | Release 域 (F3 范围外) |

## 2. 谁可以改 Verification

- 创建/更新: materialize_verification (唯一入口, RLock + 原子写)
- 状态确认 (PASS/FAIL/UNKNOWN): 由 materialize 时 status 参数决定 —
  调用方 (node_runtime 适配 / 真实验证器) 传真实结果; 禁止 WebUI/audit/EXS 直接写
- 无二次状态流转 (创建即终态 — 验证是事实快照)

## 3. 禁止路径 (验证)

- WebUI: 只读投影 (无写 ver-* API)
- audit: emit_audit 只写观察事件 (VERIFICATION_*), 不回写 domain
- EXS.result: 不冒充 Verification (EXS SUCCESS + ver FAIL 合法, E2E-2)
- release_service: 独立域验证, 不写 TaskRun 级 ver-*

## 4. 无 competing writer 结论

F2 metadata (finalize verify dict) → 单向 materialization → ver-* (SSOT);
NodeRun.verification 仅存 {verification_id, status, method} 引用。
单一事实源: verifications.json。

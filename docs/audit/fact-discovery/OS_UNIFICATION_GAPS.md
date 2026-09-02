# OS UNIFICATION GAPS — STEP 5
- G-OS-01 HIGH: 非统一 OS (多模块拼接)
  | 共享项 | 实际 |
  |--------|------|
  | Domain/SSOT | org 共享; core/exec 独立数据空间 |
  | Event | audit_events 共享 (console 域); core events 独立 |
  | Execution | 三套 (STEP4) |
  | Project Context | console+org 共享; core/runtime 无 |
  | Governance | approvals 部分共享 |
- console→org (69) + console→exec (79) 集成真实
- console→core = 0 / console→runtime = 0 (core/runtime 承担 OS 核心职责的证据缺失 → UNKNOWN)
- 分类: SSOT_GAP + INTEGRATION_GAP

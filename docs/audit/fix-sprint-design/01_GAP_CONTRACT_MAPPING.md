# 01 — GAP → CONTRACT MAPPING (STEP11, 2026-09-02)
> 将 STEP5-10 的 GAP 映射到 STEP10 冻结 Contract。分类: A TRUE_IMPL / B CONTRACT_IMPL /
> C FUTURE / D UNPROVEN / E DESIGN_CHOICE / F HISTORICAL

| GAP-ID | 原 Severity (STEP6) | STEP11 分类 | 违反/对应 Contract | Invariant |
|--------|---------------------|-------------|---------------------|-----------|
| G-TRUTH-01 三套 Task truth | HIGH (域契约) | **F+B** | 06 Execution Truth Contract (D-9) | INV-012 |
| G-REQ-01 需求无下游 | HIGH (TRUE_GAP) | **B** | 07 Req→Product→Exec Contract (D-4 C) | INV-010 |
| G-PRD-01 PRD 实体 | MEDIUM (M3) | **C** (实体 M3) + B (引用位置预留) | 07 Contract (D-5) | INV-011 |
| G-ART-01 Artifact 无关联 | MEDIUM-HIGH | **B** | 03 Task Contract §Artifact (D-6) | INV-006/007 |
| G-LLM-01 Model Selection 0 消费 | HIGH (TRUE_GAP) | **B** | 09 Model Selection Contract (D-8) | INV-009 |
| G-AGENT-01 角色 Agent 触发 UNKNOWN | MEDIUM | **D+B** | 08 Agent Selection Contract (D-7) | INV-008 |
| G-REQ-02 需求分析不落盘 | MEDIUM | **B/D** | 07 Contract + P-REAL-01 审计 | — |
| G-VER-01 验证无下游 | MEDIUM | **D** | Verification 域未冻结 SSOT | — |
| G-OS-01 非统一 OS | INFORMATIONAL | **E** | 10 Module Boundary (D-10) | INV-015 |
| G-CORE-01 core 孤立 | INFORMATIONAL | **E** | 10 Module Boundary | INV-015 |
| G-REQ-03 需求无版本 | MEDIUM (并入 G-REQ-01) | **B** | 07 Contract | INV-010 |
| G-EXP-01 经验写无读 | MEDIUM | **C** | Learning 域 FUTURE (M4 承诺) | — |
| G-LEARN-01 | MEDIUM | **C** | FUTURE M4 | — |
| G-REPLAN-01 | MEDIUM | **C** | FUTURE M3 | — |
| G-OBS-01 | LOW | **D** | Observability | — |

## 结果
- A TRUE IMPLEMENTATION GAP: 0 (STEP10 冻结后无"实现违反冻结契约"项 — 契约均未实施, 非错误实现)
- B CONTRACT IMPLEMENTATION GAP: 5 (G-TRUTH-01 映射部分, G-REQ-01, G-ART-01, G-LLM-01, G-AGENT-01 部分, G-REQ-03)
- C FUTURE: 5 (G-PRD-01 实体, G-EXP, G-LEARN, G-REPLAN, +PRD 深度化)
- D UNPROVEN: 3 (G-VER-01, G-REQ-02 部分, G-OBS-01, G-AGENT-01 部分)
- E DESIGN CHOICE: 2 (G-OS-01, G-CORE-01)
- F HISTORICAL: 1 (G-TRUTH-01 的 execution_plan 部分)

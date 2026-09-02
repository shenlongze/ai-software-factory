# SEVERITY VALIDATION — STEP 6 (2026-09-02)

| GAP | 原 Sev | 新 Sev | 依据 |
|-----|--------|--------|------|
| G-TRUTH-01 | CRITICAL | HIGH | 产品允许模块独立数据 (P-MOD-02); 违反需先证明同一执行域 — 域契约缺失 HIGH |
| G-REQ-01 | CRITICAL | HIGH | 违反 P-REQ-01 (需求可追溯); 但 M3 里程碑内 — HIGH (非 CRITICAL: 会话核心链可跑) |
| G-PRD-01 | CRITICAL | MEDIUM | PRD 审批门已实现 (P-PRD-01 ✅); 实体化是 M3 🚧 — MEDIUM |
| G-LLM-01 | HIGH | HIGH | 明确违反模型路由承诺 (P-LLM-01) |
| G-ART-01 | HIGH | MEDIUM | 审计链部分断裂, 不阻断核心执行 — MEDIUM |
| G-OS-01 | HIGH | LOW/INFO | 设计原则支撑模块独立 (P-MOD) — INFORMATIONAL |
| G-CORE-01 | HIGH | INFORMATIONAL | 意图独立产品, 无原则要求必须集成 |
| G-AGENT-01 | HIGH | MEDIUM | M2 深度承诺; 基础 Agent 执行真实 |
| 其余 MEDIUM/LOW | — | 基本保持 (FUTURE_CAPABILITY 项降为 LOW-INFO 影响当前) |

## CRITICAL 核验
- 修正后 CRITICAL = 0 (原 3 个 CRITICAL 均被原则支撑降级: P-MOD-02 允许模块独立数据 /
  M3 里程碑内未实现)
- 理由: 无 GAP 直接破坏当前已运行的核心用户旅程 (会话→计划→任务→执行→聚合 → E2E 通);
  最接近 CRITICAL 的是 G-TRUTH-01/G-REQ-01 (HIGH)

## 注意 (证据边界)
- 严重度降级依赖"产品自标 M2/M3/M4 🚧📐" = 产品明确未承诺当前交付
- 若未来里程碑承诺到期仍未实现 → 升级

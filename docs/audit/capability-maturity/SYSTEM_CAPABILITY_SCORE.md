# SYSTEM CAPABILITY SCORE — STEP 7 (修正版, 2026-09-02)

## 权重 (CORE>SUPPORTING>FUTURE, Future 不惩罚当前)
CORE×3, SUPPORTING×1, FUTURE×0.3

## 计数
- Atomic Capability: 29
- M0: 4 | M1: 4 | M2: 3 | M3: 7 | M4: 11
- CORE: 18 (M4:10/M3:4/M2:2/M1:1/M0:1)
- SUPPORTING: 7 | FUTURE: 4

## A. Capability Reality Score = 85.2/100
真实生产能力 (M≥2 加权): 核心闭环 + 集成能力 + 生产运行能力占比
证据: CORE 18 中 M≥2 = 16 (Session/Intent/Planning/Task/Dep/LLM/Orch/Exec/Recovery/Cancel/Verify/Audit/Govern/AgentSel/AgentExec)

## B. Contract Fulfillment Score = 75.0/100
产品承诺用户旅程 10 步: 7 PROVEN + 2 PARTIAL + 1 FUTURE (PRD 深度化/验证闭环/变更回流 = M3/M4 里程碑内)

## C. Production Closure Score = 49.8/100
M4 闭环加权: CORE M4 = 10 (Session/Intent/Planning/TaskMgmt/DepSched/LLMInv/Orch/Exec/Cancel/Audit)
= 会话→计划→任务→依赖执行→取消→审计 主链已闭环

## 解读 (禁止反推单一成熟度)
- A 85: 能力真实性高 — 非"代码存在", 有运行+持久化+证据
- B 75: 已承诺核心旅程兑现; 未兑现部分 (PRD 实体/验证下游/变更回流) 是产品自标 M3/M4 里程碑
- C 49.8: 主链 M4; 支撑 (WebUI/CLI/Tool M3) 与 CORE 缺口 (ReqTrace M0/ModelSel M1/Verify M2) 未闭环

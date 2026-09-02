# PROJECT PROGRESS SNAPSHOT (2026-09-02)
> 每次开发前快速查看。完整版: AI_FACTORY_PROJECT_REALITY_REPORT.md

## 项目: AI Software Factory v1.1.364
形态: 本地 Web (8011/5180) + CLI + 会话驱动执行内核 + 真实外部 Agent 执行

## 成熟度
- Capability Reality 85.2 | Contract Fulfillment 75.0 | Production Closure 49.8
- 29 Atomic Capabilities: M4×11 / M3×7 / M2×3 / M1×4 / M0×4 (CORE 18/SUP 7/FUT 4)
- 等级: FOUNDATION STRONG / CORE EXECUTION REAL / PRODUCT INTELLIGENCE PARTIAL /
  CONTROL PLANE PARTIAL / FULL PRODUCT LOOP INCOMPLETE

## 已完成核心能力 (M4 CLOSED_LOOP)
会话 / 意图 / 规划 / 任务管理 / 依赖调度 / 取消 / 执行 / 编排(会话链) / 审计 / LLM 调用 / 项目管理

## 生产运行 (M3)
Agent 选择+执行 (records 100) / 恢复 / 治理审批 / WebUI / CLI / 工具调用

## 当前主要断点
1. Requirement 无下游引用 (trace ABSENT) — 需求→执行链断裂
2. PRD domain entity ABSENT (M3 承诺)
3. Model Selection 无生产消费者 (LLMRouter=0, 违反已标✅承诺)
4. Artifact/Verification 未闭环到会话链 (exec 域真实, 无关联)
5. 三套 execution truth 并存 (域边界契约缺失)

## Future (产品自标)
Experience→Learning (M4) / Replan+变更回流 (M3) / Release / PRD 深度化 (M3)

## Unknown
factory-core 生产职责 / exec 角色 Agent 触发 / factory.db 用途 / Release-Learning 运行时

## 当前生产链 (E2E PROVEN)
User → Session → Plan(pending) → 批准(execute_plan) → Task+依赖 → ExecState 门控 →
Run → 执行回写 (done/failed/cancelled) → recover (crash) → reconcile (plan completed/failed) → Audit

# CURRENT_SYSTEM_TRUTH — 当前系统事实单一导航 (STEP11.0, 2026-09-02)

> 本文件汇总 STEP1-11 已冻结事实。权威 = 代码 + 运行时 + STEP10 Contract。
> 任何冲突: STEP10 Contract > 本文件 > 代码注释 > 历史文档。

## 1. Product Identity
AI Software Factory (v1.1.364) — 已拥有真实生产执行内核 (M4) 的 AI 软件开发平台。
方向: AI Software Factory → AI Organization Factory → AI Enterprise OS。
不是: 普通 coding assistant / ChatGPT wrapper / 完整 AI Enterprise OS。

## 2. Architecture
```
运行时 = console (Web/会话/编排) + org (领域 SSOT) + exec (执行/Runtime 域, 深度集成)
独立模块 = core (意图独立产品, 全仓消费 0) + runtime (无运行痕迹)
外部 = LLM providers (deepseek) / 外部 Agent CLI (claude/codex) — 增强层非依赖
```

## 3. Domain Model (12 Domain, STEP10 冻结)
Requirement / Product-PRD (CONTRACT-ONLY) / Planning / Execution Task / Runtime-Run /
ExecutionRecord / Artifact / Verification / Agent / Model-LLM / Project / Audit-Governance

## 4. SSOT (每 Domain 唯一, INV-001)
| Entity | SSOT | ID |
|--------|------|----|
| Requirement | requirements.json | req_* |
| PRD | (ABSENT, M3) | — |
| Plan | session_plans.json | PLAN-* |
| Task | backlog (workspace/projects/*/management) | TASK-* |
| Run | gateway registry | EXS-*/R* |
| ExecutionRecord | exec records | EXS-* |
| Artifact | exec results | ART-* |
| Audit | audit_events.json | event |
| Agent | agents.json | backend-1 等 |
| Project | org/projects.json | P-* |

⚠️ Task 域: 三套历史结构 (backlog TASK-* SSOT / execution_plan T-* 历史冻结 / exec T00x Record 域)。
STEP10 D-9: 不得形成平行 Task SSOT (INV-012)。

## 5. Production Lifecycle (M4 主链, E2E PROVEN)
```
User → Session → Intent → Plan(pending) → 批准 → Task+依赖(backlog)
→ ExecState 门控 → Run → 回写(done/failed/cancelled) → recover → reconcile → Audit
```

## 6. Execution
三域: Session chain (M4) / M3 production_run (历史) / factory-exec (员工执行, records 100)。
真并行未实现 — 单任务串行 (Ready-set 逻辑≠并行)。

## 7. Agents
执行域 5+ agents PRODUCTION (execution_records 100: backend-1×48/flutter-dev×17/...)。
角色 Agent 类 (developer/pm/architect 等): IMPLEMENTED, 生产触发入口 UNKNOWN。
注册 ≠ 生产。选择: gateway._pick_executor → router (classify+score)。

## 8. LLM
Invocation M4 (llm_fn 统一注入, console_sessions.py:104 → deepseek) / Provider M3 /
Model Selection M1 (LLMRouter 消费 0) / Fallback M0。
"能调 DeepSeek" ≠ "Model Selection 控制面完成"。

## 9. Governance
Audit M4 (5160 events) / Approval M3 / Traceability: 执行链 ✅, 需求链 ❌ (G-REQ-01)。

## 10. Production Status (STEP7, 历史评估非总完成率)
Capability Reality 85.2 / Contract Fulfillment 75.0 / Production Closure 49.8。

## 11. Known Gaps (STEP11 分类)
B CONTRACT_IMPL: FX-01~FX-07 (Task 映射/Req 引用/Artifact 挂载/Model Policy/Agent 触发/分析落盘)
C FUTURE: PRD 实体 M3 / Learning M4 / Replan M3 / Release
D UNPROVEN: Verification SSOT (FX-08 取证) / exec 角色触发
E DESIGN_CHOICE: core/runtime 独立 (已冻结)

## 12. Future (产品自标, 非缺陷)
PRD 深度化 M3 / 变更回流 M3 / Experience→Learning M4 / Release M3-M4。

## 13. Unknown
factory-core 生产职责 / factory.db (3.3MB SQLite) 用途 / exec 角色触发 /
Release-Learning 运行时 / Verification downstream。

## 14. Documentation Rules
- 本文件 + STEP10 Contract = 当前真相; 历史文档 (docs/sprint*/design/adr 等) = 证据非真相
- 修改本文件须同步 governance; 新 AI 先读 READ FIRST 链

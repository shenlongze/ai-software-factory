# AI Factory Project Reality Report
> 日期: 2026-09-02 | 生成: FORENSIC STEP 8 (汇总 STEP 1-7, 全部结论 evidence-bound)

## 1. Executive Summary

AI Factory 是一个**可运行的 AI 软件开发平台**(AI Software Factory),当前形态是
"**本地 Web 服务 + 会话驱动的执行内核 + 真实外部 Agent 执行**"。

- **核心生产链真实闭环**: 用户会话 → 计划 → 任务 → 依赖调度 → 外部执行 → 回写 → 聚合 → 审计
  (多轮真实 E2E 验证, 1049+ 测试)
- **主要限制**: 需求无法追踪到执行 (Requirements 无下游引用); PRD 域实体不存在;
  模型选择无动态控制面; Artifact/验证未闭环到会话链
- **总体成熟度**: Capability Reality 85.2 / Contract Fulfillment 75.0 / Production Closure 49.8
- **最重要事实**: "执行的执行"真实(Agent 有 100 条真实执行记录), "理解需求"部分(捕获真实,
  追踪缺失), "控制模型"未接(LLMRouter 无消费)

## 2. Project Identity

- 名称: AI Software Factory (pyproject name=ai-software-factory, v1.1.364)
- 定位: AI 软件开发工厂 — 从需求到代码的自动化 (产品方案书 523KB)
- 运行形态: 本地 uvicorn 后端 (8011) + vite WebUI (5180) + CLI
- 主要 Package: factory-console (Web/会话) / factory-org (领域 SSOT) /
  factory-exec (员工执行器) / factory-core (独立 Factory OS) / factory-runtime (独立 runtime)

## 3. Current System Architecture

```
User
 ↓ PROVEN
Session (M4: 81 sessions)
 ↓ PROVEN
Intent (M4: execution_truth)
 ↓ PROVEN (capture) / ABSENT (trace)
Requirement (requirements.json 7 条, 无下游)
 ↓ ABSENT
PRD (实体不存在, M3 承诺)
 ↓ PROVEN
Planning (M4: plan_development + approve + execute)
 ↓ PROVEN
Task (M4: backlog 八态 + dependency)
 ↓ PROVEN
Agent (M3: gateway router, records 100)
 ↓ PROVEN
LLM (M4: llm_fn → deepseek)
 ↓ PROVEN
Tool (M3: _fc 注册)
 ↓ PROVEN
Execution (M4: 会话链 E2E)
 ↓ PARTIAL
Verification (M2: exec test_result)
 ↓ PARTIAL
Artifact (M2: exec ART-*)
 ↓ PROVEN
Audit (M4: 5160 events)
 ↓ PROVEN
Result → Session (M3: progress_card)
```

## 4. Real Production Flow (E2E 证明)

| 节点 | Status | Evidence |
|------|--------|----------|
| User → Session | PROVEN | POST /messages, console_sessions |
| Plan 创建 | PROVEN | plan_development → session_plans (PLAN-*) |
| Plan 批准 | PROVEN | approve → execute_plan (幂等 85c237f0) |
| Task 创建 | PROVEN | plan_id 关联 backlog (TASK-*) |
| Dependency | PROVEN | ExecState.next 门控 (914bc341) |
| ExecState | PROVEN | session_exec 持久化 + recover (d6f1de6b) |
| Run | PROVEN | gateway registry |
| 执行回写 | PROVEN | finish_task_exec done/failed/cancelled (2da/4e1) |
| 恢复 | PROVEN | recover E2E (UNKNOWN 重排队) |
| 聚合 | PROVEN | reconcile_plan completed/failed (9b8734ad) |
| 审计 | PROVEN | audit_events + task.history |

## 5. User Can Actually Do What?

### Project (PROVEN)
创建/管理/查询项目; backlog CRUD; sprint/milestone/roadmap (org + API + UI)

### Session (PROVEN)
创建会话; 发消息; 多轮执行; 停止 (cancel); 查看进度卡 (progress_card)

### Planning (PROVEN)
说"制定开发计划" → 计划持久化 (pending) → 批准 → 任务自动创建 (带依赖)

### Task/Execution (PROVEN)
任务依赖调度 (Ready/Waiting/Blocked); 失败传播; 取消 (CANCELLED); 恢复 (recover);
FAILED retry; 计划自动 completed/failed 聚合

### Agent (PROVEN, exec 域)
外部 Agent 执行 (backend-1 等, 87 success / 13 failed records); artifacts 产出

### Requirement (PARTIAL)
需求捕获 + requirements.json 持久化 + 查询 API (PROVEN); 追踪到执行 (不 PROVEN)

### Audit (PROVEN)
事件持久化 + 审计查询 API + 执行追溯 (task.history + audit_events)

## 6. User Cannot Yet Do What?

- 需求 → PRD → Plan 的完整产品链路 (PRD 实体 ABSENT)
- 需求变更 → 版本化 → replan (FUTURE M3)
- 模型/Provider 动态选择 (LLMRouter 消费 0 — 已标✅承诺未兑现)
- 从会话链任务追到产物 (Artifact 未关联 backlog — UNKNOWN/ABSENT)
- 验证结果驱动下游 (Verification M2)
- 经验 → 学习 → 未来决策 (FUTURE M4)
- 专业角色 Agent (developer/pm 等) 的明确生产入口 (UNKNOWN — exec 有执行记录但触发链未完全证明)

## 7. Capability Inventory

见 MASTER_STATUS_TABLE.md (29 Atomic Capabilities, STEP 7 结果原样引用)

## 8. Capability Summary

- M4: 11 | M3: 7 | M2: 3 | M1: 4 | M0: 4
- CORE 18 / SUPPORTING 7 / FUTURE 4
- Reality 85.2 ≠ "项目完成 85.2%" — 它表示"已有能力的真实存在度"高;
  Contract Fulfillment 75 = 产品已承诺能力约 3/4 有兑现证据;
  Closure 49.8 = 完整闭环(含支撑/未来加权)约一半
  文字等级: FOUNDATION STRONG / CORE EXECUTION REAL / PRODUCT INTELLIGENCE PARTIAL /
  CONTROL PLANE PARTIAL / FULL PRODUCT LOOP INCOMPLETE

## 9. Requirement / Product Intelligence

| 项 | 状态 | 证据 |
|----|------|------|
| Requirement capture | PRODUCTION | agent_loop.py:795 → requirements.json |
| Requirement persistence | PRODUCTION | 7 条 VALIDATED |
| Requirement validation | PRODUCTION | status=VALIDATED 字段 |
| Requirement traceability | ABSENT | 无 plan/task 引用 |
| PRD 文档/模板 | 存在 | 文档级 (方案书 L6606) |
| PRD approval | PRODUCTION (文档级) | 审批门 (方案书 L6910 ✅) |
| PRD domain entity | ABSENT | M3 承诺 |
| Product Intelligence 分析 | IMPLEMENTED | product_intelligence action (不落盘, 返回 markdown) |

## 10. Planning / Task System

- Plan pending→executing→completed/failed (幂等+聚合, M4)
- Task backlog 八态 + dependency (M4)
- 三套 execution/task truth: backlog TASK-* / execution_plan T-* (M3) / exec T00x
  → STEP 6 结论: Domain Boundary Contract 缺失 / 原则冲突 (P-DG-04 SSOT vs P-MOD-02 模块独立) 待解

## 11. Agent System

| Agent | 状态 |
|-------|------|
| backend-1 / flutter-dev / pm-agent / architect-agent / qa-agent | PRODUCTION (exec 域, records) |
| claude.* / codex.* (external) | PRODUCTION (records) |
| developer/pm/architect/tester/release/uxui (独立 Agent 类) | IMPLEMENTED (触发入口 UNKNOWN) |
| Registered ≠ Production — agents.json 8 个注册 ≠ 8 个生产 Agent |

## 12. LLM System

Provider M3 / Configuration M3 / Invocation M4 / Catalog M2 / Selection M1 /
Routing M1 / Fallback M0 / Policy M1 / Cost M1 / Observability M3
→ 结论: 真实 LLM Invocation/Provider, Model Selection Control Plane 未闭环 (G-LLM-01 TRUE_GAP)

## 13. Orchestration

HYBRID: 执行动态 (依赖门控+Agent 路由+恢复 M4) / 规划半动态 (LLM 内容, 模板结构) /
模型静态 (无路由) / 生命周期固定链 (plan→approve→task→exec→reconcile)

## 14. Execution System (三域)

| 域 | 目的 | 证据 | 关系 |
|----|------|------|------|
| Session chain | 会话驱动执行 | E2E + session_exec | 主执行链 |
| M3 production_run | 历史执行系统 | actions.py:1758 | 与主链 ISOLATED |
| factory-exec | 员工执行 | records 100 + console 79 引用 | 部分集成 (懒装配) |

## 15. Artifact / Verification

- exec 域 Artifact 真实 (ART-* patch/test_result, event_refs) — M2
- 会话链 Task → Artifact 关联 ABSENT (backlog 无 artifact_ref)
- Verification: exec test_result 真实; 会话链 verify 在 ExecState; 无独立下游 — M2
→ 禁止把 exec 域真实推导为全系统 Artifact Lifecycle 完成

## 16. Governance / Audit / Observability

| 记录 | 生产 | 只写 | 无消费 |
|------|------|------|--------|
| audit_events | ✅ 5160 | — | — |
| session records | ✅ 81 | — | — |
| execution records | ✅ 100 | — | — |
| experience | — | ✅ 84 | ✅ (无读) |
| requirements | ✅ 7 | — | 下游无 |
| project records | ✅ 37 | — | — |

## 17. Data / Persistence Reality

requirements ✅读✅写✅API / sessions ✅ / audit ✅ / exec 全套 ✅ / agents ✅ / skills ✅(消费未知) /
memory ✅(写) / projects ✅ / experience ✅写(无读) / factory.db 3.3MB — **用途 UNKNOWN**

## 18. Package Reality

| 包 | 状态 |
|----|------|
| factory-console | Integrated Production Core (uvicorn + 371 API) |
| factory-org | Integrated Production Core (console 69 import) |
| factory-exec | Integrated Supporting (79 引用) + 独立 CLI |
| factory-core | Intentionally Independent (全仓消费 0; 原则 P-MOD-01 支撑) |
| factory-runtime | Independent/UNKNOWN (无运行痕迹) |

## 19. UI / CLI / API Reality

CLI: 4 条 (console/core/exec/runtime), console CLI 运行过
API: 371 端点 (静态), 会话/项目/执行端点真实 E2E; 大量管理/learning/optimization 端点 runtime UNKNOWN
WebUI: 5180 vite 真实服务, 任务/刷新/停止浏览器 E2E
Desktop: 空 (0 py)
→ Endpoint count ≠ Capability count

## 20. Current Progress

Capability Reality 85.2 / Contract Fulfillment 75.0 / Production Closure 49.8
文字等级: FOUNDATION STRONG, CORE EXECUTION REAL, PRODUCT INTELLIGENCE PARTIAL,
CONTROL PLANE PARTIAL, FULL PRODUCT LOOP INCOMPLETE

## 21. Current Reality by Layer

见 USER_JOURNEY_MATURITY (STEP 7) — 主链 M4, Req→PRD 断, Model M1, 验证/产物 M2

## 22. What Is Actually Finished (CLOSED_LOOP/PRODUCTION)

Session / Intent / Planning / Task Mgmt / Dependency / Cancellation / Execution /
Orchestration(会话链) / Audit / LLM Invocation / Project Mgmt = M4
Agent 执行 / Agent Selection / Recovery / Governance / WebUI / CLI / Tool = M3 (生产运行)

## 23. What Is Not Finished (M0/TRUE GAP)

Requirement Traceability (M0) / PRD Entity (M0) / Model Selection 生产 (M1+TRUE GAP G-LLM-01) /
Artifact 会话链关联 (TRUE GAP G-ART-01) / Replan (FUTURE) / Learning (FUTURE) / Release (FUTURE)

## 24. Top 10 Current Facts

1. 核心执行链 (会话→计划→任务→依赖→执行→聚合→审计) 真实 M4 (多轮 E2E + 1049+ 测试)
2. Requirement persistence 真实 (requirements.json 7 VALIDATED)
3. Requirement downstream traceability 缺失 (无 plan/task 引用)
4. PRD domain entity 不存在 (文档/审批有, M3 承诺)
5. LLM invocation 真实运行 (llm_fn→deepseek, usage 记录)
6. Model Selection production consumer = 0 (LLMRouter)
7. exec Agent 真实执行 (records 100, backend-1×48, 87 success)
8. exec 角色 Agent 触发入口 UNKNOWN
9. 三 execution domains 并存 (backlog/execution_plan/exec)
10. factory-core/runtime 生产职责无证据 (独立意图有原则支撑)

## 25. UNKNOWN Registry

factory-core 独立产品职责 / factory-runtime production role / exec 角色 Agent 触发 /
Release runtime / Learning runtime / factory.db 用途 / Verification downstream /
WebUI 全量状态一致性 / 371 API 未触发部分

## 26. Final Reality Statement

AI Factory 当前是一个**执行内核真实、产品智能层未闭环的 AI 软件开发平台**:
它已经能可靠地把"用户的自然语言开发意图"转成计划、任务和真实的外部 Agent 执行,
并对执行做依赖调度、取消、崩溃恢复、结果回写和审计 — 这条链是真实运行的 (M4)。
它还不能把"需求"结构化地贯穿到产物 (Requirement→PRD→Plan 断裂)、
不能让用户按任务选择模型 (无动态模型路由)、不能把执行产物完整关联回任务、还不能学习。
它的核心价值已经不在"能不能执行", 而在"能不能从需求到产品的完整智能闭环" —
后者目前约一半闭环 (Closure 49.8), 且产品自标 M3/M4 里程碑尚未到期。

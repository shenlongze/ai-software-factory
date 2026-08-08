# Sprint 7 — Current Capability 盘点

> 日期: 2026-08-08 | 基准: a70155d, pytest 5521, Sprint 6.5 完成
> 用途: Sprint 7 (Organization→Execution Pipeline) 设计输入

## 1. 已完成能力（真实验证）

```
✅ Agent 执行链路: Task → EmployeeExecutor → DeveloperAgent → v4-pro → Patch → 沙箱验证 → Report → Experience
✅ Employee 角色体系: roles.py 6 角色 (PM/UIDesigner/Architect/Developer/Tester/DevOps)
   + org Employee 模型 (company_id/role_ids/capabilities/knowledge_scope/performance)
✅ Task 生命周期: task create → 执行 → 审批 → 完成 (Core tasks 216 行)
✅ Benchmark 系统: benchmark_s6b (9 分级任务 + driver + 预检) + tests/benchmark (9 样本)
✅ Production 测量: Sprint 6.5 — 27/27 成功, 满分 93%, $0.789
✅ 模型选择依据: D-001 v4-pro = 生产模型 (数据驱动)
✅ Git 交付流程: 分阶段 commit + push (secure-transport)
✅ 沙箱安全: 副本 + git + 验证循环 (源零修改) + 审批 apply
✅ 经验闭环: ExperienceRecord (10A-4) + ContextExperience (T4.4) + ModelExperienceStats
```

## 2. 已存在模块（可复用）

| 模块 | 位置 | 复用点 |
|:-----|:-----|:-----|
| EmployeeExecutor | exec/employee_executor.py | 所有角色执行的统一入口 |
| roles.py (6 角色) | exec/roles.py | 角色→能力/提示词/阶段映射 |
| DeveloperAgent | exec/developer.py | Developer 执行核心 |
| AgentRuntime | exec/agent_runtime.py | 执行编排/验证循环/经验 |
| Context 智能 | exec/{ranking,progressive,budget,context}.py | 所有 Agent 的上下文 |
| Candidate/Evaluator | exec/{candidate,evaluator}.py | MultiRun 可靠性 |
| Capability Registry | exec/capability.py | 模型能力 |
| org (Company/Employee) | factory-org/org/ | 组织数据 |
| WorkflowEngine (任务级) | factory-core/workflows/ | 任务流程 (4 模板) |
| 产品链路 | factory-core/product/ | Idea→PRD→Approval (34 类) |
| Intelligence | factory-core/intelligence/ | 决策/推荐/经验 (40 类) |
| 验证 L1-L4 | factory-core/validation/ | 证据链 |
| s6b Benchmark | factory-exec/benchmark_s6b/ | 回归/验收 |
| 事件溯源 | factory-core/events/ | 158 事件审计 |

## 3. 当前限制（Sprint 7 要解决的）

```
🔴 组织-执行断链: Employee 建模但只有 Developer 能执行 (其余 5 角色 planning)
🔴 无多阶段协作: Task 直连单 Agent, 无 PM→Arch→Dev→Test 接力
🔴 Workflow 是任务级: 无 Project/Sprint 生命周期
🔴 无 Artifact 流转: 前一阶段产物 (PRD/设计) 不自动成为下一阶段输入
🔴 Tester 不可执行: 无 Developer↔Tester Loop
🔴 Release/Analytics: 无 build/package/analytics
🟡 角色双体系: org 模板 (CEO/PM/Architect/Developer/QA) vs exec roles.py (6 角色)
```

## 4. Sprint 7 设计输入（本盘点结论）

```
目标: 从 "AI Coding Worker" → "AI Software Organization"
核心: Organization → Execution Pipeline (多角色接力 + Artifact 流转 + 生命周期)
复用: EmployeeExecutor/roles/context/沙箱/经验 (零重写, 编排层新增)
```

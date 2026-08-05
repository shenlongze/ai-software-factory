# ADR-0008: Phase 4B-3 Agent Assignment Layer — 匹配/分配生命周期/Agent 状态边界/事件序/Execution 集成

> 状态: 已接受 | 日期: 2026-08-05 | 作者: 后端开发工程师
> 关联: `docs/design/phase4b3-status.md` · `docs/adr/0004-phase3b-agent-skill-registry.md` · `docs/adr/0007-phase4b2-execution-dispatch.md`

## 背景

Phase 3B 建立了 AgentRegistry (员工信息 + 状态 AVAILABLE/WORKING/OFFLINE, 只读状态,
无状态流转方法); Phase 4A 的 WorkflowStep 携带 required_skill/required_role 声明;
Phase 4B-1/4B-2 的 ExecutionRequest 有 agent_id 字段但仅由 task.owner 精确引用解析
(ADR-0006 决策 4, "按角色/技能自动分配属后续 Phase")。本阶段落地该后续: 新模块
`factory-core/assignment/` (AgentAssignment 模型 + AgentMatcher 匹配排序 + AgentAllocator
分配生命周期 + AssignmentStore JSON 持久化), AgentRegistry 增状态更新能力
(WORKING↔AVAILABLE), Event 集成 (agent.assignment.* + agent.released), Execution 集成
(回填 agent_id, 不自动执行), CLI `agent assign/assignments/release`。**无 Agent Runtime
执行 / 无 Workflow 自动执行**。

落地时有四处设计张力需明确:

1. **Agent 状态原语与事件归属**: 分配时 Agent 状态 WORKING↔AVAILABLE 由谁改、是否发事件 —
   AgentRegistry 现有 update() 会发 agent.updated, 直接复用会造成事件语义混杂
   (员工信息更新 vs 工作状态流转)。
2. **Assignment 状态机与事件覆盖**: phase4b3-status 只列 allocator 三个方法
   (assign/release/complete), 但 AssignmentStatus 含 WORKING/FAILED, 事件清单含
   agent.assignment.started/failed — 缺少对应转换方法则状态与事件不可达。
3. **状态原语不发事件的审计缺口**: 若 Agent 状态变更完全不落事件, 审计无法追溯
   "谁占用/释放了哪个 Agent" — 需定义状态变更的审计承载。
4. **Execution 集成的回填语义**: "支持 ExecutionRequest.agent_id 填充 (自动分配后填
   agent_id)" — 何时校验执行存在、是否发新事件、是否影响执行状态。

## 决策

1. **Assignment 状态机与事件序 (完整覆盖五状态/五事件)**:
   - 状态机: `ASSIGNED → {WORKING, COMPLETED, FAILED, RELEASED}`;
     `WORKING → {COMPLETED, FAILED, RELEASED}`; COMPLETED/FAILED/RELEASED 终态 (无出口)。
   - Allocator 方法 (assign/start/complete/fail/release): assign→**created**;
     start→**started**; complete→**completed** 然后 **released**; fail→**failed** 然后
     **released**; release→**released**。多事件时返回最后一个 (最相关, 同
     workflows.complete_step 口径)。`is_valid_transition` 公开供审计/测试。
   - start/fail 为 phase4b3-status 未明列的必要补充: 无它们 WORKING/FAILED 状态与
     started/failed 事件不可达 — 属最小完备集, 单行转换, 不扩展范围。
2. **AgentMatcher 排序语义 (skill 匹配数量优先)**: 过滤 ① role 必须精确匹配
   ② Agent.skills 必须至少命中一个 required_skill (单技能步骤即"必须包含该技能")
   ③ status 必须 AVAILABLE; 排序主键 = 命中必需技能数降序 (required_skill 支持
   str|list, 多技能步骤按覆盖度择优), 次键 = agent id 升序 (确定性 tie-break)。
   返回 (agent, matched_count) 列表, allocator 取首位即最优。纯读模块不发事件。
3. **Agent 状态原语不发事件, 审计由 assignment 事件承载**: AgentRegistry 新增
   `set_status(agent_id, status)` / `mark_working(agent_id, task_id=None)` /
   `mark_available(agent_id)` — 低层原语, 仅改 Agent 自身状态 (+current_task 引用,
   不复制任务数据), **不发事件**; 占用/释放的审计由 agent.assignment.created /
   agent.released 等 assignment 域事件携带 (payload.agent_status 记录流转后状态)。
   避免 agent.updated 语义混杂 (员工信息更新 ≠ 工作状态流转)。Registry 仍不复制
   Assignment 数据 (Agent != Assignment 原则不变)。
4. **Execution 回填语义**: allocator.assign(execution_id=...) 且装配 runtime_store 时:
   (a) 先校验执行请求存在 (不存在 → AgentAllocatorError, 不产生半途状态变更);
   (b) 分配成功后将 request.agent_id 回填并落库; (c) 不自动执行、不改执行状态、
   **不发新事件** (执行生命周期事件仍属 execution.*, 创建时已发 execution.created)。
5. **AssignmentStore 单文件单节 JSON**: `<root>/assignments/assignments.json`
   `{id: AgentAssignment dict}`, 原子写 os.replace, 损坏抛 CorruptAssignmentStoreError
   (同 agents/workflows/runtime 模式); 目录由首次原子写自动创建 (同 runtime 模式
   ADR-0006 决策 5 — 不依赖 context.py 骨架, 不新增子目录枚举)。
6. **CLI 读命令发 agent.assignment.viewed**: ADR-0002 铁律 (所有 CLI 行为必须产生
   Event) 要求读命令补 viewed 事件, 与 agent.viewed/workflow.viewed/execution.viewed
   同模式; EventType 仅做枚举扩展 (ADR-0001 决策 1, 不改表结构/API)。

## 后果

- EventType 新增 6 成员: agent.assignment.created/started/completed/failed/viewed +
  agent.released (纯增量, 既有事件不变)。
- AgentRegistry 仅新增 3 个状态原语方法 (set_status/mark_working/mark_available, 不发
  事件); SkillRegistry / Event API / Task API / Validation API / workflows / runtime /
  execution 均零改动。
- 新模块 `factory-core/assignment/` 4 文件 (models/matcher/allocator/store + __init__);
  Assignment 引用 agent_id/task_id/execution_id, 不内嵌 Agent 数据。
- CLI: `factory agent assign --task T-001 --step development [--agent A-001]
  [--execution EX-001]` (输出 `Assigned: <agent name>`, 退出码 7 未找到 / 1 不可用
  或无候选 / 2 用法) + `factory agent assignments [--task/--agent/--status]` +
  `factory agent release ASSIGNMENT_ID`; 均支持 `--json`。
- 手动冒烟链路: `agent add --id A-001 --role backend-developer --skills development`
  → `task create --id T-001` → `workflow add --id feature-delivery` → `agent assign
  --task T-001 --step development` (Assigned: A-001) → `agent assignments` →
  `agent release ASG-001` (A-001 回 AVAILABLE)。
- 测试: `tests/assignment/` 新增 (模型/存储/匹配器/分配器/Agent 状态/事件流/CLI/
  Execution 集成), 684 基线不回归 (已验)。
- 风险: 单进程整文件 JSON 写 (同既有 store); 匹配为纯声明式 (role/skill 精确匹配,
  无模糊/权重评分 — 未来可按需扩展); 分配与执行解耦 (回填 agent_id 不触发执行,
  ExecutionRunner 不变)。
- 后续 Phase: Agent Runtime 真正执行时由 assignment → execution 建立运行态绑定
  (本阶段仅回填引用); runtimes/ 入 context.py 骨架仍待落地 (ADR-0006 决策 5 遗留)。

# 00 — S48 审计: PLAN→Task Tree→Production Execution (READ-ONLY, 2026-09-07)

## 目标
验证 Conversation 产生的 PLAN 能否成为真实生产系统输入 (优先复用
S0.5–S46 基础设施, 不重造)。

## 现成可接 (全部既有, 取证)
1. PLAN→Task Tree
   - execute_plan (agent_loop 457): 审批通过 → backlog task 真实创建
     + P1-R1 依赖解析 (plan task title → Task ID) + approval API
   - S47-E5: execute_plan 成功 → canonical PLAN-* (approved) 落盘
   - P1-FIX (agent_loop 1132+): 建任务后自动初始化 ExecState 执行链
     (依赖从 backlog SSOT 读) — execute_plan 一调即备好逐任务推进
2. Task→Execution
   - chain_next 工具: 执行链逐任务推进 (委派执行→验证→回写)
   - execute_task (actions 1367) → cmd_exec_run (真实 Agent Runtime,
     AgentExecutionResult 统一结构); agent select; objective 透传
   - orchestrator.py: can_execute/can_retry/can_repair 政策
   - eval_loop: 低分 → 建议 → 应用 → 复验
3. Execution→Truth
   - execution_truth.py: 工具事件 (create_task/task_action/execute_plan)
     收敛; 任务状态回写 backlog SSOT + ExecState (agent_loop 1773)
   - node_runtime NodeRun; S46 全自动 absorb (workflow → EXS/art/ver)
4. Verify/Repair
   - chain_next 委派含 verify; DevTestLoop (S46 repair/retest 实证);
     orchestrator repair 政策
5. 全自动备选: workflow_runner 8 阶段 (S46 实证 production→RELEASE)

## 分层 (合理, 非重复)
- canonical PLAN-* = 事实 (E5) | ExecState.plan = 会话执行工作态 |
  backlog Task = 任务 SSOT | ExecState.tasks = 工作态引用
- 执行权: Agent Runtime (cmd_exec_run) / node_runtime — 单一

## 缺口/需验证
1. **会话驱动 task-by-task 完整链从未端到端实测**: Conversation(继续)
   → execute_plan → chain_next 逐任务 → artifact → verify → repair →
   deliver — 各部分存在, 未串成全链验收 (S46 走的是 workflow_runner
   全自动旁路, 非 chain_next 逐任务)
2. canonical PLAN → chain_next 关联: execute_plan 产出 backlog +
   ExecState; canonical PLAN-* 是否被后续逐任务链引用 (task 回写 plan_id
   S34-P0-E 有 plan 关联) — 需验证链上可见
3. "只许说继续" 的跨阶段驱动 (IDEA→…→deliver) 无整体测试

## S48 建议 (待批准)
真 E2E: 飞机大战新会话, 用户仅自然语言 + "继续", 全链推进
IDEA→DISC→REQ→PRD→PLAN→(审批)→Task→chain_next→artifact→verify→
repair→deliver; 全用既有 execute_plan/chain_next/cmd_exec_run; 发现
结构性断点即停报。不做新执行器/新 orchestrator。

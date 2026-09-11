# Product Node × Node Runtime — Compatibility & Design Audit (2026-09-07, READ-ONLY)

## 1. NodeRun Contract 到底抽象了什么 (代码取证 node_runtime.py)
- Node (定义): node_id/name/type + input_contract + output_contract +
  execution_policy — 通用模板, 无执行耦合
- NodeRun (执行事实): run_id/node_id/task_id/state + input/trigger/
  executor/agent/model + artifact_id + verification + failure_reason +
  history (append-only 状态事实)
- 生命周期: PENDING→RUNNING→VERIFYING→COMPLETED/FAILED
- Verify 四态 PASS/FAIL/INCONCLUSIVE/BLOCKED; 产物 absorb → artifact
  (type="report" 已支持文本输出 absorb — S46 实证)

## 2-3. Execution 特有 vs 通用
Execution 特有 (少): executor/agent/model 字段 (外部执行); task_id 锚;
产物 absorb 路径 (EXS→art)
通用 (主体): Node 模板/input/output contract; NodeRun 状态机;
verify; history; failure — 无 execution 耦合 → 可承载产品前链

## 4. Human Decision 作为标准生命周期事件?
现状: 无 (NodeRun 状态无 AWAIT_DECISION; RUNNING 内人工步未建模)
需求: 产品节点核心 = 决策门 (findings→提问→用户选→再继续)
→ 需最小扩展: AWAIT_DECISION 状态 (RUNNING→AWAIT_DECISION→RUNNING)
  或 decision-gate 事件记录 — 单一扩展点, 不动既有状态机语义
  (FAILED/COMPLETED 不变)

## 5. Evidence/Artifact 能否承载分析结果?
能: artifact type="report" 已可 absorb 文本 (findings/分析输出);
decision 记录 (人类选择 + who/when) 需新事件类型 (轻)
不必造新产物体系 — 复用 Artifact Lifecycle

## 6-8. Completion / Exit / Recovery
- Completion: COMPLETED 由 verify 定; 产品节点 completion =
  verify(完整性收敛: 无新 findings + 决策齐) → 映射成立
- Exit/Transition: NodeRun 无跨节点概念 (COMPLETED 止);
  下游由【编排者】起新 NodeRun — S46 production run 已实现阶段编排
  pattern (8 阶段串) → 前链编排复用同一 pattern
- Recovery/Resume: 现无 Repair/中断恢复 (S2 注释"最小: 无 Repair")
  → 产品节点需要: RUNNING 中断 → resume 需 checkpoint —
  最小方案: NodeRun input 累计 (progress: 已完成维度/待决/迭代) 存
  run["checkpoint"], 重入时续跑 (新字段, 不破坏状态机)

## 9. Conversation 职责 (Node 化后)
human interface: 理解意图 → 定位/创建 NodeRun → 展示 finding/提问 →
 收人类决策 → 写回 → 展示 verify/completion → 提议下节点
Conversation 层不再承担执行语义 (分析/完成/继续判定归 NodeRun)

## 10-11. 前链 5 节点是否同一 Node?
是 (状态机/verify/artifact 同构); 差异在:
- output_contract: 落 product_truth 记录 kind (idea/disc/req/prd/plan)
- execution_policy/work 内容: 分析型 (findings/决策) vs 生成型
- artifact type: 需求/PRD 报告 vs 代码
→ 用 Node 模板参数表达, 非新状态机 (避免"换地方打补丁")

## 12. 统一模型
Conversation → Node(产品节点模板) → NodeRun → Work(分析/生成)
→ Findings/Evidence + Human Decision → Verify(收敛/完整性)
→ COMPLETED → 编排者起下一 NodeRun → … → 执行段 (既有 task-execution
NodeRun) — 前链与执行共享同一 Contract

## 兼容性结论
- NodeRun Contract 通用性成立 → 前链 Node 化【不需要新 Runtime】
- 需最小扩展 (3 处, 不破坏既有):
  E1: AWAIT_DECISION 状态/决策事件 (Human Decision 标准门)
  E2: run checkpoint (resume/迭代进度)
  E3: 编排者前链 stage 串接 (复用 production_run 阶段编排 pattern)
- 试点建议: requirement-analysis Node (输出: Findings 报告 artifact +
  决策记录; verify: 收敛性) — 验证 E1/E2 后再铺 PRD/PLAN

## 状态
READ-ONLY 完成。未改码/未 commit。待用户批准设计后才实施。

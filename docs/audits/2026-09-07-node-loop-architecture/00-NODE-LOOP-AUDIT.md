# Node / Loop 全局架构审计 (2026-09-07, READ-ONLY)

## 核心发现: 两套执行体系并存, Node 契约只覆盖了执行段
体系 A (真 Node Loop 契约 — S2 Primitive):
  node_runtime.py: register_node / create_node_run / NodeRun
  PENDING→RUNNING→VERIFYING→COMPLETED/FAILED + Artifact Lifecycle
  实际注册: task-execution (agent_loop _chain_task_run 617) +
  workflow/production_run (S46 8 阶段 run: stages/evidence/repair/
  retest/artifact) — 覆盖 EXECUTION→VERIFY 段 ✓ 真实 Loop

体系 B (Conversation 语义层 — 修补场):
  S47 E1-E5 (governor/resolver/guide/conv_state) + S48 gate +
  S49 context + S50 entry gate — 全作用于【产品前链记录】
  IDEA/DISC/REQ/PRD/PLAN = product_truth 记录 + 会话自由操作
  → 产品前链节点【未 Node 化】— 无 NodeRun/无 Objective/无 Evidence/
  无 Human Decision 门/无 Completion Criteria/无 Exit Transition

## S48-S50 偏离点定位
- Requirement Node 应有 Node Loop: 进入→分析→发现→问题→用户决策→
  更新→重析→完整性验证→收敛→exit
- 实际: Requirement = 记录; "分析" = 会话层 get+LLM+save;
  "完成/继续/退出" 语义缺失 → S50 各修补 (gate/entry/analysis)
  全打在无 Node 契约的面上 → 补丁堆叠 (拆东墙)
- 深层: Conversation 语义层在【模拟】Node (continue=resume,
  refinement=redo), 而真 Node 契约 (node_runtime) 只服务 execution

## 为什么这是关键
用户问题 "继续分析为什么反复" 的架构根因:
  Requirement Analysis 不是 NodeRun — 无 state(维度/发现/待决/确认/
  迭代)、无 human decision 门、无 completion、无 exit →
  "继续" 无停点可恢复, 只能重推 → 读→写循环
任何在 Conversation 层继续加 resolver/skill/gate 都无法根治 —
因为缺的是该节点进入 Node Loop 契约。

## 统一方案候选 (不造新 runtime — 扩展既有 S2 Primitive)
Product Chain Node 化: 每节点 (requirement-analysis/prd/plan...) 作为
Node 注册 (register_node), Conversation 只是 Node 的 human interface:
  Conversation → NodeRun (resume/continue = 恢复 NodeRun state)
  Node 内: work → findings → human decision(提问/确认) → update →
  verify(完整性) → completion(收敛) → exit(transition 下节点)
  产物: Artifact/Evidence 走既有 lifecycle
执行段 (task-execution/workflow run) 已符合 — 前链补 Node 化后,
"S50 需要的全链" = 前链 NodeRun → 执行 NodeRun 串接, Conversation
统一入口。

## 判定
- 不是"再造统一 Node Runtime" — node_runtime 已是统一契约, 只覆盖
  执行段; 需扩展到产品前链节点 (register/run 化)
- 停止 Conversation 层修补 (governor/resolver 保留为 human-interface
  语义层, 不再承担 Node 执行语义)
- 这是一次架构补全 (前链 Node 化), 非新系统

## 待用户决策
1. 是否批准前链 Node 化设计 (先出设计文档, 再实施)
2. 实施顺序建议: requirement-analysis Node 为首个试点
   (验证 Node Loop Contract 在分析节点的完整效果)

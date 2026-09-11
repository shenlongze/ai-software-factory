# 02 — Product Node × Node Runtime IMPLEMENTATION DESIGN (2026-09-07, DESIGN ONLY)

## 1. Executive Summary
NodeRun Contract (node_runtime.py) 通用性成立。前链 Node 化 = 既有
runtime 补 3 个通用扩展 (E1 决策门 / E2 checkpoint / E3 编排) + 产品
节点模板, 不造新 runtime。requirement-analysis 为试点。DESIGN READY。

## 2. Current Contract (代码取证)
Node: node_id/name/type/input_contract/output_contract/
  execution_policy (register_node 71)
NodeRun: run_id/node_id/task_id/state/input/trigger/executor/agent/
  model/artifact_id/verification/failure_reason/history(append-only)
  状态: PENDING→RUNNING→VERIFYING→COMPLETED/FAILED (NODERUN_STATES 29)
  转换表 32-38; transition_node_run 231 (非法跳转 NodeError)
  execute_node_run 472 (executor_fn 契约 {ok, output, error,
    artifact_type, verification})
  finalize_node_run 398 (终态幂等)
  artifact absorb 251 (output→art-* type=report, exs_id 幂等)
  verify 物化 289 (verify_meta→ver-* store, run 存引用快照)
  audit event (196 _record + AuditEvent NODE_RUN_*)
执行特有: executor/agent/model + task_id 锚 + EXS absorb
通用: 其余全部

## 3. Unified Node Contract
Node: +objective +completion_criteria (既有字段可承载, 加语义约定;
  execution_policy 内嵌 policy/objective 结构化)
NodeRun: 现字段 + checkpoint(E2) + decisions(E1) — 新字段可选默认,
  不破坏既有 run (向后兼容读取)

## 4. E1 Decision Gate
- 新状态 AWAIT_DECISION; 转换 RUNNING→AWAIT_DECISION→RUNNING
  (NODERUN_TRANSITIONS 增加; COMPLETED/FAILED 不动)
- 触发者: 编排/能力 (非 LLM) — find_decision 时工具写 decision 请求
- Decision Event: run["decisions"].append({decision_id, question,
  options, finding_refs, status: PENDING|RESOLVED, chosen, actor, at})
- 事实源: NodeRun.decisions + audit event (DECISION_*); 禁止
  description 文本冒充 (product_truth 写仅在 DECISION_RECORDED 后经
  ProductTruthService — 见 §9)
- LLM 不可自标 confirmed (decision 写需 actor=human 校验 / 工具层
  decision 门); save_product_record 对需决策字段 → governance denied
  (reason: pending_decision)
- resume: AWAIT_DECISION 下 continue → 不得跳过; 仅人类决策事件
  可 RESOLVED → 回 RUNNING

## 5. E2 Checkpoint / Resume
- run["checkpoint"] = {iteration, completed_dimensions[],
  findings[] refs, open_issues[], pending_decisions[],
  resolved_decisions[], next_work, verification_progress}
  (仅存引用/计数 — 完整 finding 在 artifact/analysis store §8)
- resume: 定位当前 NodeRun (项目最新 RUNNING/AWAIT_DECISION) →
  读 checkpoint → 注入 executor prompt (从 next_work 续) → RUNNING
- 幂等: 重复 continue 同 checkpoint → executor 幂等键 (dimension 已
  completed 不重做); iteration+1 仅真实新工作
- crash: 中断 run 留 RUNNING → 下次 resume 前 crash-detection
  (heartbeat 时间戳, 超时→续)
- completed resume → NodeError 指引 (已 COMPLETED; 新工作=新 NodeRun
  或 advance)
- AWAIT_DECISION resume → 仅展示 pending 决策 (不执行)
- FAILED resume → 新 attempt (attempt 字段, 不覆写 FAILED 历史)

## 6. E3 Node Transition (编排)
- NodeRun A COMPLETED → 编排者 (workflow_chain 轻函数, 复用
  production_run 阶段编排 pattern) → 校验 A 完成事实 +
  completion_criteria → create_node_run(Node B) → 写 transition
  event {from_run, to_run, criteria_evidence}
- 谁: 编排者 (Conversation 工具链一层 "advance_product_chain";
  非 NodeRun 内部跨节点 — 防 PRD 逻辑进 REQ run)
- exactly-once: from_run COMPLETED 幂等 + to_run 由 from_run_id 派生
  键 (同 from 不重复建 B)
- B 创建失败 → A 保持 COMPLETED; 编排记录 failed_transition →
  重试幂等
- 复用 production_run 模式, 不造第二 workflow engine

## 7. Product Node Template
同一 Node Contract (状态机/verify/artifact 同构):
IDEA/DISC/REQ/PRD/PLAN 差异 = 模板参数:
- node_type: idea/discovery/requirement/prd/plan (capability 选择面)
- output_contract: 落 product_truth kind
- execution_policy.work: 分析型/生成型 (同一 executor 适配)
- completion_criteria: 各阶段收敛判据
统一成立 (状态机无需分支) — 非强行统一, 执行段 task-execution 已
证明同一状态机承载不同 node_type

## 8. Requirement Analysis Node (Pilot)
Node Type: requirement-analysis
- Objective: 对当前 REQ 做多维度完整性分析, 产出结构化 findings +
  决策点, 收敛后转 PRD
- Input: project_id + requirement record id + (可选)目标维度
- Work Capability: analysis executor (prompt 结构: 输入 REQ 正文 +
  维度清单 → 输出 findings JSON)
  维度: 功能完整性/业务规则与流程/边界与异常/交互与状态/非功能
  (性能兼容存储)/验收标准/范围 MVP/未决问题
- Checkpoint: §5 (completed_dimensions/open_findings/pending_decisions)
- Decision: 射击方式类决策点 → AWAIT_DECISION → 用户选择 → 写 REQ
- Verification: 收敛性 (新维度无新 finding + 决策齐 = PASS;
  有 open issue = INCONCLUSIVE → 续析)
- Completion: verify PASS + 无 pending → COMPLETED
- Exit: 编排者 → PRD NodeRun
- Recovery: FAILED (executor 错误) → attempt 重跑; 中断 → resume

## 9. Analysis Result / Finding Contract
- Finding 记录: {finding_id, dimension, type: gap|ambiguity|
  contradiction|missing_constraint|suggestion, severity, question,
  evidence_ref, recommendation, status: open|resolved|accepted,
  decision_ref?}
- 存哪: artifact (analysis report art-*; 复用 artifact_lifecycle
  type="report" absorb — NodeRun 产物, 可追踪) + checkpoint 引用
  (SSOT = artifact store; run 只存引用/摘要 — 同 verify 模式)
- Decision: NodeRun.decisions (SSOT) → 写 product_truth 时引用
- 禁止: finding 只在聊天; save_product_record 冒充 analysis 输出

## 10. Product Truth Boundary
NodeRun = 生产过程事实; Product Truth = 产品领域事实
- 写 Truth 时机: DECISION 后 / verify 收敛后; 谁写:
  ProductTruthService 封装 (经 NodeRun 授权调用)
- 状态允许: draft (分析中) / confirmed (决策齐 + verify pass)
- 用户确认处: Decision Gate (E1) — description 自标 confirmed 禁止
  (save handler: 状态字段 protected; content 不得含状态声明 — 现有
  agent 自标 confirmed bug 的根治)
- save_product_record 保留但定位 = Truth 写入边界 (governed by
  NodeRun/decision), 非分析入口

## 11. Conversation Boundary
- Governor/Resolver 保留为【意图→NodeRun】adapter:
  "继续/继续分析/分析更多/确认/不同意/换方案" → 映射 NodeRun 动作
  (resume/advance_dimension/decision/refine) — 转换表由 NodeRun 状态
  驱动, 非 LLM 猜 (checkpoint 决定 next_work)
- 删除倾向: 不再承担执行语义的 guide 文本 (执行指令等收敛为 NodeRun
  resume); conv_state 降级为 UI 会话引用 (NodeRun checkpoint 为执行
  事实)
- Conversation 可解释意图; NodeRun 拥有执行事实/生命周期

## 12. Execution Node Compatibility
task-execution/workflow 不变: 同一 transition 表 (新加 AWAIT_DECISION
仅新增边, 不动既有); checkpoint/decisions 新字段默认缺省 — 旧 run
读取兼容 (get_node_run 返回无新字段 → 编排按无 checkpoint 处理);
artifact/verify/audit 路径零改动

## 13. Migration / Backward
无数据迁移: 新字段可选; 旧 NodeRun 照常; 旧 product_truth 不动;
legacy session_exec/conv_state 保留读取; 新旧 NodeRun 共存 (靠
node_id/node_type 区分); rollout: 先注册 requirement-analysis 节点 +
executor, 旧 Conversation 路径保留 (feature flag), rollback = 停用
节点 + 恢复旧 continue 引导 (不改数据)

## 14. S50 Impact
- IDEA→…→PLAN: 本设计覆盖 (Node 化 + 编排)
- PLAN→TASK→EXECUTION→VERIFY: 既有 NodeRun 覆盖 ✓
- REPAIR: execution repair 既有 (attempt); analysis repair = 新维度续析
- ACCEPTANCE/RELEASE/DELIVERY: 既有 truth 链, 不受影响
- create_task bypass: Node 化后由编排边界负责 (create_task 仅
  PLAN NodeRun COMPLETED 后经编排创建 — 既有 production entry gate
  保持, 语义升级为"编排授权的 TASK 创建")

## 15. Test Matrix
Contract: node 创建/run 创建/lifecycle (含新 AWAIT_DECISION 边)/
checkpoint 读写/resume 幂等/crash/decision 写/completion
Analysis: 首析/继续(维度续)/更多(扩维)/发现/等决策/确认/拒绝/修改/
resume 重复/crash 恢复/收敛/complete/转 PRD
Regression: task-execution/workflow run/artifact/ver/evidence/acc/
release/delivery 全绿; 335+1 pre-existing CLI 维持

## 16. Failure / Recovery Model
- executor FAIL → attempt++ 重跑 (既有)
- 中断 (crash) → RUNNING 残留 → resume 续 (checkpoint)
- 决策缺失 → AWAIT_DECISION 卡 (不执行不写) → 人类决策恢复
- 收敛未达 → INCONCLUSIVE → 续析下一维度
- 跨节点失败 → A COMPLETED 幂等重试建 B

## 17. Rollout / Rollback
试点 = requirement-analysis Node (单节点上线) → 验证 E1/E2 →
PRD/PLAN/IDEA/DISC 逐个模板化 → feature flag 并行 → 稳定后旧路径
停用。rollback: flag 关 + 旧 continue 引导恢复 (零数据迁移)

## 18. Architecture Anti-pattern Audit
无新 Manager/StateMachine/Resolver/Engine/Runtime; 无 Conversation
自持事实; 无 Truth 兼任 NodeRun; LLM 不自宣完成 (verify 收敛判);
description 不冒充 decision (decisions SSOT); save 不冒充 analysis;
resolver 不冒充执行 (NodeRun checkpoint 驱动)

## 19. Open Questions
- Q1 executor 形态: analysis executor = LLM prompt 函数 (execute_node_
  run executor_fn) — 与 task-execution 外部 executor 同一契约? (建议是)
- Q2 decision options 来源: executor findings 内建议默认 (LLM 生成
  options + 建议) vs 硬编码 — 前者, 人类选/改
- Q3 同项目多 REQ (1:N): requirement-analysis NodeRun 按哪个 REQ?
  (建议: NodeRun input 显式 requirement_id)
- Q4 AWAIT_DECISION 是否要独立"卡 UI": 轻量 (run 状态投影即可)

## 20. Final Recommendation
DESIGN READY → 进入 Implementation Phase:
- Phase 1: node_runtime E1+E2 (状态/字段/转换 + tests) —
  不触产品语义
- Phase 2: requirement-analysis Node (executor + findings artifact +
  决策门 + checkpoint) — 试点验证
- Phase 3: 编排 (advance_product_chain) + PRD/PLAN 模板化
- 每 Phase: targeted + regression + 真实 E2E, commit NO PUSH

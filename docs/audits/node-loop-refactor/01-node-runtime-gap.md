# 01 Node Runtime Gap
- 缺 WAITING_FOR_USER 状态 (无 Human Decision 标准门) — LLM 只能文本问,
  无事实化 WAIT
- 缺 checkpoint/resume — NodeRun 不知道自己做到哪 (iteration/findings/
  open_questions/next_work)
- 缺 Decision Event (actor/decision/chosen) — 无人类决策事实
- REPAIRING 状态被 _record 注入但不在 NODERUN_STATES/TRANSITIONS (不一致)
- 产品前链节点无 NodeRun (Requirement/PRD/PLAN 分析无 objective/checkpoint/
  verify/completion)
收敛: 扩展既有 (E1 WAIT+Decision / E2 checkpoint+resume), 不新建 runtime

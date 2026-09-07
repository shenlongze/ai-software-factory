# 04 State Duplication
- 会话工作态散落: conv_state(语义) session_state session_plans(计划待批)
  session_exec/exec_state(执行态) topic_ledger session_topics chat.json
- NodeRun checkpoint 将承接"当前工作进度" (权威), conv_state 收敛为
  会话引用 (session_id→NodeRun id), exec_state 保留执行段工作态
- 不迁移旧数据; 新 NodeRun 先行, 兼容读取

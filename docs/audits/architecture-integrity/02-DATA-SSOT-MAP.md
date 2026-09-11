# 02 — Data SSOT Map
实体 SSOT | 投影/派生 | 重复?
Task: ManagementStore(task.json) | UI/status 读 service | id↔slug 已修(残余 slug 双口径 P2)
REQ/PRD/…: product_truth store | project_lifecycle 读 | 无
NodeRun: nodes/runs | UI run 卡 | 无
ACC/RELEASE: acceptance/release truth | UI | 无
会话消息: console_sessions | chat.json(旧?) | chat.json 疑似 legacy P2
会话工作态: conv_state.json | exec_state/session_plans/session_topics | 多 store P1 收敛面
任务: ManagementStore backlog | session_exec(执行态引用) | 职责分开(backlog SSOT, exec 工作态) OK
结论: 域 truth 无 P0 双 SSOT; 会话侧多 store = P1 面(偏离2)

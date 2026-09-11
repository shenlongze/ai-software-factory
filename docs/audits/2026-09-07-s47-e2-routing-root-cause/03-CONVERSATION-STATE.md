# 03 — CONVERSATION STATE (证据)

实际保存 (sessions_store):
- messages[]: {role, content} — 事实历史
- tool_calls: 存于消息 meta (前端可见)

未保存 (每轮从文本重猜):
- active_topic / active_domain (无)
- pending_proposal (无结构化; [3] 提议只存在于文本; 检测靠句尾正则)
- constraints / referenced_entities (无)
- 错误 assistant 回复进入历史后无恢复 (pollution 无法自愈)

结论: Conversation State = PARTIAL/NO (仅有 history; 无语义状态层)

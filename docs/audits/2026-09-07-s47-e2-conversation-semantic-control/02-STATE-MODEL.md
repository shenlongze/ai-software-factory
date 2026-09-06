# 02 — State Model
conv_state.json: {session_id: {topic, domain, relation, pending}}
- topic/domain: 上轮语义 (供 continue/reference 保持)
- pending: 待确认提议 (LLM 从上轮提取; 非句尾正则)
- 每轮 governor 更新; 失败保守不破坏

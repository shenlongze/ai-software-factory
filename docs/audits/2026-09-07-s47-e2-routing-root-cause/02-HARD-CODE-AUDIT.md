# 02 — HARD-CODE AUDIT (代码取证)

| 位置 | 内容 | 判定 |
|---|---|---|
| agent_loop CORE_TOOL_IDS | [project_status, project_scan, code_scan, bash_exec, web_search] | 常驻工具面=项目诊断 (倾斜, 非强制) |
| agent_loop _PROPOSAL_PATTERN | (需要吗…吗[?？]?)$ | 状态检测正则 (过窄) |
| agent_loop _CONFIRM/_REJECT_WORDS | 需要/好/… 不用/… | 降级词表 (仅 LLM 不可用) |
| query_engine _INTENT_RULES | 关键词→intent | 软参考 (非强制路由) |
| query_engine _INTENT_LLM_PROMPT | intent JSON 规则 | prompt 层分类 |
| AfConversationCenter taskStatsText | project_tasks → 固定模板覆盖整轮 | **真硬编码 UI 渲染规则** |
| intent_core route_for | intent→路由提示 | 软参考 |

无: forced tool / tool_choice / if message→tool 业务路由 / UNKNOWN→诊断 fallback
无: conversation_os 或 session 双写业务 truth 冲突 (聊天主链=single)

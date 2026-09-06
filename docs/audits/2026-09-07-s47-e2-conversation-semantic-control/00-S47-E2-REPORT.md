# 00 — S47-E2 Conversation Semantic Control Plane (2026-09-07)

## Before (Root cause, audit 见 s47-e2-routing-root-cause/)
自然语言被项目工具劫持: proposal 检测正则过窄 + CORE 工具面=项目诊断 +
S35 前端模板整轮覆盖 + 无 recovery 语义 + Conversation State=NO。

## Architecture change
- Semantic Governor: LLM 每轮判定 relation/domain/needs_tool/topic
  (零关键词行为; 词表不再决定行为)
- Governor guide 注入: recovery(禁诊断自证)/confirm 执行提议/保持主题/
  域工具提示/opinion 无工具/工具克制
- Conversation State: conv_state.json (topic/domain/relation/pending)
- 前端 S35 → 辅助卡片

## Implementation
agent_loop: _GOVERN_PROMPT/_govern_turn/_conv_state_load/save/
_governance_guide; run_agent_native 接线 (governor 为主, E1/E2 词表
guide 降级)
frontend: AfConversationCenter taskStatsText → supporting card

## Tests
10 governor + E1/E2 42 = 52; 回归 141 backend + frontend 560/561

## Real E2E (真实 LLM, P-b0adfaa6)
接受建议→confirm+执行 pending 提议; 继续分析需求→continue 保持主题;
你什么情况→complaint recovery 禁诊断工具; 任务数→question/task;
观点→opinion needs_tool=false

## Remaining risks
- governor 每轮 +1 次 LLM 调用 (成本/延迟)
- CORE_TOOL_IDS 仍项目诊断倾斜 (governor 引导对冲; 全平衡留后续)
- pending 提议仍需 LLM 从文本识别 (无独立 proposal store)

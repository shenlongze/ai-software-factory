# 00 — S47-E1 Conversation Continuity & Semantic Routing (2026-09-07)

## 1. Executive Summary
修复两连环问题: ① 需求/PRD 状态问题路由到任务统计 (第一 commit 42c593e1);
② AI 提议 → 用户"需要" 被 LLM 判"消息不完整" (本 commit 45b5f118)。
两修复均通用语义机制, 零场景硬编码。

## 2. Original Failure
- "需求分析完了吗" → project_tasks → "当前项目共有 20 个任务"
- Assistant 提议 → "需要" → "你的消息似乎不完整，只发来了需要两个字"

## 3. Root Cause
- ① conversation 工具层无产品链查询域; intent 无 product-lifecycle 语义
  (已修: + product_lifecycle intent 域 + project_lifecycle 工具 — 42c593e1)
- ② 上一轮 assistant 提议虽进扁平历史 (4 轮), 但无 continuation 语义引导;
  LLM 对短确认单字无"待回应提议"结构 → 自行判"不完整"

## 4. Conversation Context Reality
- SSOT: session store (sessions_store.list_messages) → run_agent_native
  history → _history_text 注入 "【最近对话】" (最近 4 轮 user/AI 300 截断)
- WebUI 真实聊天 = session (api_session_send → run_agent_native)
- 另有 conversation_os (/api/conversations, 模板状态机) 服务会话实体列表 —
  用户聊天主链在 session, 无冲突

## 5. Intent Resolution Reality
query_engine/intent_core: deterministic + LLM 软参考; run_agent_native 模型自主

## 6. Domain Routing Reality
product_lifecycle (需求/PRD/拆解) vs project_status/tasks (进度/统计) 已分

## 7. Tool Selection Reality
tool_schemas 全量给 LLM FC; project_lifecycle 已暴露 (42c593e1)

## 8. Product Truth Reality
canonical P1 真实 store 空 (诚实); org req_33846c95b001 VALIDATED + plan
plan_d92f9c23070a planning (P-b0adfaa6)

## 9. Implementation (本 commit)
- _continuation_guide: 通用 continuation 引导 — (短确认/否定 语言层词表)
  + (上轮 assistant 末尾提议问句正则) → 注入 system 引导 确认执行/拒绝/
  按新指示; 严禁"消息不完整"
- run_agent_native: hist_block 后注入

## 10. Tests
8 (continuation: 需要/好/不需要/无历史/无提议/首轮/长消息不误触发 +
routing 回归); 回归 90 passed 0 failed

## 11. Real E2E (真实 LLM, P-b0adfaa6)
"需要" → 回答开始执行提议 ("让我读取 req…/plan 素材作为 PRD"), 无"不完整"

## 12. Regression
S45/S44/session_webui/s10_114/s10_117/P1 全过; 90 passed 0 failed

## 13. Hard-code Audit
无 if message=="需要"; 无 per-scenario 分支; 词表为语言层通用确认语义;
泛化到任意 AI 提议 → 短确认

## 14. Git Commit
45b5f118 fix(session): conversation continuation for short confirmations
(+ 42c593e1 routing fix, 前序报告目录见 s47-e1-conversation-intent)
NO PUSH

## 15. Remaining Risks
- 提议问句正则 (结尾 吗/需要吗 等) 是近似 — 复杂提议句尾变化多, 靠引导
  文本让 LLM 兜底
- run_agent (兼容包装) 回答含 <tool_calls> 文本残留 (v1 协议); run_agent_native
  有清洗 — WebUI 已走 native
- conversation_os vs session 双入口仍有概念重叠 (P3 治理项)

## 16. ACCEPT
核心问题回答:
- 为何查任务? → 无产品链工具+intent 域 (已修: product_lifecycle)
- 为何丢上下文? → 扁平历史无 continuation 语义 (已修: 通用引导)
- 是否泛化? → 是 (语言层确认语义 + 提议句检测, 非修单例)

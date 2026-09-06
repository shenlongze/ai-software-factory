# 00 — S47-E2 AUDIT (2026-09-07, READ-ONLY)

## Current Architecture (代码取证)
- 聊天入口: WebUI → POST /api/sessions/{id}/messages?stream=1 →
  api_session_send → run_agent_native (agent_loop) — 主链
- 历史: sessions_store.list_messages → _history_text 最近4轮 →
  system【最近对话】; 另 _last_assistant_text 用于 challenge
- E1 continuation: _continuation_guide — (短确认词表 _CONFIRM_WORDS/
  _REJECT_WORDS) + (上轮 assistant 提议问句正则 _PROPOSAL_PATTERN) →
  注入 system 引导。**本质仍 keyword→behavior (任务书批评点)**
- 语义分类基础设施: query_engine.parse_intent_llm (LLM JSON intent),
  intent_core understand_intent — 已有 LLM 结构化语义判定模式可复用
- 产品链 truth: product_lifecycle intent + project_lifecycle 工具 (E1)
- 污染风险: 错误 assistant 回复进入历史 → 后续 _last_assistant 被污染
  (E1 实测 — 困惑回复破坏后续轮恢复)

## Root Cause (本任务)
1. continuation 判定 = 词表+正则 (需要/好 → confirm) — 非语义;
   "可以，不过先把登录需求补完整" / "那刚才那个方案呢" / "我想改目标"
   无法被词表表达 → 语义缺口
2. pending proposal 无结构化状态 — 每轮从自然语言历史重猜 (脆弱)
3. 无 constraint/modification/reference 语义提取

## STOP Check
- 无 P0 truth violation; 无 Core contract 冲突; 不动 Production Truth;
  不需大规模重构 (在 E1 guide 处升级为 LLM 语义分类, 保留降级)
- 不新造 ContextRuntime (复用 run_agent_native 注入点 + 已有 LLM 通道)
→ GO (最小架构对齐修复)

## Semantic Model (目标)
Turn relation 语义类别 (LLM 判定, 非词表):
- confirm (确认执行提议) / confirm_modify (确认+约束) / decline (拒绝)
  / reference (指代上轮内容) / redirect (改变方向) / ambiguous (需澄清)
关系作用于: pending proposal (上轮 assistant 提议) → 注入对应引导

## Fix Design (最小)
1. _classify_turn_relation(message, last_assistant, llm_fn) →
   LLM JSON {relation, summary} (复用 llm 通道; 失败/低置信 → 降级现词表)
2. run_agent_native: 上轮有提议候选时 (现正则仅作候选检测) 调分类 →
   注入 relation 引导 (confirm+约束/decline/redirect 等语义, 零词表)

# 01 — Conversation Architecture (修复后)
WebUI → api_session_send → run_agent_native:
  history 注入 → Governor (LLM 语义) → guide 注入 → state 更新 →
  LLM FC 工具 → answer → (前端 AI 文本为主 + tool 卡片)
Tool 决策权: LLM (FC) + governor 语义护栏 (域引导/recovery/克制)

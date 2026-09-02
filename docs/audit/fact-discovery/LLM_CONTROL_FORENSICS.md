# LLM CONTROL FORENSICS — STEP 4 (2026-09-02)

| Component | CODE | CALLABLE | INTEGRATED | RUNTIME | PROD | PERSISTED |
|-----------|------|----------|-----------|---------|------|-----------|
| llm_raw (统一入口) | console_sessions.py:104 | YES | YES | YES | YES | usage.json |
| _default_llm_fn | console_sessions.py:110 | YES | YES | YES | YES | — |
| LLMRouter | llm_router.py:107 | YES | NO (消费 0) | NO | NO | — |
| llm_gateway (provider 适配) | llm_gateway.py | YES | UNKNOWN | UNKNOWN | UNKNOWN | — |
| factory-core providers | core | YES | NO (console→core 0) | NO | NO | — |
| usage 记录 | providers/usage.json | — | — | YES | YES | YES (records) |

## 事实

- 模型/provider 实际选择: provider._default_llm_fn (读取 providers.json 配置, deepseek)
- LLMRouter 分层 (user/project/agent/fallback) = L1 REGISTERED, 无 L3+ 证据
- usage.json 有真实记录 (hermes 300s timeout failed, 2026-08-06)
- LLM Control Plane = PARTIAL (llm_fn 注入统一 + provider 配置真实; 分层 Router 未接入)

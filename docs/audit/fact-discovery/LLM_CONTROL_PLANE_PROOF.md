# LLM CONTROL PLANE PROOF — STEP 3 (2026-09-02)

## 真实配置 (providers.json, ~/.factory)

```
providers: { deepseek: { enabled: true, models: [deepseek-chat, deepseek-reasoner],
  base_url: https://api.deepseek.com/v1/chat/completions,
  api_key_ref: env:DEEPSEEK_API_KEY } }
```

## 选择路径 (代码证据)

```
User message
→ console_sessions.py:104 llm_raw(prompt)   [统一入口]
→ console_sessions.py:110 provider._default_llm_fn()  [装配链]
→ provider (ReasoningProvider?) 
→ providers.json 配置 (deepseek)
→ LLM 调用
```

## 各组件状态

| 组件 | 代码 | 生产消费 | 状态 |
|------|------|---------|------|
| llm_raw | console_sessions.py:104 | 全部模块 (llm_fn 注入) | PRODUCTION_USED |
| _default_llm_fn | console_sessions.py:110 | llm_raw | PRODUCTION_USED |
| LLMRouter (route 分层) | llm_router.py:107 | **0** | CONFIRMED_NO_PRODUCTION_CONSUMER |
| llm_gateway (anthropic/gemini/openai complete) | llm_gateway.py | UNKNOWN | UNKNOWN |
| factory-core providers (registry/selector) | core | 0 (console→core=0) | CONFIRMED_NO_PRODUCTION_CONSUMER (console 侧) |
| providers/usage.json | providers/usage.py? | 记录存在 | RUNTIME_PROVEN (1+ records) |

## 模型选择事实

- User explicit model override: LLMRouter._layer_user_explicit 定义 (代码), 生产消费 0
- Project rule: LLMRouter._layer_project_rule 定义, 消费 0
- fallback: LLMRouter._layer_fallback 定义, 消费 0
- 实际选择: provider._default_llm_fn (读取 providers.json)
- audit: usage.json 记录 (token/cost/latency/success)

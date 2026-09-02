# LLM CONTROL PLANE REALITY — STEP 7

| 组件 | M | 证据 |
|------|---|------|
| LLM Invocation | M4 | llm_fn 全链路 (console_sessions.py:104) |
| LLM Provider 配置 | M3 | providers.json deepseek |
| Model Catalog | M2 | providers.json models 列表 (无独立 catalog 实体) |
| Model Selection | M1 | LLMRouter 消费 0; 固定默认 |
| Provider Selection | M1 | 固定 _default_llm_fn |
| Routing (分层) | M1 | LLMRouter 定义, 无生产消费 |
| Fallback | M0 | 无生产 fallback 证据 |
| Cost | M1 | budget.py (exec), providers costs; 生产使用 UNKNOWN |
| Observability | M3 | usage.json records (latency/cost/success) |

## 事实
- 系统有"LLM 调用控制" (M4: llm_fn 注入统一)
- 系统**没有**"模型选择控制面" (M1: 无动态路由生产消费)
- 产品承诺 P-LLM-01 (弱模型规划强模型执行) → G-LLM-01 TRUE_GAP

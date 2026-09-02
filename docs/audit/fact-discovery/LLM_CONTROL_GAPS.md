# LLM CONTROL GAPS — STEP 5
| 层 | 状态 | 证据 |
|----|------|------|
| Provider Registry | PARTIAL (providers.json deepseek; core registry 孤立) | providers.json |
| Model Catalog | PARTIAL (providers.json models) | providers.json |
| Model Selection | ABSENT (LLMRouter 消费 0) | llm_router.py:107 |
| Provider Selection | ABSENT (固定 _default_llm_fn) | console_sessions.py:110 |
| Injection | PROVEN (llm_fn 全注入) | console_sessions.py:104 |
| Actual Provider | PROVEN (deepseek) | providers.json |
| Fallback | ABSENT (无生产 fallback 证据) | — |
| Audit | PARTIAL (usage.json 记录) | usage.json |
- G-LLM-01 HIGH: 无动态模型选择层 (用户/项目/任务级模型规则未接入生产)
- 分类: CONTROL_PLANE_GAP

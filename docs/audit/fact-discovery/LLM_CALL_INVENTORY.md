# LLM CALL INVENTORY — STEP 2 (2026-09-02)

## 修正结论 (F-4)

STEP 1 声称 "154/175 直接调用绕过 Router" — **方法缺陷**。
实际事实:

1. **llm_raw 是统一 LLM 入口**: console_sessions.py:104 `def llm_raw(prompt)` → 
   provider._default_llm_fn() 装配 (console_sessions.py:110)
2. **llm_fn 依赖注入**: 模块 (decomposer/discovery/product_intelligence/reasoning/agent_loop)
   通过 `llm_fn` 参数接收入口 — 抽样验证: decomposer 16/16, product_intelligence 11/11,
   reasoning 13/13 全部 llm_fn 注入
3. **LLMRouter (llm_router.py:107 route, 分层: user_explicit/agent_skill_policy/project_rule/
   system_recommendation/fallback) 消费方 = 0** — 定义存在, 生产无调用
4. **provider internal**: llm_gateway.py (anthropic/gemini/openai_compat complete) + 
   factory-core/providers (registry/selector) — 底层适配

## 调用分类 (修正)

| 类型 | 数量 | 说明 |
|------|------|------|
| 总命中 (llm_fn/llm_raw/chat_completion) | 175+ | 含定义/引用/测试 |
| llm_fn 注入调用 (业务模块) | ~150 | 统一入口 (llm_raw) 依赖注入 |
| llm_raw 定义 | 1 | console_sessions.py:104 |
| llm_raw 直接调用 | 2 | console_sessions.py 内部 |
| LLMRouter 消费 | 0 | 生产未使用 |
| provider internal | llm_gateway + core/providers | 底层适配 |

## 事实

- 业务代码通过 llm_fn 注入 (统一), 非散落裸调用
- LLMRouter (分层模型选择) 定义了但生产消费 = 0 (UNKNOWN 是否死代码)
- 模型选择实际路径: provider._default_llm_fn (console_sessions.py:110)
- factory-core/providers selector 是否被 console 用: 0 (console→core=0)

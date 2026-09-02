# 09 — MODEL SELECTION CONTRACT (STEP 10, 2026-09-02)

## 冻结语义 (D-8)
```
Task / Agent ──► Model Policy ──► Model Selection
```
- Model Selection 必须进入治理链 (audit + policy)
- 概念分离 (禁止合并):
  LLM Invocation (M4 真实) ≠ Provider (M3) ≠ Model ≠ Model Selection (M1) ≠ Routing (M1) ≠ Fallback (M0)
- "可以调用 DeepSeek" ≠ "Model Selection Control Plane 已完成"

## 已知事实 (不修)
- LLMRouter production consumer = 0 (llm_router.py:107 定义, 消费 0)
- 实际模型选择: provider._default_llm_fn (console_sessions.py:110, 固定默认)
- Status: 调用域 CURRENT M4; 选择域 CONTRACT-ONLY (实施留 Fix Sprint)

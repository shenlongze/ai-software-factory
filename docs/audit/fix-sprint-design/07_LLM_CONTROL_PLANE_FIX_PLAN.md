# 07 — LLM CONTROL PLANE FIX PLAN (STEP11)

## 概念分离 (不得合并)
LLM Invocation (M4) ≠ Provider Config (M3) ≠ Model Catalog (M2) ≠
Model Selection (M1) ≠ Routing (M1) ≠ Fallback (M0)

## 目标契约 (D-8)
```
Task/Agent → Model Policy → Model Selection → Provider/Model (治理链)
```

## 缺口
- LLMRouter (llm_router.py:107) 定义完整 (user/project/agent/fallback 分层) 但生产消费 0
- 实际选择: provider._default_llm_fn (console_sessions.py:110) 固定默认
- 无 Model Policy SSOT / 无 selection audit

## Fix 边界 (FX-05, 设计级)
1. 冻结 Model Policy SSOT 位置 (契约) — 输入: Task capability / Agent 角色; 输出: model choice
2. llm_fn 装配点接入 Policy → LLMRouter (替换固定默认的决策点)
3. Selection 决策进 audit (usage/events)
不做: fallback 完整实现 (M0, 后置) / provider 增加 (无需求证据)

## 验收
- 某 Task 类型 → policy 决定的 model ≠ 固定默认 (有决策证据)
- selection 事件进 audit
- LLMRouter 有生产消费者 (非 0)

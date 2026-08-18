# S10-082 — Conversational Intelligence & Product Manager Experience

> 日期: 2026-08-18 | 从 AI Shell → AI Product Manager | v1.1.1

---

## 1. Reality Audit

```
根因 1: 39 个 intent (audit_*/memory_*/debug_*/product_*) 有规则+action 但 DEFAULT_ROUTES 无映射
       → "我正在学习 AI Agent"(memory_learn) → UnknownIntentError
根因 2: memory_learn 规则含裸"学习" → 闲聊误判为 Factory 操作
根因 3: 命名仅关键词提取 (单候选); Discovery 问题生硬 ("这个产品解决什么问题?")
```

## 2. Root Cause

| 现象 | 根因 | 修复 |
|---|---|---|
| 学习 AI Agent → 未配置路由 | 路由表缺 39 映射 | 同名 action 兜底 + Chat 降级 |
| 裸"学习"→ memory_learn | 规则过宽 | 规则精化 (学习经验/触发学习) |
| 命名单候选 | 仅关键词提取 | 多候选 (LLM/deterministic) |
| Discovery 生硬 | 文案表单化 | 对话化引导 (字段语义不变) |

## 3. Architecture Change

```
Unknown Intent:
  修复前: Intent → 无 route → UnknownIntentError (用户可见)
  修复后: Intent → Factory Route? (含同名 action 兜底) → 执行
          └ 无 → ChatService (安全降级, 用户永不见内部错误)

Persona: Chat prompt → AI 产品经理和技术负责人
```

## 4. Modified Files

- router.py: 同名 action 兜底 (39 intent 自动可路由)
- session.py: UnknownIntentError → Chat 降级 (logger.debug 记录)
- intent.py: memory_learn 规则精化
- naming.py: suggest_names 多候选
- conversation.py: 候选列表展示 + 选择提示
- product.py: FIELD_QUESTIONS 对话化
- chat.py: AI PM persona
- version 1.1.1

## 5. Tests

```
新增 14 (test_s10_082_conversational_intelligence.py)
更新 6 旧测试 (行为变更: Chat 降级/多候选/对话化文案/版本)
console+api: 4534 passed, 0 failed
全量: 11791 passed + 1 skipped (1 runtime 冒烟 flaky — 独立重跑 8 passed)
```

## 6. CLI E2E (安装态 v1.1.1)

```
> 我正在学习 AI Agent
→ 很好！学习 AI Agent 是个非常有前瞻性的方向。作为 AI Factory 的产品经理
  和技术负责人，我可以帮你把学习路径变成一条能落地的产品线...

> 我想做一个个人密码管理 App
→ 我先帮你梳理一下。这个产品最主要想解决什么痛点?
  比如: 用户遇到什么困难? 为什么现在的方法不好?

> 密码容易忘 → 目标用户是谁? → 个人用户 → 核心功能有哪些?
→ 产品: 个人密码管理
  建议名称: 个人密码管理
    1. 个人密码管理
    2. 个人密码管理助手
    3. 个人密码管理管家
```

## 7. Remaining Issues

1. 产品流程中其他意图被吞 (Discovery 状态接管 — S10-050 既有设计, 保留)
2. LLM 命名候选在 LLM 可用时更丰富 (deterministic 已验证)
3. runtime 冒烟测试偶发 flaky (已知, 非本 Sprint 引入)

## Git

```
551b59e feat(S10-082): conversational intelligence & PM experience (16 files)
git clean ✅ | HEAD == origin/main ✅ | 已 push ✅ | v1.1.1
```

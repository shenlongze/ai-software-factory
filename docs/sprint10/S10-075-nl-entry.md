# S10-075 — Natural Language & Conversational Production Entry

> 日期: 2026-08-17 | 产品入口优化 | Command Shell → AI Shell + System Commands

---

## 1. Reality Audit

```
REPL 已有 (S10-048/050): "/" → slash registry; 产品流程多轮 (DISCOVERY);
intent 未识别 → "未知命令" (根因)。
现有 LLM 能力: ReasoningProvider._default_llm_fn (exec provider registry) — 可复用。
"未命名产品-xxx": 设计机制 (product.py 临时名, 确认前缺省, 验收 G) — 非 bug。
```

## 2. Root Cause

| 现象 | 根因 |
|---|---|
| `你好` → 未知命令 | intent_parser.parse("你好") → None → 硬编码 UNKNOWN 提示 |
| `什么是 MCP` → 未知命令 | 无普通问答路由 (conversation.py 仅产品流程) |
| `我想做 OneNote App` → 未知命令 (部分) | 主路径已可解析 (create_product); 变体输入未覆盖 |
| 多个"未命名产品" | 设计机制 (确认前临时名) — 保留 |

## 3. Architecture Changes

```
Input
 ├── "/" → System Command (slash registry, 保留)
 └── 自然语言
      ├── 产品流程中 → Conversation (多轮, 保留)
      ├── intent 命中 → IntentRouter → Action (保留)
      └── intent 未识别 → ChatService.answer (真实 LLM, 新增)
```

- 新增 session/chat.py: ChatService — 复用 ReasoningProvider LLM 装配链, 无 LLM → 诚实引导
- session.py: chat_service 注入 + 分发 (intent None → chat)

## 4. CLI Changes

- REPL 未知输入 → 真实 LLM 问答 (不再 "未知命令")
- /help 升级: 显示自然语言示例 + 系统命令

## 5. API Changes

- 无新增端点 (Conversation 是 REPL 层; API 已有 intent/chat 能力, 本 Sprint 未破坏)

## 6. Conversation Changes

- 普通问答能力 (L2): 你好/技术问答 → 真实 AI 回答 (DeepSeek 实证)

## 7. Intent Routing Changes

- "我想做X" → create_product → DISCOVERY (L3/L4, 已有, 验证保留)
- 模糊输入 → chat/引导 (F, 不再未知命令)

## 8. Discovery Changes

- 多轮状态保持 (DISCOVERY → PRODUCT_CONFIRMATION) 验证通过 (L4)

## 9. Project Lifecycle Changes

- 保留临时名机制 (验收 G, 设计兼容 — 不删历史机制)
- 确认流程 (概要 + y/N) 保留

## 10. Test Results

```
新增 17 (test_s10_075_nl_entry.py): 问答/命令/意图/多轮/模糊/生命周期
更新 5 旧测试 (新行为: 未知输入 → AI 回答)
console+api: 4465 passed, 0 failed
```

## 11. Real CLI E2E Results (安装态 ~/factory-venv)

```
> 你好 → 你好！我是你的 AI 软件开发助手，很高兴为你服务。有什么编程、项目规划或技术问题需要帮忙的吗？
> 什么是 Docker → Docker 是一个**开源的容器化平台**，它可以让开发者将应用程序及其所有依赖（代码、运行时、系统工具、库、设置等）...
> 我想做一个类似 OneNote 的 App → ConversationState.DISCOVERY (进入需求澄清)
```

## 12. Regression Results

```
console+api: 4465 passed (更新 5 旧行为断言)
全量: 等待完整结果
```

## 13. Git Commit

```
d6f4483 feat(S10-075): natural language entry — general conversation via real LLM + intent→discovery
```

## 14. Push Status

已 push origin/main

## 15. Remaining Gaps

1. Conversation 无多轮上下文 (每句独立; 产品流程除外 — L2 普通问答上下文未来增强)
2. ChatService 无 API 端点 (REPL 层; API chat 端点后续)
3. "未命名产品" 确认前临时名 (设计保留; 可增强: 确认时提示改名)

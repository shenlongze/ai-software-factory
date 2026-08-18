# S10-076 — Conversational Context & Safe Intent Routing

> 日期: 2026-08-17 | 连续对话记忆 + 安全意图路由 | AI Shell → AI Workforce OS

---

## 1. Reality Audit

```
根因 1: "刚刚创建的项目呢?" 含 "创建" → create_project 规则误命中 (name="的项目呢?")
根因 2: SessionContext.current_project 存在但 create_product/prepare_project 后从未写入
根因 3: ChatService 所有异常 → _FALLBACK ("我还不确定你的目标") — 不区分 LLM 不可用
根因 4: create_project 参数不完整 (goal=None) → 直接透传 Domain → Pydantic validation error
```

## 2. Root Cause

| 现象 | 根因 | 修复 |
|---|---|---|
| 刚刚创建的项目呢 → create_project | 规则 "创建" 宽泛 | CURRENT_PROJECT 规则前置 |
| 无当前项目上下文 | context 未写入 | create_product 成功 → context 写回 |
| Chat 失败伪装目标不明 | 异常统一 fallback | Provider 不可用 → 明确错误 |
| validation error | 参数透传 | REPL 参数完整性拦截 |

## 3. Architecture Changes

```
Input → Intent (CURRENT_PROJECT 分类) → Context Resolver (session.current_project)
      → Action Safety (参数校验) → Confirmation → Execution

Chat: Provider 不可用 ≠ 用户目标不明确 (明确区分)
```

## 4. CLI Changes

- REPL: INTENT_CURRENT_PROJECT → _show_current_project (只读, 绝不创建)
- REPL: create_project 参数不完整 → 自然语言提示 (不进入 Domain validation)
- create_product 成功 → context.current_project + last_created_project 写回

## 5. API Changes

- 无新增端点 (Conversation 为 REPL 层; 未来统一 Conversation Service)

## 6. Conversation Changes

- ChatService: Provider 不可用 → "AI 对话服务当前不可用。原因:..." (诚实)

## 7. Intent Routing Changes

- 新增 INTENT_CURRENT_PROJECT: 刚刚创建的项目/当前项目/这个项目/刚才那个项目/项目在哪里
- create_project name 清理: "创建项目" → 无实质 name; "创建项目 记账App" → "记账App"

## 8. Discovery Changes

- 无 (多轮状态保持不变, 验证通过)

## 9. Project Lifecycle Changes

- 无破坏; context 写回增强 (创建后可持续引用)

## 10. Test Results

```
新增 12 (test_s10_076_context_safety.py): Context/Intent/Safety/Chat 语义
console+api: 4477 passed, 0 failed
```

## 11. Real CLI E2E Results (安装态 ~/factory-venv 已更新)

```
> 我想做一个水利工程监控 App → Discovery 多轮 → Product Created
> 生成工程计划 → ✔ Project Ready For Engineering.
> 刚刚创建的项目呢？→ 当前项目: P-55546583 (绝不 create_project) ✅
> 继续开发 → resume_project
```

## 12. Regression Results

```
console+api: 4477 passed (新增 12, 零回归)
全量: 等待完整结果
```

## 13. Git Commit

```
bbd86a5 feat(S10-076): conversational context + safe intent routing
```

## 14. Push Status

已 push origin/main

## 15. Remaining Gaps

1. 普通问答无多轮上下文 (Conversation Context vs Factory Context 边界已定, 实现后续)
2. Conversation Service 统一 (CLI/API/Web 共享) — 未来
3. prepare_project 后 context 写回 (当前由 create_product 写; prepare 路径待接)

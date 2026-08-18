# S10-077 — Factory Query Priority Routing (生产级优化)

> 日期: 2026-08-17 | 自然语言 → Intent → Query/Action/Chat → Context → Safe Execution

---

## 1. 根因

| 现象 | 根因 |
|---|---|
| "现在有什么项目" → ChatService → LLM 失败 | list_projects 规则仅 "项目列表/有哪些项目/列出项目", "有什么项目" 未命中 |
| "最近创建了什么" → create_project | 含 "创建" 命中 create_project 规则 (误判为创建) |

## 2. 修改文件

- factory-console/session/intent.py (list_projects 关键词扩充 + recent-created → current_project)
- tests/console/test_s10_077_factory_query.py (新增 13)

## 3. 架构变化

```
Natural Language → Intent Router
   ├── Factory Query (list_projects/current_project) → Project Service (零 LLM)
   ├── Factory Action (resume/prepare) → Action + ConfirmationGate
   ├── General Chat (intent None) → ChatService → LLM
   └── Product Intent → Discovery
```

Query 与 Chat 明确分流: 确定性查询永不依赖 LLM。

## 4. 新增 Intent

无新类型 (复用 list_projects / current_project); 扩充关键词变体。

## 5. Query 路由

```
"现在有什么项目" / "有哪些项目" / "我有哪些项目" → list_projects (项目列表)
"当前项目是什么" / "刚刚创建的项目呢" / "最近创建了什么" → current_project (上下文)
```

全部走既有 action (list_projects 复用 commands.read_projects, 同一数据口径)。

## 6. Provider Failure 行为

- Factory Query: 零 LLM, Provider 缺失不影响 ✅
- General Chat: 明确 "AI 对话服务当前不可用。原因: ..." (不伪装) ✅
- 绝不猜测 Intent 执行 Action ✅

## 7. Context 行为

- create_product → context.current_project + last_created_project (S10-076 保留)
- "最近创建了什么" → last_created 查询

## 8. Safety 行为

- create_project 参数不完整 → 自然语言提示 (不进 Pydantic validation) ✅
- ConfirmationGate 保留 (prepare_project 等) ✅

## 9. 测试数量

新增 13 (test_s10_077_factory_query.py); console+api 4490 passed; 全量 11747 passed (零回归)。

## 10. 真实 CLI E2E (安装态, LLM 不可用环境)

```
> 现在有什么项目 → 项目列表 (P-1ce528fe ... ScorePocket, 博客) ✅ 零 LLM
> 当前项目是什么 → 上下文引导 (无 context) ✅ 零 LLM
> 什么是 Docker  → AI 对话服务当前不可用。原因: LLM Provider 未配置或 API Key 缺失。✅
```

## 11-13. Git

```
2508f4b feat(S10-077): factory query priority routing
git clean ✅ | HEAD == origin/main ✅ | 已 push ✅
```

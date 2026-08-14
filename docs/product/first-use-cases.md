# First Use Cases — AI Factory

> 位置: docs/product/first-use-cases.md | Sprint: S10-040 | 首批验证场景定义

---

# Scenario 1: 开发者 — "让 AI Factory 管理一个软件任务"

## User

独立开发者 / 全栈工程师。会用 CLI, 有 API key, 想验证"AI 真的能帮我改代码"。

## Problem

- 现有 AI 编码工具(Cursor/Claude Code)是"一问一答", 不可审计、不可验证
- 不知道 AI 改了什么、花了多少钱、质量如何

## Workflow

```
1. factory init --non-interactive --provider deepseek
2. export DEEPSEEK_API_KEY=...
3. factory project create --repo-path ~/my-app
4. factory run --project ~/my-app --task T-001 --agent backend-1
5. factory run-status --id <id>      # 看 patch + usage
6. factory audit                     # 看审计
```

## AI Factory Value

- **真实执行 + 审批**: AI 产出 patch, 人工批准后才应用
- **成本透明**: 每次执行 tokens/cost 可见
- **全审计**: 谁/什么/何时/哪个模型/多少钱
- **多模型**: 简单任务用便宜模型, 复杂任务用强模型

**验证目标: 开发者能否 5 分钟完成首次真实任务?**

---

# Scenario 2: 创业团队 — "多个 AI Agent 协作开发产品"

## User

2-10 人初创团队, CTO/技术负责人主导。人力有限, 希望 AI 承担重复开发。

## Problem

- 开发速度不够快, 重复工作(脚手架/CRUD/测试)占用人力
- AI 工具分散, 无法统一管理多个"AI 员工"

## Workflow

```
1. factory init + 配置多 Provider (deepseek + ollama 本地)
2. 指派 backend-1 (开发) / tester-1 (测试) 等 Agent
3. 每个任务: factory run --task <id> --agent backend-1
4. 审批门: 人工批准 AI 产出
5. factory audit: 团队可见全部 AI 活动
```

## AI Factory Value

- **组织隐喻**: Agent = 员工, 有角色/技能/权限
- **成本优化**: Router 按任务选模型(本地免费 / 云端强)
- **治理**: 审批门 + 审计, AI 可控
- **可验证**: 产出有验证门(语法/测试)

**验证目标: 团队能否用多个 Agent 角色完成一次小功能开发?**

---

# Scenario 3: 企业 AI 团队 — "统一管理多个模型和 Agent"

## User

中大型企业 AI/平台工程团队。多模型、多团队、合规要求。

## Problem

- 多个团队各自用不同 AI 工具, 无法统一治理/审计/成本
- 模型选择缺乏数据支撑, 成本失控
- 合规: "谁让 AI 做了什么" 无追溯

## Workflow

```
1. 统一 providers.json: deepseek/openai/anthropic/ollama
2. Router 五层链: 项目规则指定模型策略
3. 全事件审计: 所有 AI 活动可追溯
4. factory doctor --json: CI 健康门禁
5. (Enterprise, Future) RBAC/治理引擎
```

## AI Factory Value

- **统一入口**: 一个平台管理全部模型 + Agent
- **治理基础**: 审计/审批/权限链(Enterprise 增强)
- **成本可见**: usage 统计
- **中立**: 不绑厂商, 多 Provider 可切换

**验证目标: 企业团队能否用统一平台管理多模型 + 审计?**

---

# 场景优先级(验证顺序)

| 优先级 | 场景 | 画像 | 验证点 |
|---|---|---|---|
| 1 | Scenario 1 | 开发者 | 首次体验顺畅度(5 分钟) |
| 2 | Scenario 2 | 创业团队 | 多 Agent 协作价值 |
| 3 | Scenario 3 | 企业 | 治理/审计价值(Enterprise 前置) |

---

> Task 002 完毕 | 3 个首批场景定义 | 验证顺序: 开发者 → 创业团队 → 企业

# S10-046 Task 008 — CLI Product Roadmap

> 日期:2026-08-14 | Sprint: S10-046 CLI Design v2 | 规划, 未修改代码
> 目标: 从"传统命令工具"演进到"AI Workforce Operating System Terminal"

---

## 演进主线

```
v0.1 (现状):  Command Tool — 功能全, 概念门槛高
    ↓
v0.2:        交互会话 + Slash + 补全 — 降低门槛, 保留上下文
    ↓
v0.3:        Intent Layer + Memory + Conversation — 自然语言入口
    ↓
v1.0:        AI Workforce Operating Terminal — 组织管理 + 治理
```

## v0.2 — Interactive Session Foundation

| 项 | 内容 | 依赖 |
|---|---|---|
| Interactive Session | `factory` 无参数进入; 会话状态 (current project/agent) | Session Context (Task 005) |
| Slash Command | 17 个 / 命令 → 现有 Service | Slash 设计 (Task 003) |
| Completion | TAB 补全 (命令/项目/agent/provider/路径) | Completion (Task 006) |
| Renderer 统一 | Table/Diff/Cost/Error 渲染层 | Renderer (Task 007) |
| Progress 阶段提示 | [1/4] 执行中... | (S10-044 方案 A) |

**验收**: 普通用户 10 分钟: init → 会话 → /run 完成首个任务

## v0.3 — Intent Layer

| 项 | 内容 | 依赖 |
|---|---|---|
| Intent Parser | LLM 结构化输出 → IntentObject | Intent Layer (Task 004) |
| Policy Check | schema + 上下文 + 确认门 | 同上 |
| Memory | 会话历史/偏好 (复用 Experience) | 需 Memory 基础 |
| Conversation | 多轮对话 (澄清/追问) | 同上 |

**验收**: "帮我做一个 Todo 应用" → 安全执行

## v1.0 — AI Workforce Operating Terminal

| 项 | 内容 |
|---|---|
| 组织管理 | 多 Agent 团队/角色/权限 (Organization 域) |
| Governance | 审批流/策略/合规 (Enterprise) |
| 全会话化 | Command/Interactive/Intent 全统一 |
| 多端一致 | CLI 与 Web/UI 共享 Service Layer |

**验收**: 企业团队用 Terminal 管理 AI 员工

## 发布节奏

| 版本 | 时间(估) | 重点 |
|---|---|---|
| v0.2 | 4-6 周 | Interactive Session + Slash + 补全 |
| v0.3 | 6-8 周 | Intent Layer + Memory |
| v1.0 | 12+ 周 | Organization + Governance |

## 兼容保证

```
每版向后兼容:
  v0.1 全部命令 (factory run/project/demo...) 永不变
  新增交互模式是"加法"不是"替换"
  Service Layer 单一来源 (不产生第二套执行系统)
```

---

> Task 008 完毕 | v0.2 交互会话 → v0.3 Intent → v1.0 OS Terminal | 兼容保证

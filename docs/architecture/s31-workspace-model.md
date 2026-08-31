# S31 — Workspace Model

> 日期: 2026-08-31 | 目标架构

## 定义: Workspace 是什么

**Workspace = 当前 Conversation 上下文对应的动态工作空间。**

不是 Browser, 不是 IDE, 不是固定 Tab 集合。
由当前任务 (Conversation intent + Run 状态) 决定显示什么。

## 三类元素 (必须区分, 不能混)

| 类型 | 元素 | 说明 |
|------|------|------|
| **Workspace Tool** | Preview/Browser/Terminal/Files | 用户操作工具 |
| **Production Object** | Artifact/Run/Task/Verification/Evidence/Diff | 真实后端对象投影 |
| **Conversation Context** | 当前目标/最近决策/相关产物 | 上下文信息 |

## Workspace 状态机 (按任务)

```
任务类型        → 默认 Tab 组合
─────────────────────────────────────
prd (需求)      → Artifact + Files + Preview
coding (开发)   → Code + Files + Diff + Terminal
debug (修bug)   → Code + Diff + Evidence + Terminal
qa (验证)       → Evidence + Task + Diff
analysis (分析) → Artifact + Preview
review (评审)   → Diff + Artifact + Evidence
```

## Run 展开 (P1)

用户展开 Run 时:

```
Run R1788...
├── Agent (pm/architect/developer/tester...)
├── Task T004
├── NodeRun
├── Tool Calls
├── Artifacts
└── Verification (pytest 14 passed)
```

## 数据来源 (全部真实)

```
Workspace Tab  → API
Preview        → artifact content (web/markdown/html)
Code           → /api/artifacts/{id}/content
Files          → artifact 列表
Diff           → patch artifacts
Run            → /api/sessions/{id}/runs (S30-004)
Task           → /api/projects-os/{id}/status
Verification   → opsDrill / run verification
Evidence       → opsDrill
```

## 原则

1. Workspace 不创造事实 — 全来自 API
2. Tab 由任务驱动 — 不一次性全塞
3. 用户可手动切换 — 但默认跟随任务
4. Production Object 可点击追溯 — Artifact → Run → Task → Conversation

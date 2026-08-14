# S10-046 CLI Design v2 — 最终报告

> 日期:2026-08-14 | Sprint: S10-046 CLI Architecture Design v2 | 9 Tasks 全部完成
> 纯设计, 零代码修改, git clean

---

## 1. 完成任务

| Task | Commit | 内容 |
|---|---|---|
| 001 current audit | 6aa46c9 | 当前 CLI 架构基线(17+ 命令/2519 行/薄代理) |
| 002 cli vs terminal | e388138 | 一 CLI 两模式, 共享 Service Layer |
| 003 slash command | 0552c74 | 17 个 / 命令 → 现有 Service |
| 004 intent layer | 6a55432 | 自然语言 → IntentObject → Policy → Service |
| 005 session context | fdb0dc3 | Terminal Session vs Runtime Session |
| 006 completion | 31e317f | TAB 补全(4 数据源) |
| 007 renderer | cd04dff | 6 渲染类型 + --json |
| 008 cli roadmap | 5b5857d | v0.2/v0.3/v1.0 演进 |
| 009 final review | 本 commit | 本报告 |

## 2. 必答问题

### Q1: AI Factory CLI 最终形态是什么?

**AI Workforce Operating System Terminal** — 不是传统命令工具。
一个 CLI, 两种模式:
- Command Mode(factory xxx)— 脚本/CI/明确操作
- Interactive Session(factory)— 会话/探索/自然语言

统一架构:
```
factory
 ├── Command Mode (现有 17+ 命令, 保留)
 └── Interactive Session
      ├── Slash Command (/run → 同一 Service)
      ├── Intent Layer (自然语言 → IntentObject)
      └── Session Context (current project/agent)
          ↓
      Same Service Layer (exec/org/ControlPlane)
```

### Q2: 为什么不是普通 CLI?

| 普通 CLI | AI Factory CLI |
|---|---|
| 用户记命令 | 用户描述目标 |
| 无上下文 | 会话记住 current project/agent |
| 概念暴露 (task/provider) | 概念封装 (Intent) |
| 结果平铺 | 渲染 (diff/cost/progress) |
| 单次执行 | 组织管理 (AI Workforce) |

**本质: 管理 AI 员工的组织层需要"会话"而非"命令堆"。**

### Q3: 如何让普通用户 10 分钟上手?

```
0-3 min   安装 + init + key
3-5 min   factory (进入会话) → 看到 current 状态
5-8 min   "给 main.py 加测试" (Intent) → 确认 → 执行 → 看 diff
8-10 min  /cost 看花了多少 → /exit
```
- 自然语言入口(Intent)消除概念门槛
- Slash 提供快捷
- 补全降低输入负担
- diff/cost 渲染给出价值反馈

### Q4: 如何满足高级开发者?

- Command Mode 完整保留(脚本/CI/可编程)
- --json 机器可读
- 显式参数优先(高级控制: --provider/--agent)
- Router/策略直接管理(/router)
- 会话上下文可覆盖(不强制)

### Q5: CLI 和未来 UI/Web 的关系?

```
CLI (交互/命令)  ──┐
                   ├── Same Service Layer → 未来 Web/UI
Web/UI (观察/审批) ─┘

原则:
- Service Layer 单一来源 (CLI/UI 共享)
- CLI 优先 (完整能力); UI 为补充 (观察/审批/可视化)
- 不复制逻辑: Web 调同一 Service Layer
```

### Q6: 为什么 CLI 应该优先于 UI?

| 理由 | 说明 |
|---|---|
| 完整能力 | CLI 覆盖全部操作; UI 初期只能观察 |
| 可脚本化 | CI/自动化/SSH 场景只有 CLI |
| 低开发成本 | CLI 增量演进; UI 大规模开发 (Sprint 禁止) |
| 开发者核心用户 | 目标用户(Developer/Startup)习惯终端 |
| 快速验证 | 种子用户用 CLI 即可验证价值 |

**CLI 是"能力层", UI 是"展示层" — 能力先于展示。**

## 3. 核心架构原则(全 Sprint 贯穿)

```
1. 一个 CLI, 两种模式 — 不开发新 Terminal App
2. 共享 Service Layer — 禁止第二套执行系统
3. Slash/Intent 只是入口 — 业务逻辑全在 Service
4. 向后兼容 — v0.1 命令永不变
5. 不碰核心 — ExecutionLoop/Router/AgentRuntime/Provider 零改动
```

## 4. 交付文件(9 份设计文档)

```
docs/sprint10/S10-046-cli-current-audit.md
docs/sprint10/S10-046-cli-terminal-architecture.md
docs/sprint10/S10-046-slash-command-design.md
docs/sprint10/S10-046-intent-layer-design.md
docs/sprint10/S10-046-session-context-design.md
docs/sprint10/S10-046-completion-design.md
docs/sprint10/S10-046-renderer-design.md
docs/sprint10/S10-046-cli-roadmap.md
docs/sprint10/S10-046-cli-final-report.md
```

> 注: S10-046-final-report.md(Public Release 版, da5c3f1)保持独立 — 两 Sprint 同号, 报告分文件。

## 5. 结论

**AI Factory CLI 未来形态 = AI Workforce Operating System Terminal: 一个 CLI, 两种模式, 共享 Service Layer, 从"命令工具"演进为"AI 员工管理终端"。**

- 现状: 功能全但概念门槛高
- 目标: 普通用户 10 分钟上手, 高级开发者完整控制
- 路径: v0.2 会话+Slash+补全 → v0.3 Intent+Memory → v1.0 OS Terminal
- 原则: 不碰核心, 不建第二套执行系统, 向后兼容

**等待下一阶段(实现 Sprint)指令。**

---

> S10-046 CLI Design v2 完毕 | 9 Tasks | 9 份设计文档 | 零代码修改 | git clean

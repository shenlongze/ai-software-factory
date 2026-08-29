# AI Factory — Zero-to-Current Full Reality Audit

> 审计时间: 2026-08-29 | HEAD: 2b5eafba (v1.1.306) | 审计方式: Inspect/Run/Observe/Measure/Compare/Report (零代码修改)

---

## 1. Executive Summary

**基于当前代码与运行态,AI Factory 实际是: 一个"以事件为事实源 + 外部 AI 执行器委派 + 会话式管理"的 AI 劳动力编排框架——规划/文档/审查/委派真实可用,但"从想法到可运行代码"的生产闭环尚未闭合(代码生成真实发生,却从未落到任何可运行的工作区)。**

一句话: **它是"AI 员工管理系统",还不是"AI 软件工厂"。**

---

## 2. Original Vision

- 原始愿景(design-principles.md v2.0): **Event is source of truth** — append-only 事件流,状态是投影,CLI 一切行为产生事件
- 产品愿景演化: AI Software Factory → AI Workforce → AI Enterprise Operating System
- 核心理念: Idea → Brainstorm → PRD → Task Tree → Execute → Verify → Learn;每个 Node 应是独立完整可验证的 Agent Loop

## 3. Current Reality

- 1208 commits / 24 天 (2026-08-05 → 08-29) / v1.1.306
- 代码: factory-console 90K 行 + factory-core 33.8K + 前端 35K + 测试 159K (534 文件)
- 运行态: CLI 40+ 命令真实可用;WebUI 前端 bundle 可加载 + API 真实返回;服务可启停
- 12 个项目(8 个任务:0/产出物 v0);94 条执行记录(external_ai.invoke 委派审查器真实发生)
- **workspace/projects 代码文件总数 = 0**(补丁生成了,从未应用到工作区)

## 4. Strategic Drift

**判定: 明显跑偏 (从"软件工厂"到"AI 员工运营")**

| 维度 | 原始 | 现在 |
|------|------|------|
| 核心 | 事件溯源软件工厂 | AI Workforce OS (管理 AI 员工) |
| 交付物 | 可运行软件 | patch + 审查报告 |
| 主入口 | CLI 执行链 | 会话 (WebUI) |
| 验证 | L4 Change Validation | 外部审查器 (claude.*) |

- 何时开始: v1.1.200+ (8/26 起) 会话系统爆发式增长,AgentLoop v1→v2→v3,重心从"执行链"转向"会话体验"
- 未推送: 本地领先远程 194 提交

## 5. Architecture Reality

```
factory-core (33.8K)   — 事件/验证/审计原语 (REAL)
factory-console (90K)  — service(4911行) + cli(4896行) + session/* (51K)
factory-org (18文件)   — 组织模型 (REAL 但小)
external_executor      — 外部 AI 委派网关 (REAL, subprocess 调 codex/claude/hermes)
web (前端 35K)         — React + TS, API 同源
```

## 6. Codebase Audit

| 模块 | 标记 | 证据 |
|------|------|------|
| service.py (4911行) | PARTIAL-God | CLI 12处/API 43处引用, 165方法, 职责过重 |
| cli_factory.py (4896行) | PARTIAL-God | 40+ 命令, 含 6 个自述"骨架/只读" |
| session/orchestrator.py (4133行) | **DEAD** | agent_loop 零引用, 被 v3 替换 |
| session/actions.py (4121行) | **DEAD** | agent_loop 零引用 |
| session/conversation.py (1668) / discovery.py (1285) / product_intelligence.py (1264) / replanning.py (1005) / decomposer.py (816) | **DEAD/UNUSED** | 主循环零引用 (合计 ~14K 死代码) |
| session/agent_loop.py (1823行) | REAL | v3 主循环, WebUI 流式/同步均走此 |
| session/session_hooks.py | REAL | 5 生命周期 hooks 全注册 |
| memory_core.py (125行) | REAL | Letta 风格 self-editing |

**Architecture Drift: AgentLoop v1 (意图硬路由) → v2 (原生FC+审批) → v3 (agentic 自主循环) — v1/v2 的 orchestrator/actions 成为死代码但未删除 (~14K 行)。**

## 7. Agent Audit

**判定: 单 LLM 主循环 + 外部进程委派,非"多 Agent 实体"**

| Agent | 真实? | 证据 |
|-------|-------|------|
| 本机会话 Agent (run_agent_native) | **REAL** | 单 LLM 自主循环, 28 工具, 动态工具面 |
| local-codex/claude/hermes | **REAL** | subprocess 真调二进制 (executor.py: subprocess.run) |
| codex.*/claude.* 20+ 角色 (architecture-examiner 等) | **REAL-PARTIAL** | 外部委派真实发生 (94 记录), 但只是"换 prompt 调外部 CLI" |
| PM/Market/UX/Architect 角色 | **PARTIAL** | 是 skill/prompt 装配, 非独立 agent 实体 |

## 8. Multi-Agent Audit

**判定: PARTIAL — 外部执行器是真正的多进程委派,但内部"多 Agent"是单 LLM 换 prompt。**

- 真多进程: executor.py subprocess → codex/claude/hermes (外部二进制, 真工具)
- 非真 Agent 实体: 无独立上下文/生命周期/消息传递的 AgentEntity;agent 注册表只是 JSON 元数据
- 委派链路: external_ai.invoke 事件 85+ 次 (org.execution.started 86 → completed 75, 11 次未完成)

## 9. Business Workflow Audit (Idea → Software)

```
Idea → 会话 (WebUI) → Product Definition (product.json) → PRD (真实) 
→ Engineering (engineering.json) → Task Tree (tasks.json) 
→ Execution (patch 生成, 真实但模板化) → ⛔ 代码从未应用到工作区 → Verification (语法检查) 
→ ⛔ 无 Release/Operation
```

**断裂点: Execution → Code 之间。patch 生成后停在"待批准"状态 (report 明示 "human review required before apply"), 项目工作区零代码。**

## 10. CLI Audit

| 命令 | 状态 | 真实执行 |
|------|------|---------|
| doctor | REAL | 3 PASS/2 WARN 真实诊断 |
| status / start / stop | REAL | 真实管理进程 |
| router / config / tools | REAL | 真实读配置 (router L4 缺失, model 名不一致) |
| agent / skill | REAL-WRITE | 支持 add/remove (help 文案过时称只读) |
| task / rag / audit | PARTIAL | 自述"骨架, 只读" |
| demo run | REAL | E2E 成功但模板化 (2秒, 1152 tokens, structured operations) |

## 11. API Audit

**CLI 与 API 共享 service 层 (CLI 12处 + API 43处引用) — 同源成立, 无重复实现。**

- openapi: 124 路径, 200 (T17 已修)
- /api/projects (12) /sessions (33) /audit /monitor /approvals 全真实返回

## 12. Web UI Audit

- 前端 bundle 可加载 (347KB), CSS 正常, index.html 标准
- API 数据全真实 (dashboard/projects/sessions/audit/monitor)
- 浏览器交互审计受阻: browser daemon 超时 (环境问题, 非产品), 但 HTML/JS/API 层证据完整
- 页面代码: 173 个 ts/tsx 文件, 34.9K 行, 会话/审计/监控页均有真实组件

## 13. Real E2E Audit

**`factory demo run '给 main.py 加 add 函数'` 实测:**
- ✅ workspace 创建 → 项目目录 → 执行 → patch → test → report 全链跑通 (2 秒)
- ✅ patch 含真实代码 (add 函数 + test_main.py + 语法验证 PASS)
- ⚠️ patch 是 "2 structured operations" (模板化), 非 LLM 自由生成
- ⚠️ report 明示 "human review required before apply" — 代码不自动落地
- ⚠️ 临时目录被清理, 代码未保留
- **结论: E2E 链路真实但"演示级", 非生产级代码交付**

## 14. Production Truth Matrix

| Claim | Reality | Evidence | Gap |
|-------|---------|----------|-----|
| Real Execution | PARTIAL | 94 记录 + 75 patches 真实 | 补丁不应用, workspace 0 代码 |
| Real Agent | PARTIAL | 单 LLM 循环真实 | 无多 Agent 实体 |
| Real Tool Calling | YES | 28 工具 + 动态工具面 | 会话工具真实 |
| Real Code Generation | YES | 46/75 patches 含代码 (97行 Python 等) | 从不落地 |
| Real Patch Delivery | PARTIAL | patch 生成 | 停在待批准, 不应用 |
| Real Testing | PARTIAL | 614 passed | 38% mock, 真实 LLM 测试=0 |
| Real Multi-Agent | PARTIAL | external subprocess 真实 | 内部非多 Agent |
| Real Web UI / API / CLI | YES | bundle+124 API+40命令 | — |
| Real Memory | YES | memory_core + project_memory + Spine | — |
| Real Learning | PARTIAL | feedback.learned 事件 85 次 | 事件记录, 无闭环学习 |

## 15. Testing Audit

- 534 测试文件, 202 用 mock (38%)
- 核心层 614 passed (workspace/events/metrics/cli/llm)
- tests/console: 5721 passed + 12 过时断言失败 (锁 1.1.206/锁动态工具面)
- 前端: 711/749 (38 既有失败, 项目入口类)
- **真实 LLM 调用测试: 0** (test_real_execution_binding.py 自述 "不调真实 API")
- s9_pilot sandbox: 有真实执行痕迹 (DevToolBox 代码) — 但那是历史产物, 非测试

## 16. Observability Audit

- events 表 4831+ 行, console.viewed 3952 次 (读操作也记录 — 符合原愿景)
- 审计: audit_events.json + events 双写, event_hash 防篡改
- WebUI: 审计页 + 监控页真实 (T8/T13 已交付)
- **缺口: 无请求级 tracing (Langfuse 式), 无成本/延迟面板**

## 17. Governance Audit

- PreToolUse 权限门 (DANGEROUS_TOOLS + governance_rules.json 可配置红线) — REAL
- 批准门 (APR approvals) — REAL (E2E 报告明示 human review gate)
- 权限模式 (plan/acceptEdits/auto/normal) — REAL
- **缺口: 审计有, 但无"治理策略下发/审计回查"闭环 UI**

## 18. Memory / Learning Audit

- memory_core.json (persona+human self-editing) — REAL (Letta 风格)
- project_memory (5 类 kind + 5 级 authority + 语义召回) — REAL
- ProjectSpine (handoff/resume/closure) — REAL
- **Learning: 只有事件记录 (feedback.learned 85 次), 无"从错误中改进系统"闭环**

## 19. Architecture Debt

1. **~14K 行死代码** (orchestrator/actions/conversation/discovery/product_intelligence/replanning/decomposer)
2. **God Objects**: service.py 4911 + cli_factory.py 4896
3. 双轨残留: 同步/流式两分支 (业务同源但代码分叉)
4. 版本历史: 曾 5 个版本号不一致 (v1.1.224-261 时期, 已修)
5. 前端 38 个过时测试未清 (红灯残留)

## 20. Dead / Stub / Fake / Template Inventory

| 项 | 类型 | 证据 |
|----|------|------|
| orchestrator.py 4133行 | DEAD | agent_loop 零引用 |
| actions.py 4121行 | DEAD | 同上 |
| conversation/discovery/product_intelligence/replanning/decomposer | DEAD/UNUSED | 合计 7K+ |
| agent/skill/task/router/rag/audit 6 命令 | STUB-SELF-ADMITTED | CLI help 自述"骨架, 只读" |
| demo run | TEMPLATE | "2 structured operations" 模板化 |
| test_real_execution_binding | FAKE-ADMITTED | 自述"不调真实 API" |
| models.json 缺失 | WARN | doctor 报告 |

## 21. Capability Reality Matrix (摘要)

| Capability | 接入 | 真实运行 | 状态 |
|-----------|------|---------|------|
| Agent (会话) | ✅ | ✅ | L4 Integrated |
| Multi-Agent | 外部✅ 内部❌ | 外部✅ | L3 |
| Workflow | ✅ | ✅ | L4 |
| Task Tree | ✅ | ⚠️ 生成但未执行 | L3 |
| Execution | ✅ | ⚠️ patch 不落地 | L3 |
| Verification | ✅ | ✅ 语法级 | L4 |
| Repair | ⚠️ | ❌ | L1 |
| Memory | ✅ | ✅ | L4 |
| Skills | ✅ | ✅ 147+ | L4 |
| MCP | ✅ | ⚠️ 2 server 可接入 | L3 |
| Provider | ✅ | ✅ 3 类适配器 | L5 |
| Model Router | ⚠️ | ⚠️ L4 缺失 | L3 |
| Event Sourcing | ✅ | ✅ 4831+ 事件 | L5 |
| Observability | ✅ | ⚠️ 无 tracing | L4 |
| Governance | ✅ | ✅ | L4 |
| Human Approval | ✅ | ✅ | L5 |
| Learning | ⚠️ | ❌ 闭环缺失 | L1 |
| Product Mgmt | ✅ | ⚠️ 12 项目停滞 | L3 |
| Market/Competitive | ✅ | ⚠️ 外部审查器 | L3 |
| PRD | ✅ | ✅ 真实生成 | L4 |
| UX/Arch/Eng/QA | ⚠️ | ⚠️ skill 装配 | L2-L3 |
| Release | ❌ | ❌ | L0 |
| Operation | ❌ | ❌ | L0 |

## 22. Maturity Matrix

```
Engineering Agent = L3 | Market Agent = L3 | PRD = L4 | Task Tree = L3
Execution = L3 | Verification = L4 | Repair = L1 | Multi-Agent = L3(外)/L1(内)
Learning = L1 | Web UI = L4 | Memory = L4 | Governance = L4
```

## 23. Strengths (真实证据支持)

1. **Event-sourcing 原则贯彻最彻底** (events 4831+ 行, 读操作也记事件, CLI 全部发事件)
2. **外部执行器委派真实** (subprocess 调 codex/claude/hermes, 85+ 次真实调用)
3. **CLI/API 同源** (共享 service 层, 无重复实现)
4. **会话系统深度** (28 工具/动态工具面/思考链/证据链/审计 — 已超过多数自研)
5. **治理完整** (权限门/批准门/审计链/红线可配置)
6. **记忆系统扎实** (3 层: core memory/project memory/Spine)
7. **诚实自述** (能力矩阵反虚标, 命令标注"骨架")

## 24. Weaknesses (Top 20)

| # | 弱点 | 影响 |
|---|------|------|
| 1 | **代码从不落地** (workspace 0 代码) | 致命 — 无生产交付 |
| 2 | 14K 死代码 (旧架构) | 高 — 维护负担 |
| 3 | 真实 LLM 测试 = 0 | 高 — 无法证明生产链路 |
| 4 | demo 模板化 (2秒 structured ops) | 高 — 演示≠生产 |
| 5 | Repair/Learning 闭环缺失 | 高 — 无自改进 |
| 6 | 12 项目停滞 (8 个 0 任务 0 产物) | 中高 |
| 7 | God Objects (service/cli 各 5K) | 中 |
| 8 | 前端 38 + 后端 12 过时测试红灯 | 中 |
| 9 | Router L4 缺失 + model 名不一致 | 中 |
| 10 | 194 提交未推送 | 中 (风险) |
| 11 | 双轨分支 (同步/流式) | 中 |
| 12 | 无成本/延迟可观测 | 中 |
| 13 | Release/Operation 能力 L0 | 中 |
| 14 | MCP 仅 2 可接入未深用 | 低中 |
| 15 | 6 CLI 命令自认骨架 | 低中 |
| 16 | 并发会话污染 git (3 文件被卷走) | 低 |
| 17 | 版本历史混乱 (曾 5 号不一致) | 低 (已修) |
| 18 | 无请求级 tracing | 低 |
| 19 | 外部审查器 11 次未完成 | 低 |
| 20 | Web UI 交互未完整验证 (浏览器受限) | 低 |

## 25. Competitive Comparison

**AI Factory 弱于:**
- Claude Code/Codex/Trae: 代码落地闭环、IDE 集成、真实生产使用
- OpenHands: 沙箱执行、代码应用
- LangGraph/CrewAI: 图编排、多 Agent 生态
- Hermes: 生产级 CLI、跨平台网关、插件生态
- OpenClaw: 多平台接入、工具注册表规模

**AI Factory 设计方向更有潜力:**
- Event-sourcing 作为事实源 (多数工具不做)
- 外部 AI 执行器委派 (借力 codex/claude/hermes, 不重复造 LLM)
- 会话+工具+记忆+审计一体化 (多数工具拆散)
- 治理/审批门内置 (多数工具缺)

## 26. Strategic Drift 详情

```
Original: Event-sourced Software Factory (代码交付)
    ↓ v1.1.200+ (8/26) 会话系统爆发
Current: AI Workforce OS (员工管理)
    ↓
Drift 判定: 明显跑偏 — 从"产出软件"转向"管理 AI 员工"
```

- 是否值得继续: **值得**, 但需把"代码落地"补回主链路
- 如何纠正: 见 Proposal (审计后单独输出)

## 27. Top 20 Gaps → P0/P1/P2

**P0 (致命, 先修):**
1. 补丁应用闭环 (patch → 应用到 workspace → 可运行代码)
2. 真实 LLM E2E 测试 (至少 1 条全链路真调 LLM)
3. 删 14K 死代码 (orchestrator/actions 等)
4. 项目执行推进 (12 项目从规划到代码)

**P1 (重要):**
5. Repair 闭环 (失败 → 自动修复)
6. Learning 闭环 (feedback → 系统改进)
7. 过时测试清理 (50 个)
8. Router L4 + 模型名统一
9. God Object 拆分 (service/cli)
10. 推送 194 提交
11. 成本/延迟面板
12. Release/Operation 能力

**P2 (提升):**
13. MCP 深用
14. 请求级 tracing
15. 双轨合并
16. 前端测试修复
17. 骨架命令补全
18. 浏览器 UI 完整验证
19. 并发 git 隔离
20. 多 Agent 实体化 (可选探索)

## 28. 如果只能做 5 件事

1. **补丁应用闭环** — 让代码真正落到 workspace (从 L3 → L5 的关键一跳)
2. **真实 LLM E2E 测试** — 证明生产链路 (消除"测试都是 mock"的质疑)
3. **删死代码 + God Object 拆分** — 让架构可信 (14K + 10K 减负)
4. **Repair/Learning 闭环** — 让系统自改进 (兑现"工厂"之名)
5. **推送 + 过时测试清零** — 让仓库可信 (194 提交 + 50 红灯)

## 29. Recommended Architecture Direction

```
保持: event-sourcing + 会话 + 外部委派 + 治理
加强: patch 应用流水线 (生成→评审→应用→验证→提交) — 这是工厂的核心
删除: orchestrator/actions 等 14K 死代码
合并: 同步/流式双轨 → 单一路径
新增: Repair/Retry 状态机 + Learning 反馈环
聚焦: 从"管理 AI 员工"回到"产出可运行软件"
```

## 30. Final Verdict

```
Current Product:  AI 劳动力编排框架 (会话 + 外部委派 + 事件溯源)
Current Maturity: L3 (Implemented-Integrated, 局部 L5)
Overall Score: 62/100
Is it actually an AI Software Factory? PARTIAL
Is it actually Multi-Agent? PARTIAL (外部真, 内部假)
Is it production-capable? PARTIAL (CLI/API/UI 真, 代码交付断)
Is the current architecture worth continuing? YES BUT REFACTOR
Biggest Strength:  Event-sourcing 原则贯彻 + 外部执行器委派真实
Biggest Weakness:  代码生成但从不落地 (workspace 0 代码)
Biggest Strategic Drift: 从"软件工厂(交付代码)"漂到"AI 员工运营(管理对话)"
Single Most Important Next Move: 补丁应用闭环 — 让 AI Factory 真正产出可运行代码
```

---

*本审计全程零代码修改。证据: 1208 commits / 12 项目 / 94 执行记录 / 75 patches / 614+5721 测试 / demo E2E 实测 / 40+ CLI 命令实测 / 124 API 路径。*

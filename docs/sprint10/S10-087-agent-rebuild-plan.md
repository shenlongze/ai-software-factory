# S10-087 — 回归原设计：真实 AI Agent 团队重建计划

> 日期: 2026-08-20 | 决策: B（回到最初设计——AI Factory = 一支 AI 软件公司）| 目标版本 v1.2.0
> 触发: 用户指出"现状与最初设计不一致"——多角色只是换提示词, 不是真实 Agent 团队。

---

## 1. 设计 vs 现实对账（逐条，基于真实代码审计）

| 最初设计（Operating Model） | 现状（实测） | 差距 |
|---|---|---|
| 一支 AI 软件公司：多角色真实 Agent | exec 层有**真实单 Agent 运行时**（DeveloperAgent/ExecutionLoop/Evaluator），但工厂层"角色"是**同一模型换提示词** | 大（组织层缺失） |
| 每角色有 Role/Skill/Memory/Tools/Evaluation | Skill/Capability 注册表有；Memory store 有（S10-067）；Evaluator 真实（5 层评分）；**但未接成"一个角色实体拥有这些"** | 中 |
| 想法 → … → 交付由 AI 团队运作 | 流程状态机 + 引擎调用 + 模板；角色产出互不消费 | 中大 |
| 每阶段真实资产（市场/竞品/PRD…） | 7 角色资产 = 单模型 prompt 各生成一段 + 模板兜底；PRD 是模板 | 中 |
| 记忆系统 | 有 store/检索，**agent 学习闭环未接线** | 中 |
| 评价系统 | evaluator.py 真实（validation/patch/scope/regression/requirement 5 层），**未驱动 agent 改进闭环** | 中 |
| 代码真实落地 | patch→apply→test 管线存在（S10-083），**真实质量未在用户环境验证** | 待验证 |
| 工具系统（MCP） | 框架真实（442 行），但**只有 Mock 连接（echo），不连公网** | 大 |

## 2. 重要更正（对上一轮结论的修正）

上一轮我说"只有一个 DeepSeek + 模板"**过于绝对**。审计后更正：

- **单 Agent 执行能力是真实的**：`agent_runtime.py`(607) → `developer.py`(694, DeveloperAgent 结构化输出) → `execution_loop.py`(878, **LLMPlanner 真调 provider**) → `evaluator.py`(429, 5 层评分) → `patch_filter`/`progressive`/`capability`/`experience`。
- **真正缺的是三件事**：① 工厂层的**多 Agent 协作**（角色之间真实交接/共识）；② **真实工具**（MCP 从 Mock 到真连接）；③ **记忆/学习/评价闭环**（让 agent 因经验而变强）。

所以差距本质不是"没有 AI"，而是：**现状 = 一个 LLM + 流程状态机（受控单 Agent 流水线）；目标 = N 个真实 Agent 实体 + 协作总线（AI 软件公司）。**

## 3. 重建架构

```
AgentEntity (新建):
  {id, role, provider(model), system_prompt, skills[], memory_ref,
   tools[], evaluation_ref}
  ↓
Agent Registry (工厂层) + Agent Runtime (复用 exec 全系)
  ↓
多 Agent 协作层 (新建 HandoffBus):
  PM → Market → Competitive → UX → Architect → QA → SeniorPM
  每步: 消费上一 Agent 产出 → 自己产出 → Artifact + HandoffMessage
  共识/冲突 → 决策 (复用 ReviewGate / ConflictResolver)
  ↓
工具层 (真实 MCP): git / bash / file-read / search
  ↓
记忆/学习闭环: execution experience → agent 画像 → 下次决策引用
  ↓
评价反馈: evaluator 分数 → 回写 agent 画像 → 影响后续选择
```

## 4. 工具调用与工具管理（AI Executor 层）

> 用户点: 本机装了 Hermes / OpenClaw / Codex / Claude——能否**发现、配置、并在真实流程中调用它们干活**。
> 实测（2026-08-20, 用户机器只读扫描）: codex/hermes/openclaw 在 PATH;
> ~/.codex/config.toml 已配 2 个 MCP server (node_repl/computer-use); ~/.hermes 为
> Hermes Agent v0.18 (自带 mcp/tools/sessions/model 子命令); ~/.openclaw 有完整
> agents/tools 生态; ~/.claude.json 存在 (claude 不在 PATH)。
> 现状: mcp.py 只有 MockMCPClient (echo), 无发现/无真连接/无 AI 委托 → **工具层是重建重点**。

### 4.1 发现（Discover）

```
factory tools list            # PATH 扫描 AI CLI + 配置扫描 MCP server
  1) PATH: codex / hermes / openclaw / claude → which + --version 探测
  2) 配置: ~/.codex/config.toml (mcp_servers) / ~/.claude.json (mcpServers) /
           .mcp.json (项目) / ~/.openclaw (agents/tools) / ~/.hermes (mcp/tools)
  3) 输出: 工具名 / 路径 / 版本 / 能力标签 / MCP servers / enabled
```

### 4.2 配置（Registry）

```
tools.json (workspace 级):
  executors: [{name, binary, version, invoke_mode, capability[], enabled}]
  mcp_servers: [{name, command, args, env, transport: stdio|http, enabled}]
factory tools add|remove|enable|disable|doctor   # 管理 + 健康检查
```

### 4.3 调用（Invocation — 真实流程里"让它们干活"）

```
MCP stdio 客户端 (真连接, 替换 MockMCPClient):
  → 复用 codex 配置的 node_repl / computer-use, 或任何本机 MCP server
AI CLI 委托 (子进程, AI 调 AI):
  codex exec --json "..." | hermes -z "..." | claude -p "..." | openclaw ...
  → 超时/输出解析 → 作为 tool result 回给 Agent 循环
Agent 循环内: 工具名 → ToolRegistry → 实现 (内置 file/bash/git | MCP | AI 委托)
```

### 4.4 治理（不失控）

```
权限门: 哪些 Agent 能调哪些工具 (permission, 复用 ReviewGate 语义)
预算:   每 executor 限额 (复用 budget.py)
审计:   TOOL_CALL 事件 (EVENT_TYPES 已有) + 结果/耗时/成本
沙箱:   委托命令在项目目录内运行, 超时/失败 → 明确错误回 Agent
```

### 4.5 落地优先级（并入 S10-087 阶段）

- **P0.5 发现 + 注册**: `factory tools list/doctor` + 真实 MCP stdio 连接
  （先用 codex 的 node_repl/computer-use 打通一条真实调用）
- **P1 AI 委托**: codex/hermes/openclaw/claude headless 调用接入 Agent 循环
- **P2 深度集成**: Hermes/OpenClaw 的 agents/tools/sessions 生态 (可选)

## 5. 保留 / 重写 / 新建

**保留（不推倒）**: exec agent 运行时全系、core agents/skills/registry、experience/memory store、审计、CLI/观测、artifact_registry、Discovery、S10-084 资产链骨架。
**重写**: 工厂层角色（从"引擎调用/模板"→ Agent 实体 + 真实交接）、MCP Mock → 真实连接。
**新建**: AgentEntity + 工厂层 AgentRegistry、HandoffBus、AgentTool 接入、存量仓库模式（repo mode）、记忆/评价闭环接线。

> 边界铁律: 目标是**新增 ~15-20K 行智能层**，不是重写 120K 行基础设施。

## 6. 分阶段（sprint 拆分）

### S10-087 P0 — 工厂层多 Agent 管线（本计划落地）
- AgentEntity + AgentRegistry（工厂层）
- 7 角色 → 真实 Agent 实例（复用同一 provider，各自 system_prompt/skills）
- HandoffBus：PM 产出被 Market 消费，逐级传递，产出互引（markdown 引用上一 Agent 资产）
- 验收：`我要做CRM` → 7 个 Agent 依次真实产出，且每个产出引用上一角色结论；`让PM分析` 走真 Agent 链

### S10-088 P1 — 真实工具 + 存量仓库模式
- MCP：stdio/http 真实连接（git / bash / file / search 至少 2 个）
- repo mode：读现有仓库 → 理解 → 计划 → 多文件修改 → 跑测试 → 修复（复用 ExecutionLoop）
- 验收：对任意现有仓库能完成一次真实修改 + 测试绿

### S10-089 P2 — 记忆 / 学习 / 评价闭环
- execution experience → agent 画像（成功率/成本/质量）→ 下次决策引用
- evaluator 分数回写画像并影响 Agent 选择
- 验收：第二次同类任务明确引用第一次经验（可断言）；完整 idea→delivery 真实 E2E

## 7. 验收标准（不虚，全部可断言）

1. **真实 E2E（真网络+key，用户环境）**: 一句话 → 7 角色 Agent 交接 → 深度 PRD → 工程 → 真实代码落盘 → pytest 绿
2. **多 Agent**: handoff 消息落盘可查，每个资产含 `parent_artifact` 引用
3. **工具**: 至少 2 个真实 MCP 连接在 Agent 循环中被调用
4. **记忆**: 第二次同类任务决策引用第一次经验（replay 断言）
5. **评价**: evaluator 分数回写 agent 画像并影响后续选择（可查）
6. 回归: tests/console 全绿 + 既有 11784 基线不破坏

## 8. 版本

内核重构 → **语义化升 v1.2.0**（S10-087 完成时）；阶段内仍按 patch+1（v1.1.5/1.1.6…）。

## 9. 风险与护栏

- **成本**: 多 Agent = 每角色一次 LLM 调用 → 复用 budget.py 预算护栏（已有）
- **真实 E2E 依赖网络**: 沙箱只能验证"调用链正确"，真实验证必须在你的环境跑
- **避免二次漂移**: 每个 sprint 以"真实 E2E 锚点"验收，不造壳（沿用 S10-084 的 demo 锚点习惯）

---

**确认后从 S10-087 P0 开始。** 只重建智能层，保留基础设施。

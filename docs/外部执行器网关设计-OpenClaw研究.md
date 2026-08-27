# AI Factory 外部执行器网关设计（OpenClaw 研究借鉴）

> 日期: 2026-08-28 | 类型: 研究设计文档 (S10-127 P2.4)
> 依据: OpenClaw 开源架构 (MIT) 深读 + AI Factory 现状 (v1.1.237) + 外部委派链路审计
> 结论先行: **外部执行器 (codex/claude/hermes/…CLI) 需要一个统一"执行器网关"——OpenClaw 的
> Gateway + 任务控制面 + Hooks + 审计是最佳参考; 我们已有 60% 基础 (executor registry /
> delegate_external / session_hooks / handoff / audit), 缺的是"网关层统一编排 + 任务控制面 +
> 细粒度权限", 按 M1-M4 增量落地, 不需要重写。**

---

## 1. 背景与目标

用户诉求 (历史): "如何监控外部 agent (事件/执行效率/完成率/回修/验证), 需要通用性,
不能出一个产品就改代码; 设计要严谨"。

现状: `delegate_external` → `executor.run(adapter, prompt, project_dir)` 直接调外部 CLI,
监控用 `record_invocation`, 权限用 session_hooks PreToolUse。缺:
1. **统一网关编排**: 任务 → 选执行器 → 执行 → 验证 → 回写, 没有串成状态机
2. **任务控制面**: 外部执行没有持久化任务注册表 (无 audit/ownership/status/重试)
3. **细粒度权限**: 外部 agent 能做什么 (文件范围/命令白名单) 无配置
4. **通用适配**: 新增外部 agent (openclaw/pi/codex) 需改代码, 未纯配置化

## 2. OpenClaw 架构要点 (可借鉴)

| OpenClaw 组件 | 职责 | 对 AI Factory 的借鉴 |
|---|---|---|
| **Gateway** (hub-and-spoke) | 中央进程: HTTP/WS + 30+ RPC + 路由 → agents | ⭐ 我们的"网关"= 会话/CLI/API → 外部执行器的统一入口层 |
| **Multi-agent routing** | 按 channel/account/peer → 隔离 agent (workspace + 独立会话) | ⭐ 按项目/任务 → 隔离执行器实例 (独立 cwd/workspace) |
| **Tasks 控制面** (SQLite) | 统一注册表: ACP/subagent/cron/CLI 后台任务; ownership/status/audit/重试 | ⭐⭐ 我们缺的: 外部执行任务注册表 (exec_state 只覆盖执行链, 不覆盖外部委派) |
| **Tool Registry 75+** | 工具注册 + MCP 中介 + 权限 | 我们已有 tool_schemas + MCP (P2.3), 补权限分级 |
| **Sandbox (Docker)** | 执行隔离 | 我们 P2.2 命令级护栏; 系统级沙箱为后续 |
| **Skills 系统** | 可插拔技能 (121 个) | 我们已有 skill 导入 (U-4), 保持 |
| **Hooks 事件总线** | 生命周期事件 + 拦截 | 我们已有 session_hooks (M4/P1.5), 扩到执行器事件 |
| **Memory (embeddings)** | 语义记忆 + dreaming | 我们 project_memory/handoff 已有, 检索可增强 |
| **Subagent registry** | 嵌套子 agent 隔离上下文 | 我们 chain 执行链已有雏形 |

## 3. 目标架构 (分层)

```
用户请求 (会话/CLI/API)
      │
      ▼
┌──────────────────────────────┐
│ ① 执行器网关 (gateway)        │  ← 新增: 统一入口 + 编排状态机
│   route(task) → pick executor │     任务 → 选执行器 → 执行 → 验证 → 回写
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ ② 任务控制面 (task registry)  │  ← 新增: SQLite/JSON 注册表
│   id/status/owner/audit/retry │     (OpenClaw tasks 借鉴)
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ ③ 执行器适配层 (adapters)     │  ← 已有, 配置化扩展
│   codex/claude/hermes/…CLI    │     通用契约 {exit_code, output, error}
└──────────────┬───────────────┘
               ▼
┌──────────────────────────────┐
│ ④ 护栏 (sandbox + hooks + 权限)│  ← P2.2 命令校验 + M4 hooks + P1.5 权限模式
│   危险拦截 / 审批 / 审计        │
└──────────────────────────────┘
               ▼
       验证 → 回写 (任务/记忆/审计)
```

## 4. 与现有组件映射 (60% 已有)

| 目标层 | 现有组件 | 差距 | 落地 |
|---|---|---|---|
| 网关编排 | `chain_start/chain_next` + `delegate_external` | 无"验证→回写"闭环状态机 | M1: 执行器网关编排 |
| 任务控制面 | `exec_state.py` (执行链) | 不覆盖外部委派; 无 owner/audit/retry | M2: 外部任务注册表 |
| 适配层 | `external_executor/executor.py` + registry | 新增执行器需改代码 | M3: 配置化适配器 (JSON 声明) |
| 权限 | `sandbox.py` + session_hooks + P1.5 权限模式 | 外部 agent 无细粒度文件/命令权限 | M3: 执行器权限配置 |
| 验证/回写 | `answer_verify` / `exec_state.deliver` | 外部产出验证可加强 | M4: 产出验证 + 回填 Spine |

## 5. 落地路线 (增量, 不重写)

| 阶段 | 内容 | 预估 |
|---|---|---|
| **M1 网关编排** | `executor_gateway.py`: 任务 → route → run → verify → 回写 状态机; 复用现有 executor/registry | 2-3 天 |
| **M2 任务控制面** | `external_task_registry.json`: id/status/owner/started_at/result/retry/audit; 监控页可查 | 2 天 |
| **M3 配置化适配器 + 权限** | 执行器声明文件 (binary/args/timeout/工作目录白名单/命令白名单); 新增执行器=加 JSON | 2-3 天 |
| **M4 验证回填** | 外部产出 → answer_verify 校验 → 回填任务状态 + Spine closure | 2 天 |

## 6. 开放问题

- 外部 agent 内部行为无法沙箱化 (codex 内部命令) → 靠其自身沙箱 + 我们命令级护栏 + 审批
- 执行器并发 (多项目同时委派) → M2 控制面加队列/串行锁
- 成本/效果监控 → record_invocation 已有, 扩展维度 (时长/重试/完成率) 到监控页

## 7. 结论

- **OpenClaw 是"外部执行器网关"的最佳参考** (Gateway/任务控制面/Hooks/审计 全有)。
- 我们已具备 60% 基础 (executor/hooks/handoff/audit/sandbox/MCP), 缺的是**统一编排 + 外部任务注册表 + 配置化适配/权限**。
- 按 M1-M4 增量落地 (约 8-11 天), 不需要重写; 新增外部 agent 最终 = 加一个 JSON 声明。

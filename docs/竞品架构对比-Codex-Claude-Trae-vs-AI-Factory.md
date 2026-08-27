# 为什么不能复用 Codex / Claude / Trae — 架构对比分析

> 日期: 2026-08-28 | 依据: Codex Agent Loop 官方文章 + Claude Agent SDK 官方文档 + Trae 公开架构解析
> 结论先行: **Agent Loop 架构我们已经是同款; 真正复刻不了的是"模型能力"; 基础设施(压缩/缓存/动态工具/权限/并行)部分可借鉴; 定位不同(工厂 vs IDE/单agent)。**

---

## 1. 三方核心设计

### Codex（openai/codex 已开源）
- **Agent Loop**: 输入 → 推理(Responses API) → 工具调用 → 结果回喂 → 循环 → 助手消息
- **上下文管理**: 精确前缀追加(旧提示是新提示的前缀 → 提示缓存命中) + 超阈值自动压缩(/responses/compact, 保留模型对对话的理解)
- **缓存意识**: 静态指令放提示开头, 可变内容放末尾; 中途改 tools/模型/沙箱 = 缓存未命中
- **双层安全**: 系统级沙箱(execpolicy 硬隔离) + Approval Policy
- **模型**: gpt-5.2-codex + 模型特定 base_instructions(gpt-5.2-codex_prompt.md)

### Claude Code（Agent SDK 已开源）
- **Agent Loop**: 同样循环; max_turns / max_budget 控制
- **工具**: 19+ 权限门控 (Read/Edit/Write/Glob/Grep/Bash/WebSearch/Agent/Skill/AskUserQuestion/TaskCreate)
- **ToolSearch**: 动态发现工具(不预加载全部) — 按需加载
- **并行工具**: 只读工具并发执行, 修改工具串行
- **权限**: allowed/disallowed_tools + permission_mode(default/acceptEdits/plan/dontAsk/auto/bypassPermissions)
  - **auto 模式**: 用 Sonnet 4.6 做背景分类器自动批准/拒绝
- **Hooks**: 工具调用前拦截/修改/阻止
- **上下文**: compaction 自动压缩 (compact_boundary 事件)
- **模型**: Claude (Fable 5/Opus 4.7+/Sonnet 5)

### Trae（字节）
- **本地运行时**: Rust + WebAssembly 混合架构(非 Electron), LLM 调度/代码索引/语义补全/任务编排全收归本地
- **Agent 2.0 (SOLO)**: 高自主权, 多 agent 并行(最多 20), SWE-bench Verified 榜首
- **能力**: MCP 支持 + Global Memory + Design Mode + Voice Chat; 基于 VS Code 同源(插件生态沿用)

---

## 2. 逐项对比 AI Factory

| 能力 | Codex/Claude | Trae | AI Factory (v1.1.224) | 差距 |
|---|---|---|---|---|
| Agent Loop | ✅ 核心 | ✅ | ✅ 同款(v3) | **无差距(同架构)** |
| 工具调用 | ✅ 模型自主 | ✅ | ✅ 模型自主(FC) | 无差距 |
| 执行过程可见 | ✅ 流式展示 | ✅ | ⚠️ 刚加工具徽章(v1.1.224) | 接近 |
| 上下文管理 | 精确前缀+自动压缩 | Global Memory | 话题账本(分块/取舍/压缩) | 有雏形, 无"精确前缀缓存" |
| 提示缓存 | ✅ 前缀缓存优化 | — | ❌ 无缓存意识 | 成本/延迟差 |
| 动态工具发现 | ✅ ToolSearch | ✅ | ❌ 静态 15+ 工具 | 模型选择压力大 |
| 并行工具 | ✅ 只读并行 | ✅ | ❌ 串行 | 慢 |
| 权限模式 | ✅ 6 种+auto分类器 | ✅ | ⚠️ 敏感动作审批 | 无 auto/细粒度 |
| Hooks | ✅ 工具前拦截 | — | ❌ 无 hook 层 | 无 |
| 系统级沙箱 | ✅ execpolicy | ✅ | ❌ 无(仅审批) | 安全差 |
| MCP | ✅ | ✅ | ❌ 私有 registry | 生态差 |
| 模型 | GPT-5.2/Claude | 顶级+自研 | DeepSeek | **硬差距** |
| 定位 | 单编码 agent/IDE | IDE | AI 软件工厂(编排/审计/治理/外部委派) | **不同** |

---

## 3. 为什么不能"复用"（三个硬约束 + 一个定位差异）

### 硬约束 1: 模型是天花板, harness 抄不来模型
- Codex/Claude 的"懂人/会干活" = 顶级模型的语义理解/推理/指令遵循
- harness 只是外壳; **换个弱模型, 同样的 loop 会跑偏**(你实测的"所答非所问"就是证据)
- Claude auto 模式连权限判断都用 Sonnet 4.6 — 好模型是基础设施

### 硬约束 2: 核心 prompt 是模型特定的
- gpt-5.2-codex_prompt.md / Claude 系统提示, 都是为各自模型微调过的
- 抄过来不匹配 DeepSeek, 反而更差 — 我们只能写自己的

### 硬约束 3: 基础设施是重投入
- 系统级沙箱(execpolicy)、提示缓存前缀优化、/compact 端点、MCP 生态
- 每一项都是独立大工程, 不是"粘贴复用"

### 定位差异: 我们要的不是"一个聊天框"
- Codex/Claude = 人直接指挥单个 agent
- Trae = IDE 形态
- 我们 = AI 软件工厂: 编排 agent、审计链、治理、外部执行器委派(codex/claude/hermes 当员工)
- 这决定了我们不能照搬"单一 agent UI", 而是"工厂控制台 + 员工池"

---

## 4. 能借鉴什么（按性价比排序）

| 借鉴项 | 来源 | 落地难度 | 价值 |
|---|---|---|---|
| 1. 工具执行过程流式展示 | Claude AssistantMessage | 中 | 高(已做徽章, 可做流式) |
| 2. 动态工具发现(ToolSearch) | Claude | 中 | 高(15+ 工具按需加载, 减模型压力) |
| 3. 权限模式化 | Claude | 中 | 高(plan/acceptEdits/auto) |
| 4. 提示缓存意识(静态前缀) | Codex | 低 | 中(省成本/延迟) |
| 5. 只读工具并行 | Claude | 低 | 中(快) |
| 6. Hooks 层(工具前拦截) | Claude | 低 | 高(审计/校验/拦截) |
| 7. 本地代码索引 | Trae | 高 | 高(检索/补全加速) |
| 8. MCP 标准化 | 三方 | 高 | 高(外部生态) |

---

## 5. 结论

- **Agent Loop: 已复用**(同款架构, 无需抄)
- **模型: 不可复用** — 唯一硬差距, 换强模型即提升(机制已就位: agentic/reflection/对齐校验)
- **基础设施: 挑着借鉴** — 工具流式展示✅ / 动态工具 / 权限模式 / 缓存意识 / 并行 / Hooks
- **定位: 保持工厂** — 我们的差异点(编排/审计/治理/外部委派)正是 Codex/Claude 没有的

**下一步建议**: 按性价比, 先做 2(动态工具) + 6(Hooks 层) + 4(缓存意识) — 这四项直接提升会话"像 Codex/Claude"的体感。

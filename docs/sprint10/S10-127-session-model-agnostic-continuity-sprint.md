# S10-127 会话 Sprint 实施计划（模型无关 + 连续性 → 换模型/接得上/不选错/不丢失）

> 日期: 2026-08-28 | 前置: v1.1.224（AgentLoop v3 + Reflection + TopicLedger + 记忆 + 可观测已落地）
> 类型: **重要 Sprint 计划**（Founder: "给我解决方案" → "写计划"）
> 依据: [会话系统综合诊断与解决方案](../会话系统综合诊断与解决方案-v1.1.224.md) +
>       [会话解决方案-实施计划](../会话解决方案-实施计划.md) + 模型接入代码审计
> 状态: **✅ 已实施完成 (v1.1.225→v1.1.234)** — P0(M1-M4) + P1(P1.1-P1.5) 全部落地，WebUI 实测通过，235 回归测试全过

---

## 0. 为什么这是重要 Sprint

会话架构方向已对（agentic 同款），但**四个工程缺口**让体感上不去：

1. **模型焊死** —— `call_with_tools` 硬编码 OpenAI 兼容形状、只取 providers.json 第一个 provider，
   **未接已有 LLMRouter/ModelCatalog** → 换 Claude/Gemini 会挂，设置里选模型会话不生效
   （Founder: "以后换其他模型，我怎么办"）
2. **工具选错** —— 21 个静态工具每次全量塞给弱模型 → "扫代码返回文档数据"（工具层）
3. **会话接不上** —— 跨会话只有"最近 N 条记忆"，无结构化交接；
   任务库 T-系列多项已标 done 但体验仍断（**标完成 ≠ 真到位**，Founder 一直强调）
4. **不沉淀** —— 无会话级 Hooks：压缩前不交接、会话结束不提取决策/教训/错误→解法

**Sprint 目标：会话从"能用"→"换模型只改配置、工具必调对、继续能接上、结束不丢失"。**

成功标准（验收总纲）：
- ✅ 设置里切换模型（deepseek/openai/claude/gemini）→ 会话立即生效，不挂（M1）
- ✅ 说"扫代码/看代码逻辑" → 必调 read_code 真读代码；说"扫描项目" → 必调 project_scan 带证据数字（M2）
- ✅ 新会话"继续做 XX" → 定位任务 → 展示"上次进展到哪 + 下一步"（M3，T-6/T-8 真落地）
- ✅ 压缩后回来接得上；会话结束决策/错误→解法自动沉淀，下个会话可用（M4）
- ✅ 回归: `test_real_conversation.py` 全过；WebUI 会话实测通过

---

## 1. 史诗拆解（4 个史诗，按依赖顺序）

### M1 模型无关适配（P0-1 · 地基 · 先做）

**目标**: 会话链路接 LLMRouter + ModelCatalog，Provider 可插拔，能力协商降级。

| 任务 | 内容 | 验收标准 |
|---|---|---|
| M1.1 Provider 适配器 | 新建 `session/llm_gateway.py`：统一内部形状(OpenAI 为标准)；适配器注册表 `openai_compat`(deepseek/openai/moonshot/kimi/ollama) / `anthropic`(Messages API tool_use) / `gemini`(functionCall)；新 provider=加适配器不改主循环 | 单测：三种消息/工具形状互转；未知 provider 响亮报错 |
| M1.2 接入模型路由 | `call_with_tools` 改走 gateway；model_choice 来自 `LLMRouter.route(explicit_provider, explicit_model, project_dir, required_capabilities=["fc"])`；设置里选的模型在会话生效 | 切模型实测：deepseek↔openai↔anthropic 均跑通 FC |
| M1.3 能力协商降级 | 读 `ModelCatalog.get_model().capabilities`：无 fc → prompt 套 JSON 兜底；上下文窗口 → 注入截断；工具搜索能力 → 预告 M2 | 无 FC 模型不挂，走降级路径；现有 deepseek 回归全过 |

**依赖**: 无（LLMRouter/ModelCatalog 已有）| **风险**: Claude/Gemini 需对应 API key 实测；无 key 先做适配器+降级，用 OpenAI 兼容端点验证形状转换

---

### M2 BM25 动态工具发现（P0-2）

**目标**: 21 个工具不再全量塞给模型；"扫代码/扫描项目"必调对工具。

| 任务 | 内容 | 验收标准 |
|---|---|---|
| M2.1 工具检索 | 新建 `session/tool_search.py`：`catalog_summary()`（~400 token 目录，中英关键词）+ `discover_tools(query, top_k=5)` BM25（零依赖 stdlib：camelCase/snake_case/下划线分词 + 子串/词频评分）+ `tool_search` 元工具 schema | 单测：给定"扫描项目" top-5 含 project_scan；"读取代码" 含 read_code |
| M2.2 动态工具面 | `tool_schemas()` 改造：首轮只给核心工具 + tool_search；命中后**累积加入可见列表**（Eino 模式）；dispatch 不变；delegate_external 也入检索范围 | 实测："扫描项目" 模型只见 3-5 工具且必调 project_scan；工具 schema token 占用可测下降（audit 记 tool_catalog_bytes） |

**依赖**: M1（网关支持工具面变化）| **风险**: BM25 中文描述匹配弱 → 工具名/描述中英双语；先子串+词频实测调优

---

### M3 跨会话交接协议（P0-3 · T-4/T-6/T-8 真落地）

**目标**: 新会话"继续做 XX" → Spine 交接；任务↔会话↔决策可追溯；AI 摘要不当事实。

| 任务 | 内容 | 验收标准 |
|---|---|---|
| M3.1 Project Spine | 新建 `session/handoff.py`：`ProjectSpine`{current_goal / active_requirements / handoff_card(进展+下一步+阻塞) / resume_point(引用 exec_state) / closure_memory(归档任务压缩记忆) / source_pointers} + **权威分层**（user_intent > verified_state > repo_evidence > agent_claim > summary，低等级不当事实）；落盘 `<data_dir>/project_spine/<project_id>.json` | 单测：Spine 读写/更新；权威等级过滤（低等级不注入为事实） |
| M3.2 记忆升级 | `project_memory.py`：5 类记忆（decision/learning/error/pattern/observation）+ source 等级 + 时间衰减 | 单测：分类写入/按等级读取/衰减排序 |
| M3.3 会话注入 | `task_continue` 改造（定位任务→读 Spine→注入 handoff_card+resume_point）；`run_agent` 新会话首轮带 Spine 视图；closure-over-replay（不重放旧聊天） | 端到端：会话 A 任务做一半 → 会话 B"继续做 XX" → 能说进展+下一步；归档任务只投影摘要 |

**依赖**: 无（复用 exec_state/project_memory）| **风险**: 权威分层需在写入点加 source 标记（扫描/任务操作/agent 回答各处）

---

### M4 会话级 Hooks 生命周期（P0-4）

**目标**: 压缩前交接、结束沉淀；与工具级 Hooks 合并双层。

| 任务 | 内容 | 验收标准 |
|---|---|---|
| M4.1 事件框架 | 新建 `session/session_hooks.py`：事件 SessionStart/UserPromptSubmit/PreToolUse/PostToolUse/PreCompact/SessionEnd；hook 注册表（Python 函数，可 deny+reason 或注入） | 单测：事件分发/注册/deny 短路 |
| M4.2 内置 hooks | SessionStart→注入 Spine handoff_card+最近 decision/error→solution；PreCompact→生成结构化交接写 Spine；SessionEnd→提取 decision/error→solution/rule 写 project_memory | 端到端：压缩触发前 Spine.handoff_card 更新；结束自动沉淀，下个会话 SessionStart 可用 |
| M4.3 敏感动作门 | PreToolUse 挂敏感动作（建/改任务/委派/推送需审批，复用已有逻辑）+ 审计事件 | 实测：未审批的删除/推送类动作被 deny + reason；审计有记录 |

**依赖**: M3（交接载体）| **风险**: 压缩触发点在何处需确认（agent loop 无原生 compact → 在超长注入前触发）

---

## 2. 排期与里程碑

```
M1 模型适配 (2-3天) → M2 动态工具 (1-2天) → M3 交接协议 (2-3天) → M4 会话Hooks (2天)
合计 ≈ 8-10 天
```

| 里程碑 | 完成标志 | 用户可验证 |
|---|---|---|
| MS-1（M1 后） | 切模型不挂 | 设置里换 Claude/GPT 实测会话 |
| MS-2（M2 后） | 工具必调对 | "扫代码/扫描项目" 实测 |
| MS-3（M3 后） | 会话能接上 | 会话 B"继续做 XX" |
| MS-4（M4 后） | 结束不丢失 | 压缩后回来 + 下个会话带教训 |

## 3. 同步 Todo 任务清单（开工时创建）

| 任务标题 | 优先级 | 依赖 |
|---|---|---|
| [会话] M1.1 Provider 适配器（llm_gateway: openai_compat/anthropic/gemini） | P0 | — |
| [会话] M1.2 call_with_tools 接 LLMRouter+ModelCatalog（设置选模型生效） | P0 | M1.1 |
| [会话] M1.3 能力协商降级（无FC→prompt套JSON；上下文窗口截断） | P0 | M1.2 |
| [会话] M2.1 tool_search.py BM25 工具检索（catalog+discover+元工具） | P0 | M1 |
| [会话] M2.2 动态工具面（首轮核心+tool_search，命中累积可见） | P0 | M2.1 |
| [会话] M3.1 ProjectSpine + 权威分层（handoff.py） | P0 | — |
| [会话] M3.2 project_memory 升级（5类+source等级+衰减） | P0 | M3.1 |
| [会话] M3.3 task_continue/run_agent 注入 Spine（T-6/T-8 真落地） | P0 | M3.1+M3.2 |
| [会话] M4.1 session_hooks 事件框架 | P0 | — |
| [会话] M4.2 内置 hooks（SessionStart/PreCompact/SessionEnd） | P0 | M4.1+M3 |
| [会话] M4.3 PreToolUse 敏感动作门+审计 | P0 | M4.1 |

**注**: 任务库 T-系列（跨会话恢复/继续意图/双向追溯）已标 done 但体验未达 Spine 级 →
M3 落地时回填/升级对应任务为真实交付，防止"标完成 ≠ 真到位"。

## 4. 风险

- M1: Claude/Gemini 需 API key 实测；无 key 先做适配器+降级路径
- M2: BM25 中文匹配弱 → 中英双语关键词 + 实测调优
- M3: 权威分层写入点分散 → 收敛到统一写入入口（spine.update(source=...)）
- M4: agent loop 无原生 compact 事件 → PreCompact 挂"超长注入前"触发点

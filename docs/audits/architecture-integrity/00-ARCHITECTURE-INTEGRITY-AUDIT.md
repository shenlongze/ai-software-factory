# 00 — ARCHITECTURE INTEGRITY AUDIT (2026-09-07, READ-ONLY)

## 核心问题回答
当前 AI Factory 是否遵守"数据/逻辑/能力/状态/治理统一, WebUI 无独立
业务真相, Node 统一 Loop, Tool/Capability/Node/Work 分层"?

**部分遵守, 存在 3 条结构性偏离** (见下)。整体 = DEGRADED。

## 规模事实 (代码取证)
- 276 py 文件 / 118K 行; agent_loop.py 3840 行 (56 def, 35 _fc schema,
  35 dispatch tool 分支 — 工具自注册/自描述/自处理 全集于一身)
- session/ 巨型: orchestrator 4209 / actions 4133 / board 3230 /
  agent_loop 3840 — 单文件职责超载
- 域 truth 状态机各居其位: product_truth / node_runtime / acceptance_truth
  / release_truth / production_run / artifact_lifecycle (域真, 各自独立
  状态机属正常域边界)
- 能力路由存在: capability_router (S10-116, agent/skill/mcp 匹配),
  但【不管理 tool 注册】; skill_search (4 技能库)

## 核心结论 (三偏离)
### 偏离 1: Tool universe 集中硬编码于 agent_loop (P1)
tool_schemas 35 工具 + dispatch 35 分支同文件内联; handler 逻辑 (gate/
scope/recovery/业务规则) 与 schema/description 同置; 新增工具必改
agent_loop。capability_router/skill 未承载 tool 注册/发现/授权 —
"插件化已存在 (plugin_kernel) 但核心路径绕过 Registry"。
根因: 历史渐进 (S0.5 起工具即 agent_loop 内联), 无重构触发点。
影响: 可维护性/权限/发现分裂; 违反 能力统一。
收敛: 工具描述/handler 保留逻辑 (域行为), schema+授权+发现上移注册层
(增量迁移, 不一次重写)。

### 偏离 2: 会话侧并行状态系统模拟 Node (P1)
session 侧: conv_state.json / session_state.json / session_plans.json /
session_topics/ + exec_state(session_exec) / topic_ledger / chat.json —
多层会话/工作状态; Node 侧真契约 (node_runtime) 仅执行段。
产品前链 (IDEA→PLAN) = product_truth 记录 + 会话逻辑 (governor/resolver/
guide/exec 指令) → Conversation 层承担了本属 NodeRun 的执行语义
(上一审计结论, 代码实证)。
根因: 前链先于 node_runtime 存在; S47-S50 在会话层补 Node 行为。
收敛: Node 化 (E1/E2/E3 设计已批) + 会话状态收敛为 UI 引用。

### 偏离 3: LLM prompt/tool description 承担业务规则 (P1)
tool description 含"审批后/先 plan_development/幂等引导/已消费拒绝"
等业务语义; guide 文本 (执行指令/克制) 规则性内容由 prompt 表达 —
部分属 LLM 引导 (合法), 部分属业务策略 (应代码治理)。
判断: 描述中"何时可调"类 = 引导 (保留); "必须/禁止/授权语义"类 =
耦合 (上移 gate/契约 — S48 gate 已部分承接)。
影响: 规则分散 (prompt+code 双处), 行为漂移风险。
收敛: 业务策略代码化 (gate/policy), prompt 只留 LLM 判断引导。

## 分域健康
- Product Truth / node_runtime / artifact / acceptance / release:
  域 SSOT 清晰 (各 store 唯一) — 健康 (内部重复少)
- 前端: useState 多为 UI state (selection/input/runs 投影) —
  无独立业务真相 (健康; 个别进度卡 S35 已收敛)
- Cross-project scope: S49-FIX.1 已代码 enforce (健康)
- id↔slug 分叉: S50-P0-FIX 已收敛读路径 (残余: 双 slug 函数口径
  不一致 service._confirm_slug vs space._slugify — P2)

## 评分
Architecture Integrity Score: 62/100
P0: 0 (无数据破坏级双 SSOT/泄漏/绕过)
P1: 4 (tool 集中硬编码 / 会话状态并行模拟 Node / prompt 业务耦合 /
    capability_router 未接核心)
P2: 6 (slug 双口径 / session 模块巨形 / legacy fallback 常驻 /
    命名不统一 / conv_state 与 exec_state 边界 / 多会话 store 未收敛)
P3: 若干 (常规质量)

Verdict: DEGRADED — 域 truth 层健康; 会话/工具编排层需收敛
(方向已定: Node 化 + 工具注册层 + 规则代码化), 非重建。

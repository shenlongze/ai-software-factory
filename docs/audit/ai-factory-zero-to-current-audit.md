# AI Factory — Zero-to-Current 验尸级全面现实审计

> 日期: 2026-08-31 | 方法: production-reality-audit skill (Zero-to-Current 协议)
> 原则: 不信任任何历史结论 (Sprint 报告/测试绿/文档/模块名), 只信证据。零代码修改。
> 证据优先级: 真实运行 > 真实代码 > 真实测试 > 真实产物 > Git history > 配置 > 文档 > 推测

---

## 1. Executive Summary

**当前真实产品 = "一个能启动、能显示页面、但核心业务从未发生过的系统"。**
1340 提交 / 68 模块 / 349 API / 828 文档,但生产数据里: 会话 0、任务 0、需求 0。
这不是"差一点",是**核心闭环从未被真实走通过一次**。

## 2. Original Vision (最初想做什么, 2026-08-05)

原始设计 (docs/design/agent-model.md + architecture.md, 第一个提交 c8661109):
- **AI Software Factory**: 多 Agent 协作执行软件项目, 真实交付代码
- 核心原则: Orchestrator 不写代码(只委派)/ 一切以事件为中心 / 自报告不可信验证独立 / KISS 最小模块集(9 模块)
- Agent 实例 = Role + Skill + Delegation

## 3. Current Reality (现在实际是什么)

- 自述: "AI Workforce Operating System" (Conversation-driven)
- 实际: 能启动 (5180/8011 活着), 能显示三栏 UI, 能聊模板回复
- 生产数据 (2026-08-31 实测):
  ```
  conv 实体: 0    (会话从未真实创建)
  task 实体: 0    (任务从未真实创建)
  req 实体: 0     (需求从未真实创建)
  project: 2      (仅测试残留)
  审批: 4
  workspace 落地代码: 0  (75 个 patch 从未应用)
  ```

## 4. Strategic Drift (战略漂移)

| 维度 | 原始 (08-05) | 现在 (08-31) | 漂移 |
|------|------------|------------|------|
| 目标 | 交付真实软件 (代码落地) | 运营对话 (AI 员工聊天) | 🔴 核心目标丢失 |
| Agent | 多 Agent 协作, 每 Agent 委派干活 | 角色定义存在但执行链断 | 🔴 |
| 交付物 | 代码/产物/验证 | 对话/卡片/状态 | 🔴 |
| 演化 | 9 模块 KISS | 68 模块/1340 提交 27 天 | 🔴 膨胀 |

## 5. Architecture Reality

- 分层存在 (unified_contract 底座 ← conversation/task/project ← operational_state/tower)
- 但: 349 API 前端只用 27; 核心链路 (对话→执行→结果) 前端未接
- 死代码: orchestrator/actions/discovery/replanning/decomposer 等 (14K+ 行, 早期 v3 重构遗留, 引用近乎为零)

## 6. Codebase Audit

```
factory-console: 264 py / 110,199 行
factory-core:    138 py / 33,814 行
factory-exec:     52 py / 22,154 行
factory-org:      18 py / 11,885 行
前端: 183 文件
God Objects: cli_factory.py 8145 行 / service.py 4911 行 / workflow_runner 1181 行
```

## 7. Agent Audit

- workforce_os 定义角色: product_manager/market_analyst/ux_designer/software_architect/software_developer/qa_engineer/release_engineer
- 能力映射: software_developer → [llm, codex]; qa → [llm, pytest]
- **但**: 角色定义 ≠ 角色干活。执行链 (role → execute → result → apply) 断

## 8. Multi-Agent Audit

**多个 Agent 协作 vs 一个 LLM 切换 prompt?**
- exec 层有真实运行时 (professional_workflow: 真实 codex 执行器)
- 但 factory 层多角色 = 定义/状态, 无真实协作总线
- **结论: 实质是"单 LLM + 状态机", 不是多 Agent 公司**

## 9. Business Workflow Audit (Idea→Product→Software→Release)

```
Idea → Discovery → PRD → Architecture → Engineering → Development → QA → Release
  ❌      ❌        ❌        ❌             ❌           ❌        ❌    ❌
(生产数据 0 会话/0 任务/0 需求; 75 patch 0 落地 — 全链从未真实发生)
```

## 10. CLI Audit

- cli_factory.py 8145 行 (God Object), 17+ 命令
- 有真实命令 (start/stop/doctor/config/project/run)
- 未逐个真实验证 (审计期间不运行破坏性命令)

## 11. API Audit

- 后端 349 端点 (fastapi_adapter.py)
- 前端三栏只用 27: conversations(4) + ops(3) + projects-os(3) + artifacts(1) + approval(1)
- **主链 API (runtime/execute, task-tree, decompose, trigger_work) 前端未调用** → 闭环断

## 12. Web UI Audit

- 三栏 (Context/Conversation/Workspace) 能渲染
- 会话: 关键词正则 (INTENT_PATTERNS) + 模板回复 — 非 LLM 理解
- 旧系统并存: AfConversationPanel(旧 /api/sessions) vs AfConversationCenter(新 /api/conversations)
- 死组件: AfSidebar/BrowserWorkspace/AfCompanyHome/AfMonitorPage (半死)
- 29 页面文件, 路由 16 条, 死页面占一半

## 13. Real E2E Audit

- 今天 (08-31) 我在浏览器实测: 发送"我有哪些项目" → 模板回复"聊聊「」目标用户是谁" (错误)
- 生产数据 0 会话: 从未有任何用户 (含创始人) 真实走通一次完整会话

## 14. Production Truth Matrix

| Claim | Reality | Evidence | Gap |
|-------|---------|----------|-----|
| "K9 Human Workspace 完成" | UI 能显示, 业务未发生 | conv=0, task=0 | 壳 vs 魂 |
| "会话可用" | 模板回复, 非真实理解 | "我有哪些项目"→DISCUSS | LLM 未接 |
| "真实 LLM E2E 通过" | 测试环境 codex 执行, 非产品数据 | 生产 0 会话 | 测试≠产品 |
| "AI Workforce OS" | 角色定义存在, 执行链断 | 75 patch 0 落地 | 定义≠干活 |
| "1108 测试通过" | 测试绿, 产品不转 | 生产 0 实体 | 测试≠可用 |

## 15. Testing Audit

- 586 测试文件, 208 含 mock (35%)
- 测试验证"零件在测试台转得动", 不验证"用户能开着车上班"
- 真实 LLM 测试: 测试环境 codex 执行, 生产数据 0

## 16. Observability Audit

- execution_records 94 条, 字段: action/agent/error/intent/result/result_id/task/timestamp
- **无 tokens/llm_calls/model/cost** — 动作摘要, 非 LLM 调用日志

## 17. Governance Audit

- governance_service (334 行): 审批单链路存在
- 生产: 4 个审批 (测试残留)

## 18. Memory/Learning Audit

- learning_engine_v2 (369 行): 存在
- 无真实会话/任务 → 学习闭环无数据可学

## 19. Architecture Debt

- God Object: cli_factory 8145 行 / service 4911 行
- 双会话系统: 旧 /api/sessions + 新 /api/conversations
- 双包名: factory_console (别名) vs factory-console (源码), editable finder 复杂
- factory start 后端加载旧代码 (幽灵进程/路径解析)
- 文档 828 份全过期 (文档是过程记录, 非产品描述)

## 20. Dead/Stub/Fake/Template Inventory

```
死代码: orchestrator(4133) actions(4121) conversation(1668) discovery(1285) ... ≈ 14K+ 行
stub:   workspace 0 代码落地 (75 patch 未应用)
template: 会话模板回复 (INTENT_PATTERNS + _make_reply 模板)
fake:   "能聊" 实际是关键词匹配
```

## 21. Capability Reality Matrix

| 能力 | 级 | 证据 |
|------|-----|------|
| 会话 (conversation_os) | C Placeholder | 关键词+模板, 生产 0 会话 |
| 任务 (task_tree) | C | 生产 0 任务 |
| 项目 (project_os) | B Partial | 2 测试残留 |
| 执行 (professional_workflow) | B | 测试环境真实 codex, 生产未接 |
| 运营 (operational_state) | B | 有状态机, 无数据 |
| 治理 (governance) | B | 4 审批残留 |
| 前端三栏 | B | 能渲染, 业务未发生 |

## 22. Maturity Matrix

```
L0 Missing  ← 生产业务闭环
L3 Implemented ← 模块存在 (unified_contract/conversation_os/...)
L5 Real Production ← 从未达到 (生产 0 实体)
```

## 23. Strengths (真实证据)

- unified_contract 底座设计干净 (0 依赖, 事件/实体/版本化)
- 测试体系真实存在 (586 文件, 零件在测试台转得动)
- 执行器真实 (codex 在测试环境真干活, 生成过代码)

## 24. Weaknesses

- 产品闭环从未真实发生 (生产 0 实体)
- 代码生成但不落地 (75 patch 0 应用)
- 会话理解是关键词 (用户已否定)
- 文档全面过期 (828 份误导)
- 膨胀失控 (27 天 68 模块 1340 提交)

## 25. Competitive Comparison

| 维度 | AI Factory 现实 | 主流 (Claude Code/Trae/Cursor) |
|------|----------------|-------------------------------|
| 对话理解 | 关键词正则 | LLM 语义理解 |
| 代码落地 | 0 (patch 不应用) | 直接改文件 |
| 执行闭环 | 断 | 完整 |
| 结果回对话 | 无 | 有 |

## 26. Strategic Drift (重复强调)

**最大漂移: 从"交付真实软件"漂到"运营对话界面"。** 08-05 目标是 Factory 交付代码; 08-31 是"AI 员工聊天"。核心目标丢失。

## 27. Top 20 Gaps

1. 会话理解 = 关键词 (非 LLM)
2. 生产数据 0 会话/0 任务/0 需求
3. 代码生成不落地 (patch 不应用)
4. 前端三栏不接执行链
5. 结果不回对话
6. 文档 828 份全过期
7. 死代码 14K 行
8. 双会话系统并存
9. factory start 加载旧代码
10. 双包名混乱
11. God Object (cli_factory 8145 行)
12. 角色定义 ≠ 角色干活
13. LLM 痕迹缺失 (无 token/cost)
14. 测试测零件不测产品
15. 会话模板回复
16. 旧壳组件半死
17. 326 提交未推送
18. 前端只用 27/349 API
19. 学习闭环无数据
20. 商业可演示性为零

## 28. P0/P1/P2

| 级 | 项 |
|----|-----|
| P0 | 会话 LLM 化 (用户已拍板方向) |
| P0 | 执行闭环: 对话→建项目→拆任务→执行→结果回对话 |
| P0 | 代码落地 (patch 应用) |
| P1 | 生产数据为 0 → 需真实跑通一次 |
| P1 | 前端接执行链 |
| P1 | 文档以代码为准重建 |
| P2 | 死代码清理 / 旧壳摘除 / 双会话统一 |

## 29. The Next 5 Highest-Leverage Moves

1. **M1: 会话 LLM 化** — conversation_os 理解/回复改 LLM (真实语义 + 说人话), 保留规则 fallback
2. **M2: 最小执行闭环** — 用户一句话 → 真实建项目/拆任务/执行 (trigger_work + runtime/execute 接前端)
3. **M3: 代码落地** — 执行结果真实写盘 (patch apply 闭环)
4. **M4: 结果回对话** — 执行完成 → LLM 说人话汇报 + 真实产物链接
5. **M5: 真实 E2E 验收** — 创始人浏览器走通一次: 说一句话 → 看到真实项目/代码/结果

## 30. Recommended Architecture Direction

**冻结外围, 立主干。** 只做一条链: 对话(LLM) → 理解 → 真实执行 → 结果回对话。其余 60+ 模块冻结 (代码不删, 不进用户路径)。

---

## 31. Final Verdict

```
Current Product: 一个能启动/能显示 UI/但核心业务从未发生过的系统
Current Maturity: L2-Skeleton (模块存在) → 产品层 L0 (业务从未发生)
Overall Score: 15/100 (产品层: 会话 5, 执行 5, 落地 0, 结果回对话 0, 文档 -, 商业 0)

Is it actually an AI Software Factory? NO
Is it actually Multi-Agent? NO (单 LLM + 状态机)
Is it production-capable? NO
Is the current architecture worth continuing? YES BUT REFACTOR (unified_contract 底座值得保留)

Biggest Strength: unified_contract 底座 + 测试体系 + 真实 codex 执行器
Biggest Weakness: 生产数据 0 实体 — 核心闭环从未真实发生
Biggest Strategic Drift: 从"交付真实软件"漂到"运营对话界面"
Single Most Important Next Move: M1 会话 LLM 化 + M2 最小执行闭环 — 让用户说一句话, 看到真实代码/结果落地
```

---

## Rebuild/Refocus Proposal (审计后不直接拆 Sprint)

| 项 | 决定 | 理由 |
|----|------|------|
| unified_contract | KEEP | 干净底座, 唯一值得保留的架构 |
| conversation_os | REBUILD (LLM 化) | 关键词→LLM, 核心 |
| project_os/task_tree | KEEP + 接前端 | 零件好, 没接线 |
| professional_workflow | KEEP (测试环境已证) | 真实 codex 执行器 |
| 前端三栏 | REFACTOR (接执行链) | 壳好, 魂没接 |
| 旧会话系统/旧壳 | DELETE (藏) | 双系统混乱 |
| 60+ 外围模块 | DEFER (冻结) | 不进 v0.1 |
| 828 文档 | REWRITE (以代码为准) | 全面过期 |
| 死代码 14K 行 | DELETE (后置) | 不挡主干 |
| 326 未推送 | PUSH (后置) | 仓库卫生 |

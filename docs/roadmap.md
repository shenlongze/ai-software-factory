# AI Software Factory — MVP Roadmap

> 版本: v0.1 | 日期: 2026-08-05 | 状态: 评审中
> 关联文档: [prd.md](./prd.md) · [phase1-plan.md](./phase1-plan.md) · [design/migration-plan.md](./design/migration-plan.md)

---

## 0. 总览

五阶段演进,每阶段**独立可交付、可回退**,随时可以停在任意阶段并长期受益。

| 阶段 | 名称 | 对应迁移方案 | 核心能力 | 状态 |
|:----:|------|:------------:|----------|:----:|
| Phase 0 | 项目初始化 | — | 骨架 + 设计稿 + GitHub | ✅ 已完成 |
| Phase 1 | 观察层核心 | Phase 1 (上半) | Event Logger + SQLite + 指标 | ⬜ 下一阶段 |
| Phase 2 | 观察层入口 | Phase 1 (下半) | CLI + Dashboard | ⬜ |
| Phase 3 | 管理层 | Phase 2 | Task Manager + Agent/Skill Registry + 断点恢复 | ⬜ |
| Phase 4 | 执行层 | Phase 3 | Workflow Engine + Runtime Adapter + KB 沉淀 | ⬜ |

**演进逻辑** (对应四个痛点): 先观察 (P1) → 再管理 (P2+P3) → 后自动 (P4)。

```
现状 (能干活, 看不见)
  │
  ▼ Phase 1-2 观察层 (只读不改行为)
  看得见: 事件日志 + 仪表盘 + 指标
  │
  ▼ Phase 3 管理层 (行为不改, 结构形式化)
  管得住: 任务状态机 + 断点恢复 + 登记表
  │
  ▼ Phase 4 执行层 (行为增强, 可回退)
  自己学: 工作流编排 + Runtime Adapter + 知识沉淀
```

---

## Phase 0 — 项目初始化 ✅ (已完成)

- **目标**: 搭好骨架,定好方向,设计稿先行。
- **交付物**:
  - 目录骨架 (factory-core / cli / dashboard / api / agents / skills / workflows / runtimes / knowledge / validation / mcp)
  - 8 份设计稿 (architecture / agent-model / skill-model / workflow-model / validation-model / memory-model / runtime-design / migration-plan)
  - README (定位/原则/入口) + GitHub 仓库 (commit `c866110`)
- **验收**: ✅ 目录结构符合 README 定义;✅ 设计稿覆盖九大模块;✅ 仓库可克隆、可提交。
- **工作量**: 已完成 (1 迭代)。

---

## Phase 1 — 观察层核心: Event Logger MVP

> 铁律: **只读,不改任何现有行为**。加"记录"不加"干预"。

- **目标**: 任何时刻都能回答"系统现在在做什么? 做过什么? 结果如何?";为后续阶段提供数据基础。
- **交付物**:
  - `factory-core/events/`: Pydantic 模型 (Event / EventType) + SQLite append-only 存储 + 指标聚合
  - 六类最小事件: `task.start` / `task.end` / `task.fail` / `tool.call` / `checkpoint` / `session.close`
  - pytest 测试套件全绿
- **验收标准** (全部满足):
  - [ ] 任何会话中途,能答出"当前在做什么任务、已耗时多久、做过哪些步骤"
  - [ ] 任一失败任务,能回溯到失败前的完整事件链
  - [ ] 连续 3 个会话的指标 (成功率/耗时/重试) 可对比
  - [ ] 全程未改变任何 Agent 行为 (对照行为基线)
  - [ ] 事件只追加、不修改、不删除 (append-only 语义验证通过)
- **预估工作量**: 4-5 人天 (1 个迭代)。详细拆解见 [phase1-plan.md](./phase1-plan.md)。
- **可回退点**: 停掉 Logger,系统行为原样。

---

## Phase 2 — 观察层入口: CLI + Dashboard

> 数据已有,给它一个"眼睛"。仍只读,不干预。

- **目标**: 工程师能用 CLI 查状态,技术负责人能一眼看清全局。
- **交付物**:
  - CLI (Typer): `factory init` / `factory logs` / `factory status` (+ task/workflow 命令骨架)
  - Dashboard (Rich): 进行中任务 (做什么、多久了)、最近事件流 (倒序)、失败/错误计数、指标对比
  - 指标视图: 成功率 / 耗时 / 重试,按天、按会话聚合对比
- **验收标准**:
  - [ ] `factory status` 5 秒内回答"当前在做什么任务、已耗时多久、做过哪些步骤"
  - [ ] `factory logs --task T-xxx` 可回放该任务完整事件链
  - [ ] Dashboard 三块视图齐全,数据与事件库一致 (投影正确)
  - [ ] CLI 全程无写操作 (纯查询)
- **预估工作量**: 4-5 人天 (1 个迭代)。
- **依赖**: Phase 1 (事件数据)。
- **可回退点**: 弃用 CLI/Dashboard,事件库仍在,Phase 1 价值不受损。

> Phase 1 + Phase 2 = 迁移方案中的完整 Phase 1 (观察层)。两者共同构成 MVP。

---

## Phase 3 — 管理层: Task Manager / Agent Registry / Skill Registry + 断点恢复

> 行为仍不改,但把"谁、什么、怎么"形式化登记,让恢复与分派有据可依。

- **目标**:
  1. 截断续跑可可靠恢复 (P2): 任务状态是磁盘事实,不靠会话记忆。
  2. 自报告有对照物 (P3): Agent 声称的能力与可靠性,有登记与评级可核。
- **交付物**:
  - **Task Manager**: 任务状态机 `pending → assigned → running → verifying → done | blocked | failed`,加 `paused`;每条任务: 目标、当前进度、下一步动作、产物路径。**恢复协议**: 断点续跑只认落盘状态 + 产物,不信任口头 summary;恢复时先核对产物存在,不存在则从最近停靠点重做。
  - **Agent Registry**: 每个 Agent 一条 (agent_id / 角色 / 技能绑定 / 可靠性评级);评级来自实证: 分析型、实现型 (范围清晰)、debug 型 (首次不可靠 → 需验证);评级升降需两次独立验证。
  - **Skill Registry**: 已有 Skill 登记造册 (触发条件、适用任务类型、已知坑);新经验落为 Skill 或 experiences/ 条目。
- **验收标准**:
  - [ ] 模拟截断 3 次,恢复后均从最近真实停靠点继续,无重复劳动
  - [ ] 每个 Agent 有评级;debug 型任务分派时自动附加"必须独立验证"要求
  - [ ] 新会话开工,能从 Skill Registry 检索到相关流程与已知坑
  - [ ] 登记表随每次任务结束自动更新,无手工维护负担
- **预估工作量**: 8-10 人天 (1-2 个迭代)。
- **依赖**: Phase 1 (事件数据是状态投影与评级的依据)。
- **风险对策**: 三张登记表就够,不加第 4 张;连续 3 个会话未更新的登记表视为腐化,触发清理。
- **可回退点**: 登记表作废,回到 Phase 2 行为。

---

## Phase 4 — 执行层: Workflow Engine + Runtime Adapter + KB 沉淀

> 行为增强开始,每个自动化点都可一键关闭 (回退到 Phase 3 状态)。

- **目标**:
  1. Workflow Engine 完整化: 多步任务自动编排、自动检查点、按失败模式自动重试。
  2. Runtime Adapter: 不绑定单一 Agent 框架,统一接入 Hermes / Claude Code / LangGraph 等。
  3. Knowledge Base 自动沉淀: 错误自动建档、经验自动提炼。
- **交付物**:
  - **Workflow Engine**: 声明式流程定义 (步骤/依赖/检查点/守卫) + 执行记录 (每步状态/耗时/产物) + 失败策略 (重试/降级/上报) + 三挡板 (产品冲突/架构变更/Scope 扩展) + 关键文件串行锁。检查点沿用 Phase 3 的 Task Manager 状态,不另起炉灶。
  - **Runtime Adapter**: 统一 Runtime 接口 (委派/事件上报/产物返回),第一版至少接 1 个真实 Runtime 实测。
  - **Knowledge Base 自动沉淀**: 失败任务自动生成缺陷草稿 (事件链→症状→根因线索,证据等级标 C),人工复核后升 B/A;同类失败出现 2 次提示"是否沉淀为经验?";新任务开工自动检索注入相关条目。
- **验收标准**:
  - [ ] 5 步以上的多 Agent 任务可全程自动编排,任一步失败按策略处理且事件链完整
  - [ ] 同一任务可通过 Adapter 在 ≥2 种 Runtime 上执行,零核心代码改动
  - [ ] 一次真实失败的调试,自动生成缺陷草稿;复核后根因在后续类似任务中被成功引用
  - [ ] 新会话开工自动带出 ≥1 条相关 KB 参考,且参考可忽略 (不干扰任务)
  - [ ] 任意自动化点可一键关闭,关闭后系统行为退回 Phase 3 且无残留异常
- **预估工作量**: 10-15 人天 (2-3 个迭代,可滚动)。
- **依赖**: Phase 3 (状态机 + 登记表) + Phase 1 (事件链)。
- **上线顺序** (最无害的先上): 自动检索注入 → 自动建档 → 自动提炼。
- **可回退点**: 逐个关自动化开关。

---

## 工作量汇总与节奏

| 阶段 | 预估工作量 | 周期 | 累计 |
|:----:|:----------:|:----:|:----:|
| Phase 0 | 已完成 | 1 迭代 | 1 迭代 |
| Phase 1 | 4-5 人天 | 1 迭代 | 2 迭代 |
| Phase 2 | 4-5 人天 | 1 迭代 | 3 迭代 |
| Phase 3 | 8-10 人天 | 1-2 迭代 | 4-5 迭代 |
| Phase 4 | 10-15 人天 | 2-3 迭代 | 6-8 迭代 |

**全局退出标准**: 连续 4 个真实会话满足 —— 可观测 (随时能答状态)、可恢复 (截断零丢失)、可信 (完成声明全部有证据)、可复用 (新坑不再重复)。

---

*下一步: 执行 [phase1-plan.md](./phase1-plan.md)。*

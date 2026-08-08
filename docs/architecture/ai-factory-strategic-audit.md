# AI Factory — Strategic Audit Report（全项目审计）

> 日期: 2026-08-08 | 状态: 审计完成（以代码实际为准, 不依据旧文档）
> 扫描基线: HEAD=14997ed | pytest 5493 | 158 事件 | 91 CLI 函数 | docs 119 份

## 1. 当前真实状态（诚实）

```
✅ 扎实的部分:
  Core 冻结 (25 模块: events/tasks/workflows/execution/approval/intelligence/metrics...)
  Organization 模型已实现 (factory-org: Company/Department/Role/Employee/Authority/Knowledge)
    — 正是"正确模型" (Company→Department→Role→Employee, 非 CEO Agent 树)
  Execution 工程 (factory-exec 28 模块: Context Ranking/Progressive/Budget/Experience/
    Candidate/Multi Run/Evaluator/Capability — Sprint 4+5 全落地)
  Runtime + Desktop (Tauri dmg) + Console Web UI (7 页面只读)
  5493 tests | 158 事件 | 35+ ADR | 119 文档

⚠️ 未达成:
  真实生产闭环: 真实 LLM Benchmark Bug Fix 0% (25/27 空响应 — deepseek 瓶颈)
  组织级 Workflow: "目标→CEO→产品→架构→开发→测试→部署→运营" 全链未打通
  Monitoring/Config UI: 无实时监控面板/无配置中心界面
  Skill/MCP/Domain Intelligence: 未形成
  多行业工厂: 只有 software_company 模板
```

## 2. 当前真实架构图

```
Desktop (Tauri launcher)
  ↓
Runtime (Managed Services + Command)
  ↓
Console UI (7 只读页面: Dashboard/Projects/Lifecycle/Intelligence/Approval/Decisions/Providers)
  ↓
factory-org (Company/Department/Role/Employee/Authority/Knowledge + software_company 模板)
  ↓
factory-exec (Developer Agent: Context→Ranking→Progressive→Budget→LLM→Patch→Evaluator→Experience)
  ↓
factory-core (冻结原语: events/tasks/workflows/approval/intelligence/metrics/agents/skills)
```

## 3. 与 AI Company OS 定位差距（核心）

```
定位: 创建/管理/运行/进化 AI 公司 (多行业工厂)
当前: 强大的"软件生产管理平台" + 组织建模 + 单一 Developer Agent 执行工程

差距清单 (按严重度):
  1. 组织 vs 执行未连接: org 能建模, 但"给公司一个目标→自动组织多员工协作"没有
     (Workflow 是任务级, 非组织级; 员工不会"接力"干活)
  2. 单员工 vs 多员工: 只有 Developer Agent; 产品/架构/测试/运营员工是模型, 无执行
  3. 生产未闭环: LLM 瓶颈导致真实代码产出 0% (工程再完善也无法兑现产品价值)
  4. UI 是"管理台"不是"工作台": 无 Workspace/组织可视化/工作流看板/监控/配置
  5. 多行业: 只有软件; 电商/自媒体/数据分析/办公自动化工厂 = 0
  6. Skill/MCP/Domain Intelligence: 未整合 (有 agents/skills 基础, 无 MCP, 无领域智能)
```

## 4. 已完成能力（真实）

```
✅ 组织建模 (Company/Department/Role/Employee/Authority/Knowledge + Default Deny)
✅ 生命周期管理 (Idea→PRD→Approval→Task)
✅ Intelligence (决策四因素/推荐/经验五域/风险分级)
✅ Context 智能 (Ranking Top-K/Progressive 3 阶段/Budget 4 类型/Experience 反馈)
✅ Execution 可靠性 (Multi Run N=3/Evaluator 5 层/Capability Registry)
✅ Runtime/Desktop/分发 (dmg)
✅ 开源发布 (Apache-2.0, README, 文档体系 119 份)
```

## 5. 缺失能力（诚实清单）

```
❌ 组织级 Workflow 引擎 (多员工接力: 目标→部门间协作→交付)
❌ 产品/架构/测试/运营 Agent 执行 (只有 Developer)
❌ 真实生产闭环 (换模型前 Bug Fix 0%)
❌ Monitoring Dashboard (Agent 状态/Token/成本/成功率实时)
❌ Configuration Center (Provider/Skill/MCP/Knowledge/Workflow 模板管理 UI)
❌ Workspace/Organization UI (可视化公司/部门/员工/状态)
❌ Workflow UI (任务流看板: 当前节点/负责人/ETA)
❌ Skill 生命周期 + MCP 管理 (有 CLI 基础, 无整合)
❌ AI Domain Intelligence (Skill+MCP+Knowledge+Workflow+Eval+Learning 形成专家工厂)
❌ 多行业模板 (电商/自媒体/数据分析/办公自动化)
❌ 员工级记忆/评估/学习闭环 (Experience 有, 未绑定员工绩效/培养)
```

## 6. 架构调整建议

```
A. 模型层 (优先, 阻塞一切):
   换 Provider: Ollama 本地 qwen3:8b (非 reasoning, 零成本) 或 DeepSeek 非 reasoning
   → 真实生产闭环 (Bug Fix >0%) 是产品存在的前提

B. 组织-执行连接层 (下一步工程):
   org 与 exec 打通: Employee → 任务分配 (Registry 只推荐 → 自动分配+审批)
   → 多角色员工注册 (产品/架构/测试/运营 Agent 用同一 exec 引擎)

C. UI 层 (产品化):
   Workspace (项目/公司/行业) → Organization 可视化 → Workflow 看板 → Monitoring

D. 领域层 (远期):
   Skill Registry + MCP + Knowledge 整合 → 多行业模板 (电商/自媒体/数据分析)
```

## 7. 下一阶段 Roadmap（调整建议）

```
Sprint 6: 模型换档 + 生产闭环 (Ollama qwen3:8b 跑 9 样本, 恢复 Bug Fix ≥60%)
Sprint 7: 组织-执行连接 (Employee 自动分配 + 多角色员工)
Sprint 8: 产品 UI (Workspace/Organization/Workflow/Monitoring)
Sprint 9+: Skill/MCP/Domain Intelligence → 多行业模板
```

## 8. 文档一致性检查

| 文档 | 当前状态 | 是否需要更新 |
|---|---|---|
| vision.md | 定位 AI Enterprise OS (超前于实现) | ✅ 更新为诚实分层 (愿景/已实现/进行中) |
| architecture/roadmap.md | Phase 15-21 规划 (与 Sprint 体系并行) | ✅ 合并/对齐 Sprint 体系 |
| ai-enterprise-operating-system-reference.md | 参考架构 (仍准确) | 微调 (标注未实现层) |
| sprint 文档 (T5.x) | 最新 | ✅ 保留 |
| product-proof-report.md | 真实 Benchmark 数据 | ✅ 追加 Sprint 5 V3 |
| README.md | v1.0 发布版 | ✅ 更新当前状态 |

## 9. 外部工具原则检查

```
✅ 符合: 无外部工具是完成任务的必要条件
  (UI 原生 HTML/JS 生成, Desktop 自研 Tauri, Provider 可替换)
⚠️ 注意: 真实 LLM 目前依赖 DeepSeek API (外部) — 但 Ollama 本地已就绪 (消除依赖)
✅ Hermes/子代理用于开发流程 (不是产品依赖)
```

## 10. 结论（诚实）

```
方向: 定位正确 (AI Company OS), 组织模型实现正确 (Company→Department→Role→Employee)
偏差: 执行层只有单一 Developer Agent + 模型瓶颈 (Bug Fix 0%) + UI 是管理台非工作台
   + 组织-执行未连接 + 多行业未开始

一句话: 架构蓝图 (16A-20) 与实现 (Sprint 1-5) 都是"正确的一半" —
  组织建模 ✅ / 执行工程 ✅, 但两者未连接, 且模型瓶颈阻塞真实生产。

下一步最高优先: 换模型 (Ollama 本地) → 恢复真实生产 → 连接组织与执行
```

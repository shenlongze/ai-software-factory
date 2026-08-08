# AI Factory — Alignment Audit（架构重新校准）

> 日期: 2026-08-08 | 状态: 审计完成（以代码实际为准）
> 扫描: HEAD=a93ff8d | pytest 5493 | 只更新 docs, 代码零修改

## 0. 战略重新确认

```
AI Software Factory 定位: AI Company OS
一句话: LangChain 创建 AI 员工, LangGraph 编排 AI 工作流,
        AI Software Factory 建立、管理、治理和扩展 AI 生产组织。

AI Factory = "造专家的工厂", 不是一个专家。
```

## 1. 当前实现与战略目标差距

| 维度 | 战略目标 | 当前实现 | 差距 |
|---|---|---|---|
| 入口 | Workspace (用户无需理解 Company) | Company 强制根 | 🔴 Workspace 缺失 |
| 组织 | Organization 不绑定 Company (Software/E-commerce/Media/Personal Studio) | Company 绑定 (12 处) | 🟡 概念绑定 |
| 员工 | Employee 是执行实体 (Identity/Role/Skill/Knowledge/Memory/Capability/Model) | Employee 有 Role/Capability/experience_ref | 🟡 部分 (无 Model/Memory 绑定) |
| 执行连接 | Employee→Workflow→Task→Execution | agent_runtime 有 employee_id 参数 (松散) | 🟡 未形式化 |
| UI | 工作台 (Workspace/Org/Employee/Workflow/Monitoring/Config) | 7 页面管理台 (Dashboard/Projects/Lifecycle/Intelligence/Approval/Decisions/Providers) | 🔴 管理后台非工作台 |
| 多行业 | 6+ 工厂类型 | 只有 software_company 模板 | 🔴 未开始 |
| Skill/MCP | Domain Intelligence | 无整合 (agents/skills CLI 基础) | 🔴 未形成 |

## 2. 已完成能力（真实）

```
✅ 组织建模: Company/Department/Role/Employee/Authority/Knowledge (org 8 类)
✅ Default Deny 权限 (Role 绑定)
✅ 生命周期 (Idea→PRD→Approval→Task)
✅ Context 智能 (Ranking/Progressive/Budget/Experience)
✅ Execution 可靠性 (Multi Run/Evaluator/Capability Registry)
✅ Runtime + Desktop + Console (管理台)
✅ 5493 tests | 158 events | 35+ ADR | 119 docs
```

## 3. 缺失能力（诚实清单）

```
❌ Workspace 层 (用户入口: 项目/公司/行业)
❌ Organization 抽象 (解绑 Company; 未来 Software/E-commerce/Media/Data/Personal/Research)
❌ Employee 完整执行实体 (Model/Memory/Workflow 绑定)
❌ 组织级 Workflow (多员工接力: 目标→部门协作→交付)
❌ Employee→Task 自动分配 (Registry 只推荐, 未分配)
❌ 多角色员工执行 (产品/架构/测试/运营 Agent 只有 Developer)
❌ 工作台 UI (Workspace/Org/Employee/Workflow/Monitoring/Config 6 视图)
❌ Monitoring (实时 Agent 状态/Token/成本/成功率)
❌ Skill/MCP/Domain Intelligence
❌ 多行业模板 (6+ 工厂)
```

## 4. 组织模型对齐评估（factory-org）

```
当前: Company(root)→Department→Role→Employee (Company 强制)
目标: Workspace(root)→Organization(可选)→Department(可选)→Role→Employee

差异:
  - 缺 Workspace 根 (项目/公司/行业容器)
  - Organization 绑定 Company 类型 (需泛化: type 可配 software/ecommerce/media/data/personal/research)

迁移方案 (禁止直接改, 建议 Sprint 7):
  ① 新增 Workspace 模型 (根容器: name/projects/organizations)
  ② Company → Organization 泛化 (type 字段替代硬编码 company; 兼容旧数据)
  ③ 保持 Department/Role/Employee 不变 (已正确)
  兼容: org.company.* 事件 → org.organization.* (或双命名过渡)
  影响: 12 处 Company 引用 → Organization (org 内部 + CLI + Console)
```

## 5. 执行模型连接评估

```
当前链: Task → DeveloperAgent (employee_id 松散传入)
目标链: Employee → Workflow → Task → Execution Engine

现状:
  ✅ Execution Engine 完整 (Context/Ranking/Progressive/Budget/Experience/MultiRun/Evaluator)
  🟡 employee_id 已传 (agent_runtime 参数) 但未形式化 (无 Employee→Workflow→Task 编排)
  ❌ 无 Workflow 引擎 (多员工接力)
  ❌ 无 Employee→Task 自动分配

连接方案 (Sprint 7):
  Employee.execution_profile (绑定 Agent 实例 + Capability + 偏好 Provider)
  → 任务分配器 (Registry 推荐 + Approval 确认 → 分配)
  → Workflow 编排 (阶段: 产品→架构→开发→测试→运营, 每步分配对应角色员工)
```

## 6. UI 产品模型（工作台 vs 管理后台）

```
当前: 管理后台 (7 只读页面) — 展示生命周期/审批/决策/Provider
目标: AI Factory 工作台 (6 视图):

① Workspace Dashboard: 项目/组织/员工/任务/状态 (根入口)
② Organization View: 组织结构可视化 (Org→Dept→Role→Employee)
③ Employee View: 谁/负责什么/当前任务/能力/历史表现
④ Workflow View: 流程节点 (需求→设计→开发→测试→发布), 当前节点/负责人/ETA
⑤ Monitoring View: 实时 (谁在工作/做什么/完成%/ETA/Token/成本/错误)
⑥ Configuration Center: LLM/Skill/MCP/Knowledge/Workflow 管理

原则: 外部工具 (Figma/MCP/OpenClaw) 只增强不阻塞 (默认 HTML/JS 原生)
```

## 7. 多行业扩展评估

```
当前架构是否支持 6+ 工厂: 🟡 部分支持 (需验证)
  支持: 组织模板声明式 (templates.py) — 可加 ecommerce/media/data 模板
  缺: 行业 Workflow 模板 + 行业 Skill/Knowledge + 行业员工角色集

行业模板 = Organization + Workflow + Role + Skill + Knowledge (声明式组合)
Software = 第一个实例 (已验证); 其余 5 个 = 同构扩展 (Sprint 9+)
```

## 8. 文档一致性检查

| 文档 | 状态 | 更新 |
|---|---|---|
| vision.md | 定位超前 | ✅ 更新为分层 (愿景/已实现/进行中) |
| ai-enterprise-operating-model.md | Company 引用 ×3 | ✅ 对齐 Workspace/Organization |
| roadmap.md | Phase 15-21 | ✅ 对齐 Sprint 体系 |
| ai-factory-strategic-audit.md | 刚产出 | 保留 (基准) |
| sprint docs | 最新 | 保留 |

## 9. 架构调整建议

```
A. 模型层 (已冻结不动, 只记录迁移方案): org Company→Organization 泛化 + Workspace 新增
B. 连接层 (Sprint 7): Employee→Workflow→Task→Execution 形式化 + 多角色员工
C. UI 层 (Sprint 8): 管理台 → 工作台 (6 视图)
D. 领域层 (Sprint 9+): Skill/MCP/Domain Intelligence + 多行业模板
E. 模型瓶颈 (Sprint 6 独立): Ollama 本地换档, 恢复真实生产
```

## 10. 后续 Sprint 路线（重新规划, 非 Sprint 6 直进）

```
Sprint 6: 模型换档 + 生产闭环     (Ollama qwen3:8b 跑 9 样本, Bug Fix ≥60%)
Sprint 7: 组织-执行连接           (Workspace 新增 + Organization 泛化 + Employee→Task 分配)
Sprint 8: Workflow Engine         (多员工接力编排 + Workflow UI)
Sprint 9: 工作台 UI              (Workspace/Org/Employee/Monitoring/Config)
Sprint 10: Skill/MCP + Domain Intelligence (专家工厂)
Sprint 11+: 多行业模板 (E-commerce/Media/Data/Office 工厂)

依赖: 6 独立 (模型) → 7/8 连接 (组织+流程) → 9 UI → 10/11 领域
```

## 11. 结论

```
战略方向正确 (AI Company OS / 造专家的工厂)
核心差距: Workspace/Organization 泛化 (模型层) + 组织-执行连接 (流程层)
          + 工作台 UI (产品层) + 多行业 (领域层) + 模型瓶颈 (阻塞层)

优先级裁决: 模型瓶颈 (Sprint 6) → 组织连接 (7) → 工作流 (8) → UI (9) → 领域 (10+)
等待开发指令
```

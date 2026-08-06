# AI Software Factory — Vision

> 日期: 2026-08-07 | 状态: v4.0 (Architecture Re-alignment)
> 前置: Phase 1-14B + 15A-1 完成 (v1.0.0-rc1, 4217 tests, Core 冻结)

## 终极定位

AI Software Factory 不只是 AI 软件开发工具。

**AI Organization Factory** — 一个可以构建、运行、管理 AI 企业组织的操作系统。

终局形态：**AI Global Enterprise Operating System** — 支持创建 AI 公司、AI 部门、AI 团队、AI 专业员工。

```
Human Leadership
  ↓
AI Executive Layer
  ↓
AI Department
  ↓
AI Professional Agents
  ↓
Workflow Execution
  ↓
Experience Learning
```

## 核心理念（映射现有能力）

| 理念 | 含义 | 现有基础 | 未来 |
|:-----|:-----|:---------|:-----|
| 1. 专业的人干专业的事 | Role + Capability + Experience + Responsibility | Agent/Provider 选择 (8A-10A) | Organization Engine (16) |
| 2. 效率 | Planning Intelligence + Parallel Execution + Optimization | Task/Workflow/Assignment | Planning Intelligence (17) |
| 3. 流程 | Industry Workflow + PM 方法论 + Lifecycle Engine | Product Lifecycle (9d) | Industry Templates (20) |
| 4. 透明 | Event + Artifact + Decision Evidence + Audit | 137 EventType + Evidence | Governance Audit (19) |
| 5. 可控 | Permission + Approval + Policy + Governance | Approval Gate (9c) + Risk (10A-2) | Security & Governance (19) |

## Agent 是什么？

**Agent 不是 prompt。Agent 是专业 AI 员工（角色化，非万能）。**

```
专业 AI 员工 = Identity (职位) + Responsibility (职责) + Capability (能力)
             + Knowledge (知识) + Authority (权限) + Experience (履历) + Performance (绩效)
```

- 有职位（CEO/Product/PM/Architect/Developer/QA/Review — 不同专业不同员工）
- 有能力但**能力 != 角色**：每岗位只配岗位所需能力（禁超级 Agent）
- 有工作经验（ExperienceRecord 五域）
- 有职责边界（Authority 矩阵，默认 deny）
- 行为可审计（做了什么/为什么/进度/Token/成本/结果）

Factory 不实现 Agent 能力，Factory 管理 Agent（雇佣、分配、考核、解雇）。
分析岗（Analysis Agent）与管理岗（Project Manager Agent）是不同职业：分析提供事实和建议，经理组织执行。

## Human 与 AI 的关系

```
AI: 分析 / 推荐 / 执行 / 汇报
Human: 授权 / 批准 / 负责 / 决策
```

Human Leadership → AI 组织 → Human 最终负责（Approval Gate 铁律）。

## 成功标准

```
1. 一个用户 + Factory = 一家 AI 公司 (所有专业角色 AI 化, 人只决策)
2. 项目管理智能化 (17 Planning: 拆解/调度/风险/重规划)
3. 行业可扩展 (20 模板: 软件/金融/制造/电商/医疗/媒体)
4. 透明可控 (19 治理: 一切可见, 高危必经人)
5. 经验是资产 (Experience Loop: 每次执行都让组织更聪明)
```

## Desktop 定位 (15A-3b)

**Desktop = AI Organization Factory Application Entry (入口层), 不是业务系统。**

- Launcher UI (原生 JS 内嵌): Factory Header → Workspace Area (预留 CEO/
  Manager/Employee/Approval/Knowledge, Phase 16+) → System Status (底层状态,
  非首页唯一内容) → Log Viewer (Troubleshooting) → System Recovery。
- 业务 (创建公司/部门/员工/审批/知识) 全部由未来 Organization/Intelligence/
  Extension 层经 Runtime 提供; Desktop 无任何 business command, 不保存
  Company/Agent/Knowledge 数据 (数据全部在 `<data_root>`, 未来公司隔离经
  Runtime/Organization Layer)。
- 错误用用户语言 ("Factory startup failed: <原因>"), 禁暴露技术细节。
- 详见 [docs/architecture/desktop-product-entry.md](./architecture/desktop-product-entry.md)。

# AI Software Factory — Architecture Freeze Report

> 日期: 2026-08-06 | 状态: 冻结审查完成, 等待确认
> 前置: 20 Phase (2159 tests), 产品定位升级为 AI 工作生命周期管理平台

## 一、核心边界（最终确认）

### Factory Core（必须保持 — 通用原语）

| 能力 | 说明 |
|:-----|:-----|
| 状态管理 | Task/Workflow/Agent/Assignment/Execution 状态机 |
| 生命周期 | Workflow 引擎 + 状态转换 + 恢复 |
| 调度 | Orchestration + Assignment (Agent 匹配) |
| 执行抽象 | RuntimeAdapter 接口 (不实现具体) |
| 事件审计 | Event Logger = 唯一事实源 |
| 恢复 | Checkpoint + Event Replay |
| 观测基础 | Dashboard/Metrics 只读聚合 (基于 Event) |
| 组织 | Workspace/Project 分层 |

### 不能进 Core（全部 Extension）

| 领域 | 类型 | 接入方式 |
|:-----|:-----|:---------|
| Git / GitHub | Integration | Skill / MCP |
| Jira / Figma / AWS / Database | 外部工具 | MCP |
| Market Research / UI Generation / Office / SEO | 能力 | Skill |
| Monitoring / Incident | 运营 | Operations Layer |
| 具体 LLM (OpenAI/Claude/Local) | 模型来源 | Provider |

**边界原则**: Core = 通用原语 (状态/流程/事件/验证/抽象); Extension = 领域能力 (经 Skill/MCP/Runtime/Provider 声明式注册接入)。**Core 零领域依赖**。

## 二、最终 Extension Model

```
Agent (角色配置实例)
  ├── Skills     能力声明   (flutter-development / market-analysis / excel-report / seo)
  ├── MCP Tools  外部工具   (GitHub / Jira / Figma / AWS / Google Drive)
  └── Runtime    执行方式   (Hermes CLI / Codex CLI / Claude API / Local Model)
        └── Provider      LLM 来源 (OpenAI API / Anthropic / Local)
```

- Skill 独立于 Agent（SkillRegistry 已有）; Agent = 角色 + skill 集 + MCP 工具集 + runtime 偏好
- Runtime = 执行器; Provider = LLM 来源（Runtime 可对接多 Provider）
- **新增任何能力不修改 Core**: OpenClaw skill / Codex plugin / MCP server / 第三方 Agent = 声明式注册（JSON）

## 三、Event 唯一事实源确认 + Namespace

**确认: 未来所有层都产生 Event。**

```
现有 namespace:
  task.* / workflow.* / agent.* / assignment.* / execution.* / runtime.* / validation.*
  recovery.* / dashboard.* / metrics.* / workspace.* / project.* / git.* / change.* / system.*

未来扩展 (按 domain):
  idea.*          idea.created / idea.refined
  research.*      research.completed / market.analyzed / competitor.analyzed
  prd.*           prd.generated / prd.approved / prd.rejected
  ui.*            ui.generated / ui.reviewed / ui.approved
  deployment.*    deployment.started / deployment.completed
  incident.*      incident.created / incident.resolved
  approval.*      approval.required / approval.granted / approval.denied
```

原则: EventType 枚举扩展 (ADR-0002 路径, 加成员不改表); 未来层复用 Core Event Logger。

## 四、Human Approval Gate 模型

```
ApprovalGate = { phase, required: mandatory|recommended|optional, approver, evidence, status: pending|approved|denied }
```

| 节点 | 级别 | 说明 |
|:-----|:----:|:-----|
| Idea | optional | 想法收集可自动 |
| PRD | **mandatory** | 产品方向确认 |
| UI Design | **mandatory** | 视觉方向确认 |
| Architecture | recommended | 大重构必须, 小改动可选 |
| Code | optional | AI 自主, 人工抽查 |
| Deploy | **mandatory** | 发布授权 |
| Incident | optional | 告警自动, 重大事故人工 |

实现: Approval 为 Gate 原语 (pending→approved/denied→Event); CLI validate 退出码语义 + Web UI 审核台 (Phase 11)。

## 五、Phase 7-11 路线评估

**合理, 建议微调 (排序保持, 标注并行性):**

| Phase | 方向 | 评估 |
|:-----:|:-----|:-----|
| 7 | Project Understanding | ✅ 优先 (任意阶段接入的基础) |
| 8 | LLM Provider | ✅ 独立性强, 可并行 |
| 9 | Product Intelligence | ✅ 依赖 Phase 7 理解能力 |
| 10 | Operations | ✅ 依赖部署/Provider |
| 11 | Approval Console | ✅ 核心价值; **建议可并行启动** (审核需求全程存在) |

**结论: 排序合理。Phase 11 标注"可并行"。**

## 六、文档变更计划

新增:
- docs/core-boundary.md — 核心边界 (Core vs Extension 最终清单 + 原则)
- docs/extension-model.md — 扩展体系 (Skill/MCP/Runtime/Provider 注册模型 + 未来扩展点)
- docs/agent-skill-runtime-model.md — Agent/Skill/Runtime/Provider 关系
- docs/approval-model.md — Approval Gate 模型 (节点表 + 实现方向)

更新:
- README.md / architecture-overview.md / roadmap.md (Core/Extension/Human Layer 三区划分)

## 七、冻结结论

架构**冻结有效, 无需重构**。Core 边界清晰, 扩展体系完整, Event 唯一事实源确认, Approval Gate 模型就绪。冻结后: 不修改 Core 行为; 新能力一律走 Extension 注册。

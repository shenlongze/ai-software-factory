# Phase 9 Plan — Product Intelligence Layer

> 日期: 2026-08-06 | 状态: 架构设计评审, 待确认
> 冻结约束: Core 零修改 / Extension 独立 / Event 唯一事实源 / Approval Gate / Provider Intelligence 利用

## 0. 定位

**不是 PRD 生成工具。** 是 AI 驱动的软件生命周期管理: 从 Goal/Idea 到 Research/PRD/UI/Architecture/Task/Development 的完整产品链路, 关键决策人工批准。

## 1. 架构图

```
┌─ factory-core/product/ (新 Extension, 独立) ─────────────────────┐
│                                                                  │
│  Idea ──→ Research ──→ PRD ──[GATE]──→ UI ──[GATE]──→ Architecture ──→ Task → Development
│   │          │          │    mandatory       │    mandatory    (recommended)   │
│   │          │          │                    │                                 │
│   Event: idea.*  research.*  prd.*  approval.*  ui.*  architecture.*  product.* │
└────────────────────────────┬────────────────────────────────────────────────────┘
                             │ 复用 (只读调用, 零修改)
        ┌────────────────────┼──────────────────────────┐
   EventLogger          ProviderRegistry           Task/Workflow Core
   (唯一事实源)        + CostAwareSelector         (task.create → workflow run)
                        (Provider Intelligence)
```

## 2. 数据模型

```python
class ProductIdea(Pydantic):
    id: str; title: str; description: str
    goals: list[str]; context: dict
    status: str            # created/refined/approved/archived
    created_at: str

class ResearchArtifact(Pydantic):
    id: str; idea_id: str
    market_summary: str
    competitor_analysis: dict      # competitor → insights
    opportunity: str; risks: list[str]
    evidence: list[str]            # 来源 (Provider 产出证据)
    provider_id: str | None        # 生成来源
    status: str                    # pending/completed/failed

class PrdArtifact(Pydantic):
    id: str; idea_id: str; research_id: str | None
    sections: dict                 # problem/goals/users/features/non_goals/success_metrics/ac
    approval: ApprovalRecord | None
    provider_id: str | None
    status: str

class UiArtifact(Pydantic):
    id: str; prd_id: str
    direction: str; flow: list[str]; prototype_ref: str | None
    approval: ApprovalRecord | None
    status: str

class ApprovalRecord(Pydantic):
    gate: str                      # prd/ui/architecture
    status: str                    # pending/approved/denied
    approved_by: str | None
    comment: str | None
    decided_at: str | None

class ProductWorkflow(Pydantic):
    id: str; idea_id: str
    stages: list[str]              # [research, prd, ui, architecture, tasks]
    current_stage: str
    status: str                    # running/awaiting_approval/completed/failed
```

## 3. Event Namespace

```
idea.*            idea.created / idea.updated / idea.archived
research.*        research.started / research.completed / research.failed
prd.*             prd.generated / prd.approved / prd.rejected / prd.updated
ui.*              ui.generated / ui.approved / ui.rejected
architecture.*    architecture.proposed / architecture.approved
product.*         product.workflow.started / product.workflow.stage.completed / product.workflow.completed
approval.*        approval.required / approval.granted / approval.denied
(provider 生成时复用 provider.selected / provider.usage.recorded — Provider Intelligence 闭环)
```

## 4. Approval Gate 设计

```
Gate 定义: {phase: prd|ui|architecture, required: mandatory|recommended}
Flow: artifact 生成 → approval.required (workflow 进入 awaiting_approval)
      → 人工 decide (CLI approve/deny; 未来 Web UI) → approval.granted/denied
      → granted: 推进下一阶段; denied: 回退重生成 (记录 comment)
PRD/UI = mandatory (阻塞推进); Architecture = recommended (可跳过, 记录)
未批准时 workflow 暂停 (不自动推进)
```

## 5. Extension 边界

```
factory-core/product/
├── models.py        Idea/Research/PRD/UI/Architecture Artifact + ApprovalRecord + ProductWorkflow
├── service.py       ProductService (idea/research/prd/ui/workflow/approve 编排)
├── providers.py     ProductProvider 接入 (经 ProviderAdapter + CostAwareSelector 生成 artifacts)
├── store.py         独立数据空间 .factory/product/ (artifacts.json/ideas.json/workflows.json)
├── events.py        product 事件辅助
└── __init__.py
复用 (只读): EventLogger / ProviderRegistry + CostAwareSelector / Task/Workflow Core / Validation
禁止: 修改 Core 任何模块
```

## 6. CLI 规划

```
factory product idea create --title "..." --description "..."
factory product research run <idea_id>            # 经 Provider 生成 Research
factory product prd generate <idea_id>            # 经 Provider 生成 PRD
factory product prd approve|reject <id> [--comment]
factory product ui generate <prd_id>
factory product workflow start <idea_id>          # 启动产品流程
factory product workflow status <idea_id>         # 当前阶段/待批准
factory approval list [--pending]                 # 待批准清单
factory approval decide <approval_id> approve|deny [--comment]
```

## 7. Dashboard 规划

```
Product View (19 视图): Idea 列表 + 阶段进度 (Research/PRD/UI/Architecture/Tasks)
+ Approval 待办 (pending gates) + Provider 生成来源
默认关零回归
```

## 8. Provider/Agent 调度关系

```
产品阶段 (Idea→UI): TaskRequirement (task_type=research/prd/ui, required_capabilities) 
  → CostAwareSelector.recommend → provider (Provider Intelligence: 能力+成本+表现)
  → ProviderAdapter.generate → artifact + provider.usage.recorded (经验积累)
开发阶段 (Tasks): Task → Agent (Assignment) → Runtime → Provider (8B-1 runtime_preferences 链)
产品阶段无人 Agent (AI 生成 artifact); 开发阶段有人 Agent (执行任务)
```

## 9. 分阶段实施计划

```
9a: product 基础 — 模型 + store + Event + CLI (idea/artifact CRUD + workflow 骨架)     [+~60 tests]
9b: Provider 生成 — ProductProvider 接入 (research/prd/ui 经 ProviderAdapter + usage) [+~80 tests]
9c: Approval Flow — Gate + approve/deny + workflow 暂停/恢复 + approval.* 事件       [+~80 tests]
9d: Product Workflow 编排 — stages 推进 + task.create 衔接开发 + Dashboard Product View [+~60 tests]
```

## 10. 确认要点

1. ✅ Core 冻结 (product/ 纯新增)
2. ✅ Extension 独立 (独立数据空间 + 独立测试)
3. ✅ Event 唯一事实源 (product/approval namespace)
4. ✅ Approval Gate (PRD/UI mandatory, Architecture recommended)
5. ✅ Provider Intelligence 利用 (CostAwareSelector + usage 闭环)
6. ✅ Agent 自动选择 Provider (TaskRequirement → recommend; 开发阶段 8B-1 链)
7. ✅ 不是 PRD 生成工具 (生命周期管理)
8. ✅ 分阶段实施 (9a→9b→9c→9d)

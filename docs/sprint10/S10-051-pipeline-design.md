# S10-051 — AI Software Factory Pipeline 设计

> 日期:2026-08-15 | Sprint: S10-051 | Phase 0 分析 + Phase 1-7 设计

---

## 1. Phase 0 — 内部分析

### 复用点(S10-050)
```
product.py      ProductIntent (to_dict/from_dict/to_summary/to_json, status: draft→project_created)
actions.py      create_product (projects/<slug>/product.json 落盘, status=project_created)
conversation.py ConversationState (DISCOVERY/PRODUCT_CONFIRMATION/PROJECT_CREATION/DONE)
actions.py      select_agent (S10-049: 前端→flutter-dev/默认 backend-1)
router.py       IntentRouter (声明式映射)
audit.py        record_execution
```

### 当前缺口
```
G1: 无 PRD 生成 (ProductIntent → PRD.md)
G2: 无 EngineeringPlan (PRD → engineering.json)
G3: 无 Task Tree (工程计划 → tasks.json)
G4: 无 Agent Assignment (task → execution_plan.json)
G5: 无 Project Lifecycle (IDEA→...→DELIVERED)
G6: 无 prepare_project 高级 Action (一次完成全部)
G7: Conversation 在 PROJECT_CREATION 后直接 DONE (无"是否生成工程计划"引导)
```

### S10-051 最小范围
```
P0: ProductDocument → PRD.md (规则生成)
P1: EngineeringPlan → engineering.json (规则生成: architecture/modules/technical_tasks)
P2: Task Tree → tasks.json (Epic/Task/Priority/Agent Type)
P3: Agent Assignment → execution_plan.json (复用 select_agent)
P4: Lifecycle 状态 (project.json status 扩展)
P5: prepare_project Action (一次完成 P0-P4, 走确认门)
P6: Conversation 集成 ("产品定义完成, 是否生成工程计划?")
```

---

## 2. Pipeline 架构

```
User: "我想开发一个台球比赛计分APP"
    ↓
[Discovery] → ProductIntent (problem/user/core_features)
    ↓
[Product Confirmation] → y
    ↓
[create_product] → projects/<slug>/product.json (status: project_created)
    ↓
AI: "产品定义完成, 是否生成工程计划?"
    ↓
User: "准备开发" → prepare_project intent
    ↓
[ConfirmationGate] → y (敏感 action)
    ↓
[prepare_project action]
    ├─ generate_prd     → PRD.md (Product Overview/Problem/Target User/Core Features/Usage Scenario/Future)
    ├─ engineering_plan → engineering.json (architecture/modules/technical_tasks)
    ├─ task_tree        → tasks.json (Epic/Task/Priority/Agent Type)
    ├─ agent_assignment → execution_plan.json (task_id → agent, 复用 select_agent)
    └─ lifecycle        → project.json status: EXECUTION_READY
    ↓
"Project Ready For Engineering."
```

## 3. 资产文件(projects/<slug>/)

| 文件 | 内容 | 生成 |
|---|---|---|
| product.json | ProductIntent (S10-050 已有) | create_product |
| PRD.md | 产品需求文档 | generate_prd |
| engineering.json | 架构/模块/技术任务 | engineering_plan |
| tasks.json | Epic/Task/Priority/Agent Type | task_tree |
| execution_plan.json | task_id → agent | agent_assignment |
| project.json | 生命周期状态 | prepare_project |

## 4. 规则生成(不过度智能, 支持未来 LLM)

### PRD.md(ProductDocument)
```
基于 ProductIntent 字段 + platform 推导:
- Product Overview: name + platform
- Problem: problem
- Target User: user
- Core Features: core_features (列表)
- Usage Scenario: platform + features 组合描述
- Future Direction: 占位 (LLM 未来增强)
```

### EngineeringPlan
```
architecture: 规则推导 (platform=mobile → "Flutter + Backend API"; web → "Web Frontend + Backend API"; desktop → "Desktop App + Backend API")
modules: core_features → 模块名 (slug)
technical_tasks: 基础任务 (database schema/backend api/frontend page/test)
```

### Task Tree
```
每个 module 生成 Epic:
  Epic: <module> 系统
  Tasks: database schema / backend api / frontend page / test (priority: P0/P1)
  Agent Type: backend/frontend/qa (规则映射)
```

### Agent Assignment
```
task.agent_type → select_agent:
  frontend → flutter-dev
  backend → backend-1
  qa → qa-agent (若存在, 否则 backend-1)
```

### Lifecycle
```
IDEA → PRODUCT_DEFINED (create_product) → ENGINEERING_READY (PRD+plan) → EXECUTION_READY (tasks+execution_plan) → DEVELOPMENT → TESTING → DELIVERED
prepare_project 后状态: EXECUTION_READY
```

## 5. Action 注册

```
generate_prd        (name=generate_prd, sensitive=False, category=product)
prepare_project     (name=prepare_project, sensitive=True, category=product) — 高级组合 Action
```

## 6. Conversation 集成

```
handle_product_confirm y → PROJECT_CREATION → 创建成功后:
  state → DONE 前: 返回 "产品定义完成 — 是否生成工程计划? 输入 '准备开发' 或 '生成工程计划'"
prepare_project intent 关键词: "准备开发" / "生成工程计划" / "生成PRD" / "工程计划"
```

## 7. 架构符合性

| 原则 | 符合 |
|---|---|
| 复用已有系统 | ✅ ProductIntent/select_agent/ActionRegistry/Router |
| 不生成代码 | ✅ 只规划 (PRD/计划/任务/分配) |
| 输出落盘为资产 | ✅ projects/<slug>/ 全部文件 |
| 走 Intent/Action/Service | ✅ prepare_project → 各子 Action |
| 长期方向 | ✅ Idea→Product→Engineering→Execution Ready |

---

## 8. 文件计划

```
factory-console/session/
  pipeline.py       (新增: ProductDocument/EngineeringPlan/TaskTree/AgentAssignment/Lifecycle + 规则生成)
  actions.py        (修改: +generate_prd +prepare_project)
  intent.py         (修改: +prepare_project 关键词)
  router.py         (修改: prepare_project 映射)
  conversation.py   (修改: PROJECT_CREATION 后引导)
  context.py        (修改: +project_status 或复用 metadata — 最小)
tests/console/
  test_session_pipeline.py (新增, >=50 测试)
docs/sprint10/S10-051-software-factory-pipeline.md (Phase 10)
```

> Phase 1-7 设计完毕 | 规则生成 (未来 LLM 可替换) | 全资产落盘 | prepare_project 组合 Action

# AI Software Factory — Planning Intelligence

> 日期: 2026-08-07 | 状态: 设计 (Phase 17 实现)
> 定位: AI Project Manager — 分析目标/创建计划/管理进度/动态重规划

## 核心能力

```
1. Task Decomposition     目标 → 任务图 (Task Graph)
2. Dependency Graph       依赖关系 (前置/并行/关键路径)
3. Scheduling             调度 (Scrum/Kanban/Waterfall/Hybrid/MVP 模式)
4. Critical Path          关键路径计算 (瓶颈识别)
5. Parallel Optimization  并行优化 (无依赖任务并行执行)
6. Dynamic Replanning     进度监控 → 风险发现 → 重新规划
```

## 项目管理方法论支持

```
Scrum:     Sprint 拆解 / Backlog / 迭代计划 / 燃尽
Kanban:    列状态流转 (To Do/In Progress/Review/Done) / WIP 限制
Waterfall: 阶段串行 (需求→设计→开发→测试→上线) / 里程碑
Hybrid:    阶段框架 + 迭代执行
MVP:       最小可行 → 快迭代 (范围裁剪优先)
```

## 数据模型

```python
class TaskGraph(Pydantic):
    id/goal_id
    nodes: list[PlanNode]      # 任务节点
    edges: list[PlanEdge]      # 依赖边 (from→to)
    mode: str                  # scrum|kanban|waterfall|hybrid|mvp
    critical_path: list[str]   # 关键路径节点

class PlanNode(Pydantic):
    id/title/description
    role_required: str         # 需要哪个角色 (Organization Model)
    capabilities: list[str]    # 需要哪些能力
    estimated_cost: float
    depends_on: list[str]      # 前置节点
    status: pending|active|blocked|done|failed
    assigned_agent_id: str | None

class Schedule(Pydantic):
    graph_id
    parallel_groups: list[list[str]]   # 可并行组
    order: list[str]                  # 拓扑序
    risks: list[PlanRisk]             # 风险 (延误/依赖/资源)

class PlanRisk(Pydantic):
    node_id/type (delay|dependency|resource|scope)
    severity (low|medium|high)
    mitigation: str
```

## Planning Engine 流程

```
目标 (Goal/PRD)
  → 分析 (目标分解: 复用 understanding 7 + product 9d)
  → 计划生成 (Task Graph + 模式选择)
  → 调度 (拓扑排序 + 关键路径 + 并行组)
  → 执行 (任务分派: Organization Agent Registry → 17 执行)
  → 监控 (进度事件 → 偏差检测)
  → 重规划 (风险触发 → 更新图/调度)
```

## 关键路径与并行

```
关键路径: 最长依赖链 = 项目最短工期 (瓶颈不可并行)
并行优化: 无依赖节点组成 parallel_groups → 多 Agent 并行 (Phase 18 多执行器)
动态重规划: 某节点延误 → 重算关键路径 → 调整资源/顺序 → 报告 Human
```

## 与 Organization 协作

```
Goal → Planning (PM 角色) → Task Graph
  → 每节点 → Role 匹配 (Agent Registry) → 4B-3 分配
  → 并行组 → 多 Agent 并行执行 (18)
  → 汇总 → Review (Tester/Security) → Human Approval → Merge
```

## 透明与可控

```
透明: 计划/调度/关键路径/风险全部 = Artifact + Event (planning.*)
可控: 重规划 = 建议 (Recommendation, 10A-3 语义) → 重大变更 Human Approval
      项目经理 (Planning AI) 无执行权 (执行权 != 审核权, Phase 18 铁律)
```

## 与现有能力复用

```
understanding (7)    → 目标分析
product 9d           → 生命周期阶段
agents/assignment    → 角色/分配
execution (4C)       → 执行编排
metrics (5B)         → 进度监控
intelligence (10A)   → 推荐/决策/风险
approval (9c)        → 计划变更审批
```

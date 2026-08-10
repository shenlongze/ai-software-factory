# Project Management System (S10-010 设计)

> 状态: 架构待确认 | 范围: 设计文档 (不开发 UI)
> 核心差异: 传统工具辅助人管理项目; AI Factory = AI 项目经理主动管理 AI 团队完成项目。

## 一、管理模型 (Agile Scrum)

```
Project
├── Vision
├── Product Discovery
├── PRD
├── Roadmap
├── Milestone
├── Backlog
│   ├── Epic        (月/季度 — 大能力)
│   ├── Feature     (周/月 — 用户可感知功能)
│   ├── Story       (周 — 用户需求描述)
│   └── Task        (小时/天 — 实际执行工作)
├── Sprint          (固定周期 — 执行窗口)
│   ├── Sprint Planning
│   ├── Sprint Goal
│   ├── Task Reference   ← Sprint 引用 Task, 不是包含
│   ├── Daily Progress
│   └── Sprint Review
├── Priority Engine
├── Critical Path
├── Dependency Graph
├── Todo Tree
├── Workflow Instance
├── Runtime
├── Logs
└── AI Project Manager (Progress/Risk/Priority/Schedule/Decision)
```

## 二、Backlog 层级 (Sprint 与 Task 关系)

```
Backlog:  Epic → Feature → Story → Task        (需求层级)
Sprint:   Sprint-001 → Task-001/002/003        (执行窗口, 引用 Task)

一个 Task 可以延期/转移 Sprint/重新规划 — 需求不变。
Task 属于 Backlog; Sprint 只是引用。
```

## 三、Task 生命周期

```
BACKLOG → READY → WAITING_DEPENDENCY → AVAILABLE → ASSIGNED → RUNNING
  → REVIEW → TESTING → DONE
异常: BLOCKED / FAILED / CANCELLED
```

Task 记录 (谁什么时候干了什么 — 多 Agent 公司可审计):

```json
{
  "id": "TASK-001",
  "title": "Implement Login API",
  "owner": "Backend Agent",
  "priority": "P1",
  "milestone_ref": "M1",
  "created_at": "2026-08-11",
  "started_at": "2026-08-12",
  "completed_at": null,
  "executor": { "type": "agent", "name": "Backend Engineer Agent" },
  "depends_on": ["TASK-000"],
  "resource": ["database", "user_model"],
  "conflict_scope": ["backend/user"],
  "history": [
    { "time": "", "actor": "", "action": "", "result": "" }
  ]
}
```

回答: 昨天 AI 干了什么? 为什么延期? 谁阻塞? 当前进度?

## 四、Priority Engine (AI 自动计算 + 用户 Override)

```
P0 Critical / P1 Important / P2 Normal / P3 Nice To Have

AI Priority Score (0-100):
  影响用户 ★ / 影响收入 ★ / 阻塞任务 ★ / 开发成本 ★

决策权限: AI Recommendation → 用户 Override → Decision Log (可学习)
```

## 五、Milestone (项目生死节点)

```
Milestone → Epic → Feature → Task
M1: App Store First Release (状态/完成%/包含/预计/风险)
```

## 六、Critical Path Engine (AI 自动判断关键任务)

```
输入: Task List + Dependency + Deadline + Resource + Cost
输出: 关键路径 (T001→T005→T008→Release) + 风险任务 (阻塞 N 个后续/延期影响/建议)
```

## 七、Todo Tree (普通人视角 — 非 Jira)

```
ScorePocket — 完成度 42%
├── 产品定义 ✅
├── UI设计 ✅
├── 后端开发 🚧
│   ├── 用户系统 (登录接口 ✅ / 注册接口 ✅ / 权限系统 ⏳)
│   └── 比赛管理 (创建比赛 ✅ / 计分逻辑 🚧 / 排名系统 ⏳)
├── 测试 (单元测试 ⏳ / 自动化测试 ⏳)
└── 发布 (App Store准备 / 商业化配置)
```

## 八、Progress Intelligence (项目状态面板)

```
Project Health: Progress / Schedule (At Risk) / Budget / Critical Tasks / Blocked
Next Action: Backend Agent 完成计分模块
AI Recommendation: 增加 QA Agent 提前测试
```

## 九、AI Project Manager

```
- Progress Analysis     (进度分析)
- Risk Detection        (风险检测)
- Priority Recommendation (优先级建议)
- Schedule Prediction   (排期预测)
- Decision Support      (决策支持 — Decision Log 记录 AI 建议 vs 用户 Override)
```

## 十、数据存储

```
workspace/projects/{slug}/management/
  roadmap.md / milestone.json / sprint/{sprint-N}.json
  backlog/{epic,feature,story,task}.json
  risk.json / metrics.json / decisions.json
约束: 管理状态存 management/ (禁止存 runtime/); runtime 只存执行过程。
```

# S10-056 — Agent Team Collaboration 设计

> 日期:2026-08-15 | Sprint: S10-056 | 设计
> 目标: 从"单 Agent 自动开发"升级为"多 Agent 软件生产团队"

---

## 1. 架构(扩展层, 不重构主链路)

```
已有主链路 (保持稳定):
  Intent → Product → Engineering → Tasks → AgentMatcher → Execution → Validation → Repair → Delivery
    ↓
新增 Team 扩展层:
  AgentTeam (team.json: 团队成员/角色/项目归属)
    ├─ Team Registry (团队注册/查询/分配)
    ├─ Team Assignment (项目 → 团队)
    └─ Team Collaboration 视图 ("查看团队" 增强: 成员角色/负载/绩效)
```

## 2. 数据模型

### AgentTeam
```json
{
  "team_id": "software-team",
  "name": "AI Software Team",
  "members": [
    {"agent": "pm-agent", "role": "product_manager"},
    {"agent": "architect-agent", "role": "architect"},
    {"agent": "backend-1", "role": "backend"},
    {"agent": "flutter-dev", "role": "frontend"},
    {"agent": "qa-agent", "role": "qa"}
  ],
  "projects": [],
  "created_at": "..."
}
```

### Team Registry (teams.json)
```json
{"software-team": {team_id, name, members, projects, created_at}}
```

## 3. 模块计划

```
factory-console/session/teams.py (新增):
  - class AgentTeam (dataclass): team_id/name/members/roles/projects/created_at
  - class TeamRegistry: create/get/list/assign_project/members; DEFAULT_TEAM (software-team)
  - class TeamService: build_default_team(agents) → 默认团队; team_snapshot(registry, metrics) → 协作视图

actions.py (修改): +team action ("查看团队/团队状态" 增强 → 团队视图; "创建团队" → TeamRegistry.create)
intent.py/router.py: +INTENT_TEAM 关键词 ("团队", "查看团队" 已有 workforce; 扩展 team 语义)
tests/console/test_session_teams.py (新增, >=50 测试)
docs/sprint10/S10-056-agent-team-collaboration.md
```

## 4. 协作视图 (team_snapshot)

```
Team: AI Software Team
  pm-agent       product_manager    -       -        -
  architect-agent architect          -       -        -
  backend-1      backend            65%     17       2 任务中
  flutter-dev    frontend           100%    1        0 任务中
  qa-agent       qa                 -       -        -
```

## 5. 边界

- 不重构主链路 (Team 是扩展层)
- 复用 agents.json/AgentMetrics (真实数据)
- 默认团队含现有 3 Agent + 预留 pm/architect/qa 角色
- Core 零改动

---

> 设计完毕 | Team Model + Registry + 协作视图 | 扩展层

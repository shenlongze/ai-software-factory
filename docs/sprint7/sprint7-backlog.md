# Sprint 7 — Backlog

> 日期: 2026-08-08 | 状态: 设计待审核 | JSON + Tree

## Backlog Tree

```
Sprint 7 — Organization → Execution Pipeline
├── S7-001 Organization Model 统一 (org 模板 vs exec roles)   [P0, 前置]
├── S7-002 PM Agent executable (planning→executable)         [P0, dep: 001]
├── S7-003 Architect Agent executable                        [P0, dep: 001]
├── S7-004 Tester Agent executable (Developer↔Tester Loop)   [P0, dep: 001]
├── S7-005 Workflow Engine (组织级编排 + Artifact 流转)        [P0, dep: 002-004]
├── S7-006 Release Agent (build/package/release note)        [P1, dep: 005]
├── S7-007 Analytics Agent (metrics/建议)                    [P1, dep: 006]
└── S7-008 Full Lifecycle Demo (Idea→Release 全链)           [P1, dep: 005-007]
```

## Backlog JSON

```json
{
  "sprint": "7",
  "goal": "AI Software Factory: AI Coding Worker → AI Software Organization",
  "backlog": [
    {
      "id": "S7-001",
      "title": "Organization Model 统一",
      "priority": "P0",
      "dependency": "Sprint 6.5",
      "acceptance": "org 模板角色 (CEO/PM/Architect/Developer/QA) 与 exec roles.py (6 角色) 统一为单一角色注册表; employee hire 大小写不敏感; capabilities 生效",
      "estimated_complexity": "M"
    },
    {
      "id": "S7-002",
      "title": "PM Agent executable",
      "priority": "P0",
      "dependency": "S7-001",
      "acceptance": "输入想法 → 输出 PRD artifact (market/persona/requirement/feature tree/MVP scope); 真实 v4-pro 执行; 产物结构化可验证",
      "estimated_complexity": "M"
    },
    {
      "id": "S7-003",
      "title": "Architect Agent executable",
      "priority": "P0",
      "dependency": "S7-001",
      "acceptance": "输入 PRD → 输出 Design artifact (system/db/API/task breakdown); 任务拆解自动生成; 可验证",
      "estimated_complexity": "M"
    },
    {
      "id": "S7-004",
      "title": "Tester Agent executable + Dev↔Tester Loop",
      "priority": "P0",
      "dependency": "S7-001",
      "acceptance": "输入 Developer Artifact → 测试 → 失败分析 → bug report → repair task 回传; Loop ≤2 轮; 复用验证循环",
      "estimated_complexity": "L"
    },
    {
      "id": "S7-005",
      "title": "Workflow Engine 组织级编排 + Artifact 流转",
      "priority": "P0",
      "dependency": "S7-002/003/004",
      "acceptance": "User→Project→Workflow→Role→Task→Artifact 全链; 阶段产物自动流转; 人工闸门保持; 事件审计",
      "estimated_complexity": "L"
    },
    {
      "id": "S7-006",
      "title": "Release Agent",
      "priority": "P1",
      "dependency": "S7-005",
      "acceptance": "build/package 沙箱内执行; release note 生成; 产物 artifact",
      "estimated_complexity": "M"
    },
    {
      "id": "S7-007",
      "title": "Analytics Agent",
      "priority": "P1",
      "dependency": "S7-006",
      "acceptance": "metrics 采集 + 分析建议 artifact",
      "estimated_complexity": "S"
    },
    {
      "id": "S7-008",
      "title": "Full Lifecycle Demo",
      "priority": "P1",
      "dependency": "S7-005/006/007",
      "acceptance": "一个真实小项目: Idea→PM→Arch→Dev→Test→Release 全链自动; 输出代码+测试+发布产物+证据",
      "estimated_complexity": "L"
    }
  ]
}
```

## 执行顺序

```
S7-001 (统一) → S7-002/003/004 (角色并行) → S7-005 (编排) → S7-006/007 → S7-008 (演示)
每任务: 设计 → 编码 → 测试 → commit → push (Agile 小步)
```

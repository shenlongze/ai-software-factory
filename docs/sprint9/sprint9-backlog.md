# Sprint 9 — Backlog

> 日期: 2026-08-09 | 状态: 设计待审核 | JSON + Tree

## Backlog Tree

```
Sprint 9 — Productionization
├── S9-001 Approval Gate (人工审批接线: 三挡板)         [P0, 最高优先]
├── S9-002 Project 接入器 (已有项目注册 + 选择性沙箱)     [P0, dep: 001]
├── S9-003 Flutter/Dart 验证 (Dart 9 任务 Benchmark)    [P0, dep: 002]
├── S9-004 Cost Ledger (成本/日志追踪)                  [P1, dep: 002]
├── S9-005 Factory Console 操作化 (审批+项目+成本视图)    [P1, dep: 001-004]
└── S9-006 真实项目试点 (MarkPad 小任务 或 DevToolBox)   [P1, dep: 001-005]
```

## Backlog JSON

```json
{
  "sprint": "9",
  "goal": "AI Software Factory Productionization: MVP Demo → 真实生产使用",
  "backlog": [
    {
      "id": "S9-001",
      "title": "Approval Gate 人工审批接线",
      "priority": "P0",
      "dependency": "Sprint 8",
      "acceptance": "Workflow stage approval_required 属性; 完成→PAUSED; CLI workflow approve/reject; 三挡板 (product 后 MVP/design 后架构/release 前发布); 事件 +2 (paused/resumed); 测试 ≥25; 状态机严格 (禁非法跳转)",
      "estimated_complexity": "L"
    },
    {
      "id": "S9-002",
      "title": "Project 接入器 (已有项目注册 + 选择性沙箱)",
      "priority": "P0",
      "dependency": "S9-001",
      "acceptance": "register_project(path/lang/build_cmd/test_cmd); 选择性沙箱快照 (lib+pubspec 等, 排除 build/.dart_tool); 基线测试确认环境; Project 模型扩展; 测试 ≥20",
      "estimated_complexity": "L"
    },
    {
      "id": "S9-003",
      "title": "Flutter/Dart 验证",
      "priority": "P0",
      "dependency": "S9-002",
      "acceptance": "Dart 9 任务 Benchmark (dart analyze + dart test, 纯 Dart 包); 成功率/成本/失败分类; 对比 Python 基线; 诚实报告 (完整 Flutter 重 — 分步验证)",
      "estimated_complexity": "L"
    },
    {
      "id": "S9-004",
      "title": "Cost Ledger 成本/日志追踪",
      "priority": "P1",
      "dependency": "S9-002",
      "acceptance": "per project 聚合 (calls/tokens/cost/success_rate/per_stage); CLI org cost report; 从 events/execution 聚合; 测试 ≥15",
      "estimated_complexity": "M"
    },
    {
      "id": "S9-005",
      "title": "Factory Console 操作化",
      "priority": "P1",
      "dependency": "S9-001/002/004",
      "acceptance": "Console POST 端点 (approve/reject/register_project); Approval 页可操作; Projects 页注册视图; 成本视图; 只读→可写权限/审计 (操作记录事件); 测试 ≥15",
      "estimated_complexity": "L"
    },
    {
      "id": "S9-006",
      "title": "真实项目试点",
      "priority": "P1",
      "dependency": "S9-001~005",
      "acceptance": "MarkPad 小任务 (纯 Dart 逻辑 bug, 不重构) 或 DevToolBox 任务; 全链真实执行 + 审批闸门 + 成本日志; 产物交付用户验收; 报告",
      "estimated_complexity": "L"
    }
  ]
}
```

## 执行顺序

```
S9-001 审批门 → S9-002 项目接入器 → S9-003 Dart 验证 → S9-004 成本
→ S9-005 Console → S9-006 真实试点 (MarkPad/DevToolBox)
每任务: 设计 → 编码 → 测试 → commit → push (Agile 小步)
```

## 验证载体

```
S9-003: 纯 Dart 包 9 任务 (复用 s6b 分级模式, dart analyze/test)
S9-006: MarkPad lib/ 子集小任务 (用户冻结: 仅 bug/feature, 不重构)
```

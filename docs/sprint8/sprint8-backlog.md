# Sprint 8 — Backlog

> 日期: 2026-08-09 | 状态: 设计待审核 | JSON 格式

## Backlog Tree

```
Sprint 8 — AI App Production Team
├── S8-001 PM Agent executable                      [P0, 前置]
├── S8-002 UX/UI Designer Agent executable          [P0, dep: 001]
├── S8-003 Architect Agent executable               [P0, dep: 001+002]
├── S8-004 Release Agent executable                 [P0, dep: 005 链]
├── S8-005 Full App Lifecycle Demo                  [P0, dep: 001-004]
└── (Developer/Tester 增强内嵌各任务 — 不单独拆)
```

## Backlog JSON

```json
{
  "sprint": "8",
  "goal": "AI Software Organization → AI App Production Team: '开发一个 App' → Product+UX/UI+Architecture+Code+Test+Release",
  "backlog": [
    {
      "id": "S8-001",
      "title": "PM Agent executable",
      "goal": "想法 → Product Artifact (market/persona/journey/PRD/MVP/user story 6 节)",
      "input_artifact": "idea (自然语言)",
      "output_artifact": "product",
      "dependencies": "Sprint 7 (roles.py/EmployeeExecutor/Artifact/Workflow)",
      "acceptance_criteria": "PMAgent 真实 v4-pro 执行; Product Artifact 6 节结构化; CONTRACTS product 校验通过; Workflow product stage 可跑; 测试 ≥25",
      "estimated_complexity": "L"
    },
    {
      "id": "S8-002",
      "title": "UX/UI Designer Agent executable",
      "goal": "Product Artifact → UX/UI Artifact (IA/user flow/wireframe/screen spec/UI component/design token/prototype 7 节)",
      "input_artifact": "product",
      "output_artifact": "ux_ui",
      "dependencies": "S8-001",
      "acceptance_criteria": "UXUIDesignerAgent 真实 v4-pro; 新角色 ui-designer executable; CONTRACTS ux_ui 类型; wireframe ASCII+JSON spec 可消费; 测试 ≥25",
      "estimated_complexity": "L"
    },
    {
      "id": "S8-003",
      "title": "Architect Agent executable",
      "goal": "Product + UX/UI → Design Artifact (tech arch/db/api/frontend/backend/task breakdown 6 节)",
      "input_artifact": "product + ux_ui",
      "output_artifact": "design",
      "dependencies": "S8-001 + S8-002",
      "acceptance_criteria": "ArchitectAgent 真实 v4-pro; Design Artifact 6 节; task breakdown 自动生成 (task create); CONTRACTS design 校验; 测试 ≥25",
      "estimated_complexity": "L"
    },
    {
      "id": "S8-004",
      "title": "Release Agent executable",
      "goal": "Test Artifact → Release Artifact (build/version/package/release note/deployment 5 节)",
      "input_artifact": "test",
      "output_artifact": "release",
      "dependencies": "S7-004 (Tester) + S8-005 链",
      "acceptance_criteria": "ReleaseAgent 真实执行 (沙箱 build + 打包); Release Artifact 5 节; CONTRACTS release 强化; 测试 ≥20",
      "estimated_complexity": "M"
    },
    {
      "id": "S8-005",
      "title": "Full App Lifecycle Demo",
      "goal": "输入'开发一个记账 Web App' → 全链自动: PM→UX/UI→Arch→Dev→Test→Release, 输出完整产物集",
      "input_artifact": "idea",
      "output_artifact": "product+ux_ui+design+code+test+release (全链)",
      "dependencies": "S8-001~004",
      "acceptance_criteria": "真实 v4-pro 全链 (Product→Release 6 阶段); 每阶段 Artifact VALIDATED 流转; UI 代码生成 (HTML/JS); Test 通过; Release 产物 (zip+notes); 人工闸门 (MVP+发布); 报告 + 测试 ≥20",
      "estimated_complexity": "XL"
    }
  ]
}
```

## 执行顺序

```
S8-001 PM → S8-002 UX/UI → S8-003 Architect → S8-004 Release → S8-005 全链 Demo
(Developer/Tester 增强内嵌: S8-005 前按需 — 多语言 prompt/UI 代码/测试类型)
每任务: 设计 → 编码 → 测试 → commit → push (Agile 小步)
```

## 验证载体

```
记账 Web App (纯前端 HTML/CSS/JS + 静态检查测试) — 全链可测, 发布简单
```

# AI Software Factory — 主视图（Factory Tree）

> ⭐ 项目全景主视图 | 实时更新 (与 factory-state.json 同步)
> 最后更新: 2026-08-08 | 基线: pytest 5493 / 158 事件 / 91 CLI / 147 commits

```
AI Software Factory (AI Company OS — 愿景)
│
├── 🎯 定位: 软件生产管理平台 + 组织建模 + 单 Agent 执行工程 (当前现实)
│           → AI Company OS 愿景达成度 ~25% (见 audit/architecture-reality-audit.md)
│
├── 📦 顶层结构
│   ├── factory-core/    [冻结] 25 模块 32736 行 — 事件/任务/工作流/审批/产品/智能
│   ├── factory-org/     [扩展] 组织模型 2081 行 — Company→Department→Role→Employee
│   ├── factory-exec/    [扩展] 执行工程 12353 行 — Context/Ranking/Progressive/Budget/
│   │                            Experience/MultiRun/Evaluator/Capability
│   ├── factory-console/ [UI]   Web 管理台 7 页 (只读) — Dashboard/Projects/Lifecycle/
│   │                            Intelligence/Approval/Decisions/Providers
│   ├── factory-runtime/ [Runtime] Managed Services + Command
│   ├── desktop/         [桌面] Tauri 2 launcher (dmg)
│   ├── tests/           [测试] 285 文件 5493 测试
│   ├── docs/            [文档] 185+ 文件 (本体系 5 个控制文件)
│   └── ⚠️ 11 空目录: agents/ cli/ dashboard/ knowledge/ mcp/ runtimes/ skills/
│                     src/ validation/ workflows/ (脚手架残留)
│
├── 🧱 核心能力 (DONE)
│   ├── 组织建模: Company/Department/Role/Employee/Authority/Knowledge (org)
│   ├── 产品链路: Idea→Research→PRD→Approval→UI→Arch→Task (product, 501 测试)
│   ├── 任务/工作流: TaskStore + WorkflowEngine + 4 技术模板 (feature-delivery 等)
│   ├── 验证: L1-L4 (task_data/workflow/artifact/change) + 证据链
│   ├── 审批: ApprovalGate + 三挡板 + 决策门
│   ├── 智能: Decision/Recommendation/Experience/Risk (intelligence, 509 测试)
│   ├── 执行工程: Context Ranking→Progressive→Budget→Experience→MultiRun→Evaluator
│   └── Provider 可替换: anthropic/openai 适配器 (Ollama 本地验证就绪)
│
├── 🚧 关键缺口 (见 audit)
│   ├── 真实生产 0%: DeepSeek 25/27 空响应 (模型瓶颈) → Sprint 6 换模型
│   ├── 组织-执行断链: Employee 不干活 → Sprint 7
│   ├── 单 Agent: 只有 Developer → Sprint 7-8
│   ├── UI 管理台非工作台 → Sprint 9
│   └── 多行业/领域智能 → Sprint 10-12
│
└── 🗺️ 路线 (见 roadmap.md / sprint-board.md)
    Sprint 6: 模型换档 → 7: 组织-执行连接 → 8: 多角色员工
    Sprint 9: 工作台 UI → 10: Skill/MCP 领域 → 11: 自改进 → 12: 多行业
```

## 模块状态速查

| 模块 | 状态 | 测试 | 说明 |
|:-----|:----:|:----:|:-----|
| factory-core | 🟢 冻结 | 4000+ | 不可改 (Removal 测试保护) |
| factory-org | 🟢 完成 | 192 | 组织模型 (待 Workspace/Organization 泛化) |
| factory-exec | 🟢 完成 | 1019 | 执行工程 (待模型兑现) |
| factory-console | 🟡 管理台 | 172 | 只读; 待工作台化 |
| factory-runtime | 🟢 完成 | 130 | Managed + Command |
| desktop | 🟢 完成 | 116 cargo | launcher |
| docs | 🟡 已校准 | — | 本体系 5 控制文件实时更新 |

## 链接

```
状态源 (机器可读):    docs/factory-state.json
任务板:              docs/sprint-board.md
路线:                docs/roadmap.md
决策:                docs/decisions.md
审计 (差距详情):      docs/audit/architecture-reality-audit.md
现状总表:            docs/status.md
```

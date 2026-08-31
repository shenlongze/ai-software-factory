# K8 WebUI IA — 推荐信息架构

> 日期: 2026-08-29 | 纯审计 (HARD STOP, 不执行)

## 1. 页面分类 (基于真实 Inventory)
| 分类 | 页面 | 理由 |
|------|------|------|
| KEEP | ConversationPage / WorkPage / ControlTowerPage | K6 三入口, 接 SSOT, 真实可用 |
| KEEP (项目 Detail) | project/AfProjectHome + Docs + TodoTree + Ops | 项目级工作区 |
| MERGE | AfProjectListView → WorkPage; AfProjectManage → WorkPage; ProjectsPage → WorkPage | 项目列表三处表达同一事实 |
| MOVE | AfMonitorPage → ControlTower (监控是塔的子视图); ApprovalPage → Work (审批是任务子操作) | 职责归位 |
| HIDE | AuditPage / AfSettings / DecisionsPage / IntelligencePage / LifecyclePage / ReviewPage / ProvidersPage / WorkflowPage / ArtifactsPage | 专业/内部能力, 非普通用户一级入口 |
| DEPRECATE | DashboardPage (board 旧板) / AfCompanyHome (旧首页, Conversation 取代) | 历史实现 |
| NEW | 无 (三入口已覆盖) | - |

## 2. 推荐 IA
```
AI Factory OS (Human Console)
│
├── 💬 Conversation (默认)
│   ├── 新对话
│   ├── 会话历史
│   └── Active Work (内嵌状态)
│
├── 📋 Work
│   ├── Projects (列表)
│   └── Project Detail
│       ├── Sprints
│       ├── Tasks (+ Approval)
│       └── Evidence
│
└── 🛰 Control Tower
    ├── Overview (全局)
    ├── 谁在工作 (Workforce)
    ├── Approvals (待审批)
    ├── Incidents (失败/恢复)
    └── Trace (钻取)

专业视图 (HIDE, 保留路由可访问):
  Audit / Settings / Intelligence / Providers / Plugins
```

## 3. 普通用户 vs 专业用户
- 普通用户: Conversation (默认) + Work (必要时)
- 专业用户: + Control Tower (运营) + 项目 Detail (执行/Evidence)
- OS 内部 (不暴露一级): Plugin Kernel / Context Runtime / Learning / Promotion / Self-Healing

## 4. 收敛原则
- 一级入口 = 3 (Conversation/Work/Tower)
- 旧 board 页面 (DashboardPage 等) 移入专业区或 deprecate
- 不删除功能, 只收敛入口 (HIDE 保留路由)

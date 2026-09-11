# 02 — MAINLINE COVERAGE (READ-ONLY)

| Mainline | Backend | WebUI | Status | Gap |
|---|---|---|---|---|
| IDEA | org project goal | AfSidebar/AfContextNav createProject | 🟢 REAL | — |
| DISCOVERY | project idea/disc 资产 | AfProjectHome detail (goal) | 🟡 PARTIAL | discovery 资产展示弱 |
| REQUIREMENT | P1 canonical (tmp only) | 无独立入口 | 🔴 MISSING (主链) | canonical P1 未接旅程 |
| PRD | P1 canonical / M3 design | Workflow viewer (design 阶段) | 🟡 PARTIAL | 非 canonical 展示 |
| PLAN | P1 canonical | ProjectHome plans 字段 | 🟡 PARTIAL | 只读字段 |
| TASK TREE | backlog 真 | AfTodoTree | 🟢 REAL (读) | 无任务创建/操作 |
| EXECUTION | workflow_runner (S46 真) | chat → start; WorkflowPage 查看 | 🟡 PARTIAL | 触发真; 事件视图 mock fallback |
| VERIFICATION | P0 ver-* / org gate | AfQualityGate (org) | 🟡 PARTIAL | canonical ver-* 未接 UI |
| ARTIFACT | P0 art-* / M3 | AfWorkspace artifacts | 🟡 PARTIAL | canonical vs M3 展示面 |
| ACCEPTANCE | S45 ACC-* 完整 | **无** | 🔴 MISSING | **approve/request-change 零 UI** |
| RELEASE | S45 RELEASE-* 完整 | **无** | 🔴 MISSING | **create/gate/release 零 UI** |
| DELIVERY | dist zip (S46 真) | workspace 文件/产物; preview | 🟡 PARTIAL | 无下载/发布入口 |

主链覆盖率: 8/12 有真后端; WebUI 完整闭环到 EXECUTION; 验收→交付
(ACC/RELEASE/DELIVERY) 后端全有但 UI 全缺 → 用户无法完成主线终点。

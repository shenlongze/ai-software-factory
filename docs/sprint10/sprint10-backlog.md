# Sprint 10 — Backlog: AI Factory Workspace

> 日期: 2026-08-10 | 状态: 设计待审核 | 复用 Sprint 1-9, 不重复建设

## Backlog Tree

```
Sprint 10 — AI 软件生产工作台
├── S10-000 Design System (新增: 颜色/字体/Button/Card/Timeline/Status Badge/Artifact Card/Agent Avatar/Modal)
├── S10-001 Workspace Shell (三栏 UI 框架: Explorer/Workspace/Panel)
├── S10-002 Factory Runtime API (Timeline/Monitor/SSE/Browser URL/Artifacts/Downloads)
├── S10-003 Agent Timeline (中间核心: 事件流实时渲染 + 产物按钮 + 底部持续开发输入)
├── S10-004 Runtime Workspace ⭐核心 (调整: "+" 创建 Instance — Browser/Terminal, 非固定 Tab)
├── S10-005 Artifact Center (Explorer + Artifact Tab: 资产库式 6 类产物 + Renderer)
├── S10-006 Review Workflow (Review Tab + 页: PRD/UI/架构/发布审核闭环)
└── S10-007 CLI MVP (统一 factory 命令, 与 UI 同 API)
```

## Backlog JSON

```json
{
  "sprint": "10",
  "goal": "AI Factory Workspace — 用户打开输入一句话, 看到 AI 工作/设计/浏览器/审核/发布",
  "backlog": [
    {
      "id": "S10-000",
      "title": "Design System",
      "priority": "P0",
      "dependency": "无 (先行)",
      "acceptance": "设计 token (颜色/字体/间距/圆角/亮暗主题) + 组件库 (Button/Card/Timeline/StatusBadge/ArtifactCard/AgentAvatar/Modal/Layout); 复用 AI 自产 uxui.json token; 组件测试 + 文档; 后续所有页面消费",
      "estimated_complexity": "M"
    },
    {
      "id": "S10-001",
      "title": "Workspace Shell (三栏 UI 框架)",
      "priority": "P0",
      "dependency": "S10-000",
      "acceptance": "三栏布局 (Explorer 220px/Workspace flex/Panel 360px 可折叠); Header (品牌/项目/LLM 状态/主题); 路由; 消费 Design System; 复用 S9 数据逻辑; vitest+tsc 绿",
      "estimated_complexity": "L"
    },
    {
      "id": "S10-002",
      "title": "Factory Runtime API",
      "priority": "P0",
      "dependency": "Sprint 9 (workflow/approval/events)",
      "acceptance": "GET /api/timeline (事件流); GET /api/projects/{id}/monitor (8 阶段/成本/耗时); SSE /api/events; POST /api/projects (一句话建项目+启动); GET /api/projects/{id}/browser/url; GET /api/projects/{id}/downloads; 测试 ≥25",
      "estimated_complexity": "L"
    },
    {
      "id": "S10-003",
      "title": "Agent Timeline",
      "priority": "P0",
      "dependency": "S10-001/002",
      "acceptance": "中间核心区: 事件流渲染 (user/stage/artifact/review/diff/error 节点); SSE 实时追加; 产物按钮 (查看/打开设计/去审核); 状态色; 测试 ≥20",
      "estimated_complexity": "L"
    },
    {
      "id": "S10-004",
      "title": "Runtime Workspace (Instance 模式)",
      "priority": "P0",
      "dependency": "S10-002",
      "acceptance": "Runtime Tab = Instance 列表 + [+] 创建菜单 (browser|terminal); RuntimeInstance 模型 (id/type/project_id/artifact_id/status/url|session); API: POST/GET runtimes + start/stop + screenshot; Browser Instance: iframe 沙箱预览 + Artifact 绑定 + 截图反馈; Terminal Instance: 日志流 + 命令输出 + Build/Test 状态; 测试 ≥20",
      "estimated_complexity": "XL"
    },
    {
      "id": "S10-005",
      "title": "Artifact Center",
      "priority": "P1",
      "dependency": "S10-001/002",
      "acceptance": "Explorer Project Tree (阶段→产物); Artifact Tab 6 类产物查看 (JSON 格式化/代码高亮/zip 下载); Artifact Renderer L1 (wireframe 布局预览) + L2 (token 主题预览); 测试 ≥20",
      "estimated_complexity": "L"
    },
    {
      "id": "S10-006",
      "title": "Review Workflow",
      "priority": "P1",
      "dependency": "S10-001~005",
      "acceptance": "Review Tab 待审清单; Review 页 (左内容右操作: 意见 + 重新设计/批准继续); 历史审批记录; 与 S9 审批门对接; 测试 ≥20",
      "estimated_complexity": "L"
    },
    {
      "id": "S10-007",
      "title": "CLI MVP",
      "priority": "P1",
      "dependency": "S10-002 (同一 API)",
      "acceptance": "factory 命令: init/start/status/create/review/approve/artifact/release; 委托现有 CLI 函数; 与 UI 同 API; 人类可读+--json; 测试 ≥20",
      "estimated_complexity": "M"
    },
    {
      "id": "S10-084",
      "title": "Product Intelligence Pipeline (Idea → PRD 多角色资产链)",
      "priority": "P0",
      "dependency": "S10-050/065/066/083 (复用引擎+血缘字段); 计划见 docs/sprint10/S10-084-plan.md",
      "acceptance": "7 角色 (PM/Market/Competitive/UX/Architect/QA/SeniorPM) 真实产出版本化资产 (product/market_analysis/competitive_analysis/ux_flow/architecture/test_plan/prd); 每资产 AuditEvent 含 artifact_reference+parent_event; discovery.md 落盘 (整理需求不创建); LLM 失败→deterministic 兜底; PRD 深度化替代模板; Discovery/PRD 审批门; 需求变更回流 (ChangeProposal→影响分析→审批→资产 v+1→ReplanningEngine); CLI factory product pipeline/artifact/approve + API; 测试 ≥60; 真实 E2E: 客户管理系统 7 资产可见→确认→PRD→工程→执行",
      "estimated_complexity": "XL"
    },
    {
      "id": "S10-087",
      "title": "回归原设计: 真实 AI Agent 团队重建 (AgentEntity + HandoffBus + 真工具 + 记忆闭环)",
      "priority": "P0",
      "dependency": "S10-084 (资产链); 计划见 docs/sprint10/S10-087-agent-rebuild-plan.md",
      "acceptance": "P0: 7 角色真实 Agent 实体 (各自 system_prompt/skills) + HandoffBus 真实交接, 每资产含 parent_artifact 引用; P1: 工具层 (发现本机 AI CLI codex/hermes/openclaw/claude + MCP stdio 真连接 + AI 委托调用) + 存量仓库模式 (读→改→测试→修复); P2: 记忆/评价闭环 (经验回写 agent 画像并影响决策); 真实 E2E: 一句话→7 Agent 交接→深度 PRD→工程→代码落盘→pytest 绿; 回归 tests/console 全绿; 版本 v1.2.0",
      "estimated_complexity": "XL"
    }
  ]
}
```

## 执行顺序

```
S10-001 Shell → S10-002 API → S10-003 Timeline → S10-004 Browser
→ S10-005 Artifact → S10-006 Review → S10-007 CLI
每任务: 设计 → 编码 → 测试 → commit → push (Agile 小步)
```

## 复用清单（避免重复建设）

```
✅ Workflow/Artifact/Approval/Agent (S1-9) — 全复用
✅ S9 Console 前端/后端 — 数据逻辑复用, 重排三栏
✅ events 流 — Timeline/Monitor 数据源
✅ org approval — Review 闭环
✅ 沙箱 — Browser 预览隔离
✅ 已有 AI 自产设计规范 (/tmp/ai-factory-product-ui/uxui.json) — UI token/布局参考
🆕 仅新增: 三栏 Shell + Timeline + Browser Runtime + Artifact Renderer + Runtime API + CLI 壳
```

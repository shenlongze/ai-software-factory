# Sprint 10 — Backlog: AI Factory Workspace

> 日期: 2026-08-10 | 状态: 设计待审核 | 复用 Sprint 1-9, 不重复建设

## Backlog Tree

```
Sprint 10 — AI 软件生产工作台
├── S10-001 Workspace Shell (三栏 UI 框架: Explorer/Workspace/Panel)
├── S10-002 Factory Runtime API (Timeline/Monitor/SSE/Browser URL/Artifacts/Downloads)
├── S10-003 Agent Timeline (中间核心: 事件流实时渲染 + 产物按钮)
├── S10-004 Browser Runtime (右侧 Browser Tab: iframe 沙箱预览)
├── S10-005 Artifact Center (Explorer + Artifact Tab: 6 类产物查看 + Renderer)
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
      "id": "S10-001",
      "title": "Workspace Shell (三栏 UI 框架)",
      "priority": "P0",
      "dependency": "S9 Console 前端",
      "acceptance": "三栏布局 (Explorer 220px/Workspace flex/Panel 360px 可折叠); Header (品牌/项目/LLM 状态/主题); 路由 /projects/:id 等; 亮暗主题 (design_tokens); 复用 S9 数据逻辑; vitest+tsc 绿",
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
      "title": "Browser Runtime",
      "priority": "P0",
      "dependency": "S10-002 (browser/url)",
      "acceptance": "右侧 Browser Tab: iframe 沙箱预览; 工具栏 (刷新/截图/新窗口); 空态引导; 沙箱静态服务器启动 (python http.server); 测试 ≥15",
      "estimated_complexity": "L"
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

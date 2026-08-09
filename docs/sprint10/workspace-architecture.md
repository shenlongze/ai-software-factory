# Sprint 10 — Workspace Architecture: AI 软件生产工作台

> 日期: 2026-08-10 | 状态: 设计 (ONLY DESIGN) | 参考: Cursor/TRAE/Windsurf/Devin/Figma Review
> 目标: AI Factory 从"生产引擎" → "软件生产产品" (普通用户打开就能用)

## 1. 产品定位

```
AI Factory = AI 软件生产工作台 (不是后台管理/CRUD Dashboard)

用户打开 AI Factory:
  输入 "开发一个记账 App"
  → 看到: PM 分析 → PRD 查看 → UX/UI 设计 → 浏览器真实预览
  → 审核: 需求/设计/架构/发布
  → 看到: 代码变化 → 测试 → 发布下载
```

## 2. 总体布局 (三栏)

```
┌───────────────────────────────────────────────┐
│ Header: 品牌 / 项目选择 / LLM 状态 / 主题 / 命令  │
├─────────┬───────────────────────┬──────────────┤
│         │                       │              │
│ Factory │   AI Workspace        │ Factory Panel │
│ Explorer│   (Agent Timeline)    │ (4 Tabs)     │
│         │                       │              │
│ 左侧栏   │  中间核心区            │ 右侧面板      │
│         │                       │  Browser     │
│         │                       │  Task        │
│         │                       │  Artifact    │
│         │                       │  Review      │
└─────────┴───────────────────────┴──────────────┘
```

## 3. 组件架构

```
① Factory Explorer (左侧)
   导航: Home / Projects / Tasks / Agents / Skills / Templates / Artifacts / Settings
   Project Tree: Ledger App ├ Product ├ UX/UI ├ Architecture ├ Code ├ Test └ Release
   (项目 → 阶段树, 点击跳阶段产物)

② AI Workspace (中间, 核心)
   Agent Timeline: 从上到下事件流 (类似 Chat 但非聊天)
     User: "开发一个记账 App"
     → PM Agent [Running] → Product Artifact [查看]
     → UX/UI Agent → UX/UI Artifact [打开设计]
     → Developer → Code Artifact [修改文件/diff]
   → 实时 SSE 推送 (org.workflow.* 事件 → Timeline 节点)
   → 每节点: Agent 图标/状态/耗时/成本/产物按钮

③ Factory Panel (右侧, 4 Tabs)
   Browser: 内置浏览器 (AI 生成软件真实运行预览 — 核心差异化)
   Task: Workflow 8 阶段状态 (✅🟡⭕ + Progress/Cost/Time)
   Artifact: 全部产物 (PRD/Design/Code/Test/Release)
   Review: 人工审核 (需求/UI/架构/发布 — 意见 + 批准/重做)
```

## 4. Browser Runtime (核心差异化)

```
功能: 查看 AI 生成的软件真实运行页面 (localhost:<port>)
  - 刷新 / 截图 / 打开链接
  - 未来 Agent Browser Tool: open()/click()/input()/screenshot()/console()

实现:
  后端: 沙箱内起静态服务器 (python -m http.server 或 node serve)
      → GET /api/projects/{id}/browser/url 返回运行 URL
  前端: iframe 嵌入 + 工具栏 (刷新/截图/新窗口)
  安全: 仅本机沙箱进程, 生产项目不暴露
```

## 5. Artifact Renderer (UX/UI Visual Review)

```
问题: UX/UI Artifact 是 JSON (wireframe/screen/component/token) — 用户看不到
设计: Artifact Renderer 层
  UX/UI Artifact (JSON) → Renderer → Visual Preview

渲染策略 (分三级, 渐进):
  L1 Wireframe Renderer: JSON Screen {components/actions} → 布局卡片预览 (现有)
  L2 Token 主题化: design_tokens → CSS 变量 → 预览页真实样式
  L3 真实页面: Developer 产物 (HTML) → Browser Runtime 预览 (最高保真)
  → Review 页三态切换: Wireframe / 主题预览 / 真实浏览器
```

## 6. API 设计 (Runtime API — CLI 与 UI 同一 API)

```
GET  /api/timeline?project_id=      Agent Timeline 事件流 (org.workflow.*/artifact.*)
GET  /api/projects/{id}/monitor     8 阶段状态/成本/耗时 (轮询 2s 或 SSE)
POST /api/projects                  {idea, project_type, tech} → 建项目+启动 workflow
GET  /api/projects/{id}/artifacts   产物列表
GET  /api/artifacts/{id}            产物详情 (metadata + renderer 提示)
GET  /api/projects/{id}/browser/url 运行 URL
POST /api/approvals/{id}/approve|reject  审批 (已有)
GET/PUT /api/settings/llm           LLM 配置 (key 加密)
GET  /api/projects/{id}/downloads   发布包下载

SSE: GET /api/events?project_id=    实时事件推送 (Timeline 驱动)
```

## 7. 复用清单（不破坏 Sprint 1-9）

```
✅ Workflow/Artifact/Approval/Agent Executor — 全复用
✅ org CLI 函数 — factory 包装委托
✅ Console 前端/后端 (S9) — 数据逻辑复用, 重排为三栏
✅ events 流 — Timeline/Monitor 数据源
✅ 沙箱/审批门 — 生产保护
🆕 新增: 三栏 Shell + Timeline 渲染 + Browser Runtime + Artifact Renderer + Runtime API
```

## 8. 技术栈

```
前端: React + TS + Vite (现有 5180 基础) + iframe (Browser)
后端: FastAPI (现有 8011) + SSE + 沙箱静态服务器
数据: ~/.factory (唯一数据根)
```

## 9. 安全

```
沙箱: 所有 AI 生成代码运行在沙箱 (Browser 只开沙箱进程)
Key: 加密存储 + 进程内注入
审批: 写路径仅 approve/reject/create (Permission Boundary)
```

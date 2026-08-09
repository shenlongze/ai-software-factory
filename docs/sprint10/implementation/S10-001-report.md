# S10-001 — Workspace Shell 实现报告

> 任务: S10-001 Workspace Shell (三栏 UI 框架) | 日期: 2026-08-10 | 状态: 已提交, 等人工审核
> 依据: workspace-architecture.md (三栏) + ui-information-architecture.md (导航/路由/状态机) + api-data-model.md (mock 数据形状) + sprint10-backlog S10-001
> 约束达成: 只做 Shell 框架; 消费 S10-000 Design System 零重复 CSS; mock data 不接 API; Core/Runtime/Desktop 冻结; vitest/tsc/pytest 全绿

## 1. 交付摘要

| 项 | 结果 |
|---|---|
| 三栏布局 | Header + Explorer 220px + Workspace flex + Panel 360px, 两侧可折叠 (消费 S10-000 `<Layout>`) |
| Header | AI Factory 品牌 / 项目选择 (mock) / LLM 状态 / ThemeToggle / 用户菜单 (设置 + 返回控制台) |
| Explorer 导航 | 8 项 (Home/Projects/Tasks/Agents/Skills/Templates/Artifacts/Settings) + Project Tree mock |
| Project Tree | 记账 App ├ Product ├ UX/UI ├ Architecture ├ Code ├ Test └ Release — 状态色点 + 中文标签 |
| Workspace | 空态页 "AI Workspace" + Timeline 预留容器 (S10-003 接入点) + 项目工作台 (选中项目) |
| Panel | 4 Tab 框架 (Browser/Task/Artifact/Review), 每 Tab Empty State |
| 路由 | state 导航 (与 AppState 模式一致) + `#/workspace` 直接入口 (URL hash) |
| mock data | `src/mock/workspace.ts` (导航/项目树/Panel Tab/LLM 状态/用户) |
| 测试 | vitest 177 全绿 (151 基线 + 26 新) / tsc 零错 / pytest 6456 全绿零回归 |
| 截图 | /tmp/s10-001-shots/workspace-shell-home.png (1600×900, headless Chrome, `#/workspace`) |

## 2. 布局与组件

```
┌ Header: ◆ AI Factory | 项目选择 (mock) | LLM 已连接 · DeepSeek v4-flash | 🌙/☀️ | 管理员 ▾ ┐
├─────────────────────┬──────────────────────────────┬───────────────────────────────────┤
│ Factory Explorer    │  AI Workspace (flex)         │ Factory Panel (360px, 可折叠)      │
│ (220px, 可折叠)      │  空态 ✨ + 新建项目/选择项目   │  [Browser|Task|Artifact|Review]    │
│ 导航 8 项            │  + Agent Timeline 预留容器    │  每 Tab Empty State (S10-00X 接入)  │
│ 项目树 (选中后展开)   │  (选中项目 → 项目工作台)       │                                   │
└─────────────────────┴──────────────────────────────┴───────────────────────────────────┘
```

### 新增文件 (全部 `frontend/src/**`, 无冲突 basename)

| 文件 | 职责 |
|---|---|
| `src/mock/workspace.ts` | mock 数据: NAV_ITEMS (8) / MOCK_PROJECTS (阶段链) / PANEL_TABS (4) / LLM_STATUS / CURRENT_USER / projectStatusBadge |
| `src/shell/WorkspaceShell.tsx` | Shell 主组件: 组合 Header + `<Layout>` 三栏; 内部 state (view/selectedProjectId/panelTab) |
| `src/shell/WorkspaceHeader.tsx` | Header: 品牌/`Select` 项目选择/LLM 状态 pill (复用 `ds-badge`)/`ThemeToggle`/用户菜单 |
| `src/shell/ExplorerNav.tsx` | 8 项导航 (图标+文字, active + aria-current) |
| `src/shell/ProjectTree.tsx` | 项目行 + 6 阶段树, 状态色点 (tone → `--ds-status-*`) + 中文状态标签 |
| `src/shell/WorkspaceView.tsx` | 空态页 AI Workspace / 项目工作台 / Settings / 通用占位; `TimelinePlaceholder` (S10-003 接入点, testid `timeline-placeholder`) |
| `src/shell/FactoryPanel.tsx` | 4 Tab 框架 (role=tablist/tab/tabpanel, aria-selected) + 每 Tab Empty State |
| `src/shell/workspace.css` | 仅 Shell 专属结构样式, 100% 消费 `--ds-*` 令牌 (见 §3) |

### 修改文件

| 文件 | 变更 |
|---|---|
| `src/state/AppState.tsx` | Page 增加 `workspace`; 新增 `pageFromHash()` (`#/workspace` 直接入口, 默认仍 dashboard) |
| `src/App.tsx` | 导航新增 "工作台" → `{name:'workspace'}`; 该页全屏渲染 `<WorkspaceShell/>` (独立于 Human Console, 无 console 头/脚) |

## 3. 消费 Design System — 零重复 CSS

- **组件复用**: `<Layout>` (三栏/折叠) / `<ThemeToggle>` (主题) / `<Select>` (项目选择) / `<StatusBadge>` (项目状态) / `<Button>` (空态按钮) / `ds-badge` 类 (LLM 状态 pill)
- **令牌消费**: `src/shell/workspace.css` 只定义 `ws-` 前缀的结构类 (Header 条/导航行/树行/Tab 条/空态), 所有颜色/间距/圆角/字体/阴影引用 `design.css` 的 `--ds-*` 变量 — **未重复定义任何令牌, 未重写任何 ds- 组件样式**
- 组件逻辑侧复用 `tokens.ts`: `statusTone`/`statusLabel` (阶段色点 + 中文标签)、`agentMeta` 未直接使用 (树用色点, 头像由 S10-005 阶段产物接入)

## 4. 导航与路由

- **state 导航** (与 AppState 模式一致): Shell 内部 `view` (8 项) + `selectedProjectId` + `panelTab`; App 级 `page.name==='workspace'`
- **直接入口**: `#/workspace` → `pageFromHash()` → Workspace Shell (headless 截图入口; S9 默认 dashboard 不变)
- **返回控制台**: 用户菜单 "返回控制台" → `navigate({name:'dashboard'})` (S9 Human Console 零破坏, App.test 全绿)

## 5. 测试 (26 新用例, 唯一 basename `workspace-shell.test.tsx`)

| 分组 | 用例数 | 覆盖 |
|---|---|---|
| 三栏布局 | 4 | header/explorer/workspace/panel 渲染; 220px/360px 尺寸; 两侧折叠/展开 |
| Header | 5 | 品牌; 项目选择 (mock 选项/切换生效); LLM 状态; ThemeToggle 亮暗切换 (`html data-theme`) |
| Explorer 导航 | 3 | 8 项渲染; 点击切换 active + aria-current; Projects → 树显示 |
| Project Tree | 3 | 6 阶段渲染; 状态色点 data-status (completed/waiting_review/pending); 点项目 → 项目工作台 + Timeline 预留 |
| Panel 4 Tab | 3 | 4 Tab 渲染 + Browser 默认; Browser 空态; Tab 切换 (Task/Artifact/Review 空态 + aria-selected) |
| Workspace 视图 | 4 | AI Workspace 空态 + timeline-placeholder; 新建项目提示 (点击反馈); Settings 视图; Tasks 占位 |
| 用户菜单 | 2 | 打开→设置→Settings; 返回控制台 → navigate dashboard (探针) |
| App 集成/入口 | 2 | 控制台 "工作台" → Shell 全屏 (无 console 页脚); pageFromHash |

## 6. 验证结果

```
npx vitest run      → 177 passed (18 files), 0 failed   (S9 121 + S10-000 30 + S10-001 26)
npx tsc --noEmit    → 0 errors
.venv/bin/pytest -q → 6456 passed, 0 regression
```

> ⚠️ pytest 观察 (诚实记录): 全量跑 5 次中 2 次出现 `tests/runtime/test_cli_runtime_test.py::TestSmokeSuccess::test_smoke_default_instruction` 失败 — **已确认为既有 suite-order 偶发 flake, 与本任务无关**:
> - 本任务 diff 100% 在 `frontend/src/**` (后端零改动); 该测试在**隔离运行**和**文件级运行**均通过 (19/19)
> - **clean tree (stash 后 HEAD) 全量复跑 → 6456 passed**; 带本任务改动再次全量复跑 → 6456 passed
> - 结论: 环境/顺序依赖的间歇性 flake (runtime CLI smoke 测试), 建议后续单独排查, 不在 S10-001 范围

## 7. 启动验证 — headless 截图

```
vite dev (5173) → Chrome headless --screenshot --window-size=1600,900
URL: http://localhost:5173/#/workspace
截图: /tmp/s10-001-shots/workspace-shell-home.png  (1600×900, 91KB, 4643 唯一色 = 已渲染非空白)
DOM 佐证: --dump-dom 确认 ws-shell / ws-header / ds-layout (三栏) / ws-explorer-nav /
          ws-workspace-home / timeline-placeholder / ws-factory-panel / ws-panel-browser /
          ds-theme-toggle / 8 导航项 / 4 Panel Tab 全部在 #/workspace 渲染
```

## 8. 范围边界 (严格遵守)

- ✅ 只做 Shell: Header + 三栏 + 导航 + Tree mock + 空态 + Panel Tab 框架
- ❌ 未实现: Timeline 内容 (仅预留容器) / Browser Runtime / Artifact Renderer / Review 流程 / Agent 执行 / SSE
- ❌ 未接真实 API (mock data); 未动 Core/Runtime/Desktop; 未删任何既有测试; 无重复 CSS; 无 key/明文

## 9. 下一步

- **S10-002 Factory Runtime API**: `GET /api/projects/{id}/timeline|monitor` + SSE + `POST /api/projects` + `browser/url` — 替换 `src/mock/workspace.ts` (形状已对齐 api-data-model.md: Project/Stage/TimelineEvent/Artifact)
- S10-003 Agent Timeline: 在 `timeline-placeholder` (testid) 处接入 `Timeline` + `StageCard inTimeline` + SSE 事件流
- S10-004/005/006: 分别填充 Panel 的 Browser/Task/Artifact/Review Tab 空态

## 10. 文件清单

新增:
- `frontend/src/mock/workspace.ts`
- `frontend/src/shell/` (8 文件: WorkspaceShell/WorkspaceHeader/ExplorerNav/ProjectTree/WorkspaceView/FactoryPanel/workspace.css)
- `frontend/src/test/workspace-shell.test.tsx`
- `docs/sprint10/implementation/S10-001-report.md` (本文件)

修改:
- `frontend/src/state/AppState.tsx` (Page + workspace; pageFromHash)
- `frontend/src/App.tsx` (工作台 导航 + Shell 全屏渲染)

截图 (不入库, /tmp): `/tmp/s10-001-shots/workspace-shell-home.png` + `dom.html`

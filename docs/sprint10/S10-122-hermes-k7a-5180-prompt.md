# S10-122 · K-7a 5180 布局收敛（Human Console 重构第一步）— Hermes 提示词（2026-08-25）

> 战役: K-7a（docs/5180-Human-Console-设计稿.md §5）· 目标版本 v1.1.95/96（当前 HEAD v1.1.94;
> 若 K-5 先行消耗则顺延）
> 交付后: 设计稿 K-7a 状态 ✅ · 战役规划 K-7 部分完成
> 设计依据: docs/5180-Human-Console-设计稿.md（Founder 确认, Codex 布局）

---

请作为 Hermes 派发 Sprint 任务给 Codex，遵守既有纪律（pre-flight → plan → dispatch → verify → acceptance → report）。

【任务】S10-122 · K-7a 5180 布局收敛（Human Console 重构第一刀）
版本目标：v1.1.95（从实际 HEAD +1；若 K-5/S10-121 并发先行消耗则顺延 v1.1.96）

【背景（K-7a 是什么）】
5180 现在是"3 套独立页面(~28 页)"：普通模式(9 页监控向) + #/workspace(7 页) + #/project/:id(12 页)，
加上 ModeToggle 双模式、Header 项目选择器、常驻右栏 —— 太乱（Founder 确认）。
K-7a = 布局收敛第一刀：砍双模式/占位/常驻右栏，改造成 Codex 风格一套导航
（左=项目列表 · 中=项目工作区 · 底=对话输入 · 右=上下文按需 · 顶=状态）。

【现状（实事求是，pre-flight 必须核对，不限于此）】
1. App.tsx: Shell() 有 NavLink 主导航（Dashboard/项目/工作流/产物/审批/决策/智能/工作台/Providers-expert）
   + ModeToggle（普通↔Expert）+ isAiFactoryRoute 分支（#/workspace → AfWorkspaceEntry, #/project/:id → AfProjectEntry）
2. WorkspaceShell.tsx: 三栏（Explorer 220px | AI Workspace flex | Factory Panel 360px 常驻）+ ExplorerNav(4 项)
   + ProjectTree + WorkspaceHeader（品牌/项目选择器/LLM 状态/主题）
3. router.tsx: WORKSPACE_ROUTES(7) + PROJECT_ROUTES(12) + 普通模式页由 App.tsx page state 驱动
4. 普通模式页面组件（DashboardPage/ProjectsPage/LifecyclePage/ApprovalPage/DecisionsPage/IntelligencePage/
   WorkflowPage/ArtifactsPage/ReviewPage/ProvidersPage）——监控向（设计稿: 移 board 或并项目内）
5. 前端测试 43 个文件（vitest + testing-library）; 构建: tsc --noEmit && vite build; node_modules 已装
6. 后端 API 已就绪（/api/projects 等），5180 由 backend 托管 dist（同源 /api）

【设计与实现要求（先出设计文档 docs/sprint10/S10-122-k7a-5180-plan.md，批准后再实现）】
1. 砍双模式:
   - App.tsx 去掉 ModeToggle 与普通模式 NavLink 导航; 统一入口 = #/workspace（项目列表首页）,
     #/project/:id（项目工作区）
   - 普通模式页面组件**保留文件但不从导航/路由可达**（死代码留 K-7b 清理, 避免测试大爆炸）;
     受影响的 App/Shell 测试同步更新
2. 左栏 = 项目列表（Codex 任务列表形态）:
   - 新建项目按钮 + 搜索框 + 分组（进行中/已交付）——数据走 /api/projects 真实数据
   - 替代 ExplorerNav + ProjectTree 双导航（选项目只在左栏）
3. 底部全局对话输入（Composer）:
   - 常驻底部输入框（"继续聊 / 改需求 / /命令"）; 提交 → 调后端会话接口（无接口则先接线占位,
     如实标注）; 多行/Enter 发送
4. 顶栏状态: 项目名 + 生命周期状态 + 当前页 + 「🛠 开发者控制台」链接（→ http://127.0.0.1:8011/api/board）
5. 右栏: FactoryPanel 从常驻改为**默认收起/按需展开**（保留组件, 收起态不占 1/3 屏）
6. Header 项目选择器移除（选项目只在左栏）; 主题默认 light 不动（深色统一留 K-7c）
7. 注册表门禁（P0-10/11）: 若新增后端端点/前端路由规则, 同步注册表; 前端测试断言对齐

【硬边界】
- K-7a 只做布局收敛; 不做 K-7b 页面并轨（项目工作区 7 页全真实数据）/ K-7c 互通风格（互链+深色）
- 普通模式页面组件文件不删（K-7b 清理）; 业务逻辑/后端 API 不改
- 不新增依赖（用现有 React/Vite/vitest）; 不调 LLM
- 5180 由后端托管 dist, 构建产物要能更新（npm run build 后 dist 可被 backend 服务）

【验收标准（独立可验证，非 Codex 自报告）】
1. 进入 5180 → 直接项目列表（左栏）+ 项目工作区; 无 ModeToggle/普通模式导航残留
2. 左栏含 新建/搜索/分组, 数据来自 /api/projects（真实）
3. 底部 Composer 存在（输入/提交接线; 若未接后端如实标注"UI 就绪, 待 K-7b 接线"）
4. 顶栏含项目名/状态 + 开发者控制台链接（可点）
5. 右栏默认收起, 可展开
6. npm run build 通过（tsc --noEmit + vite build）; npm test（vitest）全过（更新受影响测试）
7. 后端回归 0 新增失败（环境性失败如实标注）
8. 版本 v1.1.95（或 96, 若并发消耗; pyproject+CHANGELOG+FEATURES+断言 同步）
9. 设计文档落盘 docs/sprint10/S10-122-k7a-5180-plan.md

【诚实记录】任何无法在 K-7a 完成的部分（如 Composer 真实后端接线、页面组件清理）如实标注
留 K-7b; 前端测试改动面大 → 列出影响清单; 不擅自扩大范围

# Changelog

> AI Software Factory — 变更日志 (Keep a Changelog 风格, 中文)。
> 版本语义: `v1.0.0-rc1` 为 v1.0 发布候选 (Release Candidate), 功能冻结, 只做文档与修复。

## [v1.1.114] — 2026-08-26

**项目导航 6 项路由落地 + C-2 集成收尾 (白名单/注册表同步)**。

### Changed

- **项目导航 6 项路由精简**: PROJECT_ROUTES 收敛为 overview/docs/todo/workflow/runtime/
  quality (全真实页面); 旧 URL (vision/prd/roadmap/backlog/sprint/logs) 自动回退 overview
- **白名单/注册表同步 (C-2 集成)**: test_s10_112 写路由白名单补 MCP 移除/LLM 配置/
  Agent/Skill 管理; test_console_api 路由导出补 remove_mcp_connection (v1.1.102 路由
  未同步注册表 → 2 回归, 本提交修复)

### 验证

- 后端 103 passed (C-2 接线 573 行测试 + 契约 + 白名单 + 导出) · 前端 681 passed
- 债务清单: C-2 ✅ · 契约缺口 G1-G4 已记录

## [v1.1.113] — 2026-08-26

**修复: 浅色主题强对比 — 硬编码深色全部变量化**。

### Fixed

- af.css 硬编码深色 (边框 #2a3140 89处 / 文字 #e5e7eb 66处 / 面板 #161a22 30处 /
  卡片/输入 #0f1115 26处 / hover #1c212b 等) 全部收敛为语义变量
  --c-border/--c-text/--c-panel/--c-card/--c-input/--c-surface/--c-hover 等
- 浅色主题统一覆盖这些变量 → 切换后无遗漏、无强对比 (剩余仅强调色/状态色, 两主题通用)

### 验证

- 前端 681 passed · build 通过 · 后端零改动

## [v1.1.112] — 2026-08-26

**主题 (深色/浅色) + 自定义背景图 (透明化/模糊)**。

### Added

- **主题切换**: ThemeProvider (dark | light, localStorage af.theme); 顶栏 ☀️/🌙 +
  设置 → 🎨 外观; 浅色主题 CSS 全量覆盖 (面板/卡片/表格/会话/文档/状态栏)
- **自定义背景**: 用户选本地图片 (dataURL) 或粘贴 URL; 透明化(opacity 5-90%) +
  模糊(blur 0-30px) 滑杆; 可读性遮罩 (深色暗遮/浅色亮遮); 清除背景;
  设置 → 🎨 外观

### 验证

- 前端 681 passed (含主题切换 + 背景层/透明化 2 用例) · build 通过 · 后端零改动

## [v1.1.111] — 2026-08-26

**系统级中英文切换 (Founder: 中文英文都要, 语言选择)**。

### Added

- **i18n 基础设施**: LanguageProvider + useI18n + zh/en 词典 + localStorage 持久
  (af.locale); 默认中文, 未迁移文案回退中文 (诚实)
- **语言选择器**: 顶栏 🌐 切换 + 设置 → 🌐 语言 tab
- **主界面双语化** (第一批): 工作区/项目导航 · 顶栏 · 公司首页 · 设置 tab 标签 ·
  状态栏 · 会话栏 (作用域/按钮/占位) · 文档/产出物 tab

### Changed

- 项目子页分发改按 route.page (i18n 安全, 不再依赖中文标签)
- 项目侧栏去掉重复 ◆ 品牌标记 (与工作区一致)

### 验证

- 前端 679 passed (含 i18n 切换 2 用例: 默认中文 + 切 English 导航全局切换) · build 通过
- 长尾页面文案 (设置表格/文档内容/项目详情等) 增量迁移 — 记入债务清单

## [v1.1.110] — 2026-08-26

**C-3 WebUI 实时 + 产出物历史查看 (与 C-2 引擎接线合并版本)**。

### Added

- **📦 产出物 tab** (文档页升级为 文档/产出物 双 Tab): Manifest 视图 — 类型/文件/
  版本/生产者/trace_id/更新时间 + 漂移提示; 选中产出物 → 内容查看 + **版本链 chips**
  (点历史版本读取 history 内容, 可追溯)
- **实时**: 产出物视图 10s 轮询 `GET /api/projects/{id}/artifacts/version`, 版本变化
  自动重载 + "产出物已更新"提示 (数据同步不再靠手动刷新)
- **轻量轮询端点**: GET /api/projects/{id}/artifacts/version ({version, updated_at})
- 存量产出物标 📦存量 (可查看, 未纳入契约)

### 验证

- 后端 artifact_contract 10 passed · 前端 685 passed (含产出物 tab 3 用例) · build 通过
- 与 C-2 (Hermes 引擎接线) 合并同一版本; 版本文件由本侧统一 bump

## [v1.1.109] — 2026-08-26

**产出物契约 C-1（平台级, Manifest + 历史 + 追溯）: 全部项目统一产出物标准**。

### Added

- **Manifest 权威清单** (factory-console/artifact_contract.py):
  每项目 `artifacts.manifest.json` 记录产出物 {type/label/kind/file(当前)/version/
  producer/trace_id/created_at/updated_at/versions[]} — 固定文件名降为默认约定,
  manifest 是权威 (路径可改/可多份/可版本化)
- **历史不丢 + 追溯**: `set_artifact` 更新前旧版归档 `history/<名>.v<N>.<ext>`
  (git 可 diff); 每版带 producer/trace_id/时间戳; `get_artifact_version` 按版本读历史
- **统一写入口**: `set_artifact(project, type, data, {producer, trace_id, file?})`
  校验→归档旧版→写当前→更新 manifest→bump 项目版本 (WebUI 轮询依据)
- **API**: GET /api/projects/{id}/artifacts (manifest 视图) +
  /artifacts/{type}/versions/{v} (历史内容, 404 缺失)
- **CLI**: factory artifacts list|validate (list — 产出物+版本+历史; validate —
  对照 schema 报 missing/legacy/format/history-missing/no-version/drift)
- 存量文件标 `legacy` (存在但未纳入契约, 需 set_artifact 迁移); 漂移排除合法辅助文件

### 验证

- 后端 artifact_contract 9 passed + 相关 111 passed · CLI 实测 ai-factory-self
  与全部项目 · CLI 注册表测试同步 (eval 一致性 P0-10) · 前端零改动 (WebUI 实时 = C-3)

## [v1.1.108] — 2026-08-26

**项目文档管理 (Founder 要求: 项目文档管理/查看)**。

### Added

- **📄 文档 项目页 (左树右看)**: 左侧文档清单 (核心资产 PRD/工程计划/任务拆分 +
  可配目录扫描 docs/), 右侧内容预览 (markdown 简单渲染 / JSON 格式化 / 纯文本);
  未生成/不支持类型 → 诚实提示不伪造
- **后端文档 API**: GET /api/projects/{id}/docs (清单) + /docs/{doc:path} (内容,
  路径安全, 越界 404); 复用 session/board.read_project_doc_content

### Changed

- 项目导航新增 📄 文档 (PRD 之后); 路由 #/project/:id/docs

### 验证

- 后端 docs API 7 passed (清单/内容/嵌套/越界/不支持/缺失) + 相关 49 passed
- 前端 682 passed (含文档页 4 用例) · npm run build 通过

## [v1.1.107] — 2026-08-26

**页面适配窗口大小: 固定 100vh + 内部滚动 (Founder 反馈: 页面/会话栏太长)**。

### Changed

- 壳 (af-shell/workspace/project) 从 `min-height: 100vh` 改 `height: 100vh +
  overflow: hidden` — 页面不再随内容变长, 严格适配窗口
- B 列: 标签条固定, 内容区 `.af-main-scroll` 内部滚动 (滚动不再带走标签条)
- C 列会话栏: 高度受窗口约束 (`min-height: 0` + `.af-chat height:100%`),
  消息区内部滚动, 不再整页拉长

### 验证

- 前端 678 passed · npm run build 通过 · 后端零改动

## [v1.1.106] — 2026-08-26

**去掉侧栏重复 ◆ 品牌标记 (Founder 反馈: 左侧多了一个 ◆)**。

### Changed

- 移除 AfSidebar 顶部 af-sidebar-brand (◆) — 顶栏 AfBrandHeader 已有
  「◆ AI Factory」, 避免双品牌标记

### 验证

- 前端 678 passed · npm run build 通过 · 后端零改动

## [v1.1.105] — 2026-08-26

**预览默认收起 + 不记住上次状态 (Founder A 方案)**。

### Changed

- **中间 B 列预览不再默认展示**: 每次进入默认显示页面, 预览仅在点「👁 预览」
  标签时打开; 切回页面标签即关闭
- **不再持久化预览打开状态**: 移除 af.preview.open 读写 (历史残留键一次性清理);
  侧栏折叠持久化不变

### 验证

- 前端 678 passed (含默认收起/开关断言) · npm run build 通过 · 后端零改动

## [v1.1.104] — 2026-08-26

**AI 员工/技能人话标签 (Founder 反馈: 普通人看不懂内部代号)**。

### Changed

- **Agent 表人话化**: 角色→中文 (产品经理/后端开发/QA 工程师…) + 分组
  (产品/研发/质量) + 一句职责说明 + 状态→可用/忙碌; 内部代号移到悬浮提示;
  注册表单占位符改中文示例
- **Skill 表人话化**: 技能 id→中文 (后端开发/测试/需求分析…) + 分类中文
  (后端/前端/测试/通用); 未知名原样兜底

### 验证

- 前端 678 passed (含设置管理面) · npm run build 通过 · 后端零改动

## [v1.1.103] — 2026-08-26

**设置页表格化 + LLM 新增/编辑 (Founder 反馈)**。

### Added

- **LLM 新增/编辑**: POST /api/config/llm (新增 Provider, upsert) + PATCH 扩展
  (models/base_url/api_key_ref 编辑); api_key_ref 只收 env: 引用 (明文 key 400
  响亮拒绝, D8 铁律); GET/POST/PATCH 均每次 reload 磁盘
- **表格模式**: 设置页从卡片改为**表格全量展示** (LLM/Agent/Skill/MCP/Tool),
  行内管理动作 (启用停用/默认模型下拉/移除) + 新增/编辑表单

### 验证

- 后端 settings 13 passed (LLM 增改/明文 key 拒绝/404) + 权限边界 2 passed
- 前端 678 passed (设置 5 用例含新增 Provider) · npm run build 通过

## [v1.1.102] — 2026-08-26

**设置页完善: LLM/Agent/Skill/MCP 全管理面 (非只读)**。

### Added

- **LLM 管理**: GET/PATCH /api/config/llm (providers.json 管理面 — 启用/停用
  Provider + 默认模型; key 只显示已配置态, 不存明文; GET 每次 reload 磁盘,
  反映 CLI factory config 外部改动)
- **Agent 管理**: POST/DELETE /api/agents (注册/移除, 与 CLI factory agent
  add|remove 同源)
- **Skill 管理**: POST/DELETE /api/skills (注册/移除, 与 CLI factory skill
  add|remove 同源)
- **MCP 管理**: DELETE /api/mcp/connections/{id} (移除, 与 CLI factory mcp
  remove 同源) + 前端连接表单 (注册即连, Mock)
- **前端设置页**: 卡片式管理 UI (Provider 启用/停用/默认模型下拉 · Agent/Skill
  注册表单+移除 · MCP 连接表单+移除+Tool 清单) + 动作结果反馈

### 验证

- 后端 settings 测试 9 passed (LLM 配置读写/MCP 移除/Agent-Skill 管理) +
  权限边界 2 passed (新写路由入白名单)
- 前端 677 passed (含设置管理面 4 用例) · npm run build 通过

## [v1.1.101] — 2026-08-26

**工作区导航方案 A 落地: 7 项 → 3 项 (我的公司/项目/设置)**。

### Changed

- **导航精简 (Founder 方案 A 定稿)**: Dashboard → **我的公司**; 砍掉
  AI Team / Workflow Center / Runtime Monitor / Audit 四个占位页 —
  职责归位 board (8011 开发者/运维控制台); 5180 = 产品工作台
- **路由同步**: #/workspace/team|workflows|runtime|audit 旧 URL 自动回退
  我的公司 (不 404); 保留 #/workspace/manage (项目管理, 左栏 ⚙ 管理入口)

### 验证

- 前端 673 passed (导航/路由/激活态/点击测试同步方案 A) · npm run build 通过
- 后端零改动

## [v1.1.100] — 2026-08-26

**修复: 目录项目收藏 404 (Founder 实测 ai-factory-self)**。

### Fixed

- **PATCH /api/projects/{id} {starred} 对目录项目不再 404**: 真实工作区目录项目
  (projects/<id>/product.json, 无 org 记录) 首次写操作 → 惰性注册 org Project
  (无事件, 保留生命周期状态); starred/archived 统一落 org (单一事实源,
  消除目录项目收藏 404 / 双轨漂移)。列表状态保留 (lifecycle 同源映射)。

### 验证

- 回归测试 +1 (目录项目 star→列表 starred=true→落 org→状态保留)
- 实测: PATCH ai-factory-self {starred:true} → 200 · 列表 starred=true ·
  org 落库 · 无重复条目 (11 项目) · project_draft/web_adapter/lifecycle 相关
  162 passed

## [v1.1.99] — 2026-08-26

**布局 v4 (K-7d) + AI 会话栏 (K-7e) — 三栏 A|B|C 定稿落地**。

### Added

- **三栏布局 v4 (Founder 定稿 A|B|C)**: A 列 OS 导航 / B 列数据工作区
  (预览窗口并入 B 列标签页) / C 列 AI 会话栏 (可收起、可常驻) + 底部状态栏
  (模型/作用域/上下文 tokens/版本) + 快捷键 (Cmd+B 切侧栏 · Cmd+J 切会话 ·
  Cmd+K 新建会话); 各栏收起状态持久化
- **AI 会话栏 (C 列)**: 作用域选择 (公司/项目) + 多会话线程 (新建/改名/归档/
  自动标题) + 真实对话 (项目级注入事实卡) + 上下文指示器 (消息数/tokens/压缩
  诚实标注 K-7f 待接入) + 发送失败诚实提示
- **后端会话 API**: GET/POST /api/sessions · PATCH /api/sessions/{id} ·
  GET/POST /api/sessions/{id}/messages (console_sessions.py — 会话+消息
  JSON 存储, 线程安全, 失败安全; LLM 回复复用 ReasoningProvider 装配链,
  不可用 → 诚实降级不假装)

### Changed

- 移除 v3 中央区内 Composer 与右栏独立预览 — 预览入 B 列标签页, 对话入 C 列

### 验证

- 后端: console_sessions 测试 17 passed (存储/回复/HTTP 400/404)
- 前端: 679 passed (含会话栏 7 用例) · npm run build 通过
- 数据真实: /api/projects 11 项目 · 会话 API 落盘 console_sessions.json
  · LLM 不可用 → 诚实降级提示

## [v1.1.98] — 2026-08-26

**WebUI 工作台主页面 (我的公司首页) — K-7b 首页定稿**。

### Added

- **#/workspace 默认页改为"我的公司"首页** (AfCompanyHome, 替换信息过重的 AfDashboard):
  - ⭐ 关注项目: 收藏 + 近期有更新 (近 7 天) 才展示, 无近期更新不占位; 点击卡片进项目
  - 📋 我的待办: 公司级聚合待审批 (GET /api/approvals?pending_only=true) + 项目级过滤
    (下拉: 全部(公司) / 按项目; 有 project_id 时按项目切)
  - 诚实空态: 无收藏/无待办 → 明确提示; 质量待检/成本告警 API 待接入 → 诚实占位不伪造

### 验证

- 前端 672 passed (0 failed) · npm run build 通过 (tsc + vite) · 数据真实:
  /api/projects 11 项目 + /api/approvals?pending_only=true 1 条真实待审批 (APR-001)
- 后端零改动 · 前端测试 +5 公司首页用例 (关注/过滤/空态/失败安全); shell/入口/路由用例随新首页更新

## [v1.1.97] — 2026-08-26

**项目收藏/关注 + 左栏"收藏/最近3/全部" + K-7b 累积**。

### Added

- **项目收藏 (Founder #1)**: org Project 加 starred 字段 (方案 A: 项目属性, 落库
  org/projects.json) + PATCH /api/projects/{id} {starred} + ProjectSummary 返回 starred
- **左栏项目展示**: 收藏 ⭐ 区 (置顶) + 最近 🕐 3 个 (last_activity) + 全部 📋 (可折叠,
  默认收起) — 项目行 ⭐ 星标切换 (AfSidebar)
- K-7b 累积: 左栏 OS 树 / 右栏预览窗口 / 项目首页 (生命周期+Todo 列表⇄泳道+运维) /
  对话分域 / 刷新+自动轮询

### Fixed

- service.list_projects org 循环补 starred (org-only 项目之前漏填)

### 验证

- 契约测试 +3 (star/unstar/落库/无事可做 400) · console+api 回归 0 新增失败 ·
  前端 667 passed · 实测 PATCH starred 生效 · v1.1.97


### Added — K-6 项目级 RAG (战役第六战役)
- **M5-2/B-8 KnowledgeStore**: 项目文档入库 (README/docs/PRD/工程/质量/经验 → 片段+元数据索引,
  复用 board read_docs_config 扫描, 索引独立 .factory_rag 零污染) + 三级分档
  (raw 原始片段 / summary 章节摘要·目录 / knowledge 跨文档知识条目) + 增量重建
  (mtime, 失败安全: 坏文件跳过)
- **确定性检索**: 词频/TF 打分 (ASCII 词 + CJK 二元子词, 纯规则零依赖, 同输入同输出,
  reason 可解释 "命中关键词 X(tf=N) in 文件 F 片段 C"); embedding/LLM 仅可选接入
  (scorer 注入点, 规则始终可用, 诚实标注)
- **M5-3 外挂适配器接口先行**: ExternalKnowledgeSource Protocol + MockExternalSource
  (确定性) + 注册表 + 配置 providers.external_rag (未配置 → 空不崩); 复用
  RetrievalSource.EXTERNAL_RAG 挂点
- **问答入口**: `factory rag query <项目> <问题>` (确定性片段 + 引用源文件+片段+score+reason)
  + `factory rag index <项目> [--incremental]` + `factory rag sources`;
  API `POST /api/rag/query` + `GET /api/rag/sources` (只做后端, 禁碰前端)
- **F-11 知识沉淀**: PRD/工程/经验入索引 (raw/summary/knowledge 分档; 跨项目检索接口预留)
- **E-5 检索回路**: RAG_QUERY 审计事件带 trace_id (K-4 contextvar 自动填充, 检索动作可溯源)

### Honest Notes
- 真实 embedding/LLM 检索未接入 (接口就绪, 纯规则为主); 二进制文档 (doc/docx) 与
  损坏文件无法确定性检索 → 跳过并记录 (失败安全, 不中断)

## [v1.1.95] — 2026-08-25

### Added — K-5 评测体系渐进 (战役第五战役)
- **P0-1/C-1 七维评测第一版**: `factory eval` — 正确性/鲁棒性/一致性/性能/安全/长期/用户价值 7 维,
  每维 ≥1 可断言评测项 (复用 H-1/K-2/K-3/K-4 数据), L0-L3 等级判定 (第一版 L0/L1 可判)
- **P0-5/C-6 发布门自动化**: `factory eval --gate patch|minor|major` — patch=L0 · minor=L0+L1;
  失败 → rc 1 明确阻断 [E4102]; --check 只读不阻断 (不破坏现有版本流程)
- **P0-4/C-5 长跑+并发**: 多项目并发 trace 隔离断言 (K-4); scripts/smoke_longrun.py 长跑冒烟 (可配置);
  scripts/smoke_24h.py (待长跑如实标注)
- **H-1 整体流程评测**: 创建→发现→PRD→工程→审批→执行→证据→交付 端到端 fixture, 每节点衔接断言 + J-1 状态投影
- **F-10 测试覆盖度**: scripts/coverage_report.py (stdlib trace, 模块级报告, 不设达标线)
- **M5-7 错误码表**: docs/error-codes.md 集中表 + 主要错误路径有码
- **C-4 中间盲区核对**: docs/eval-blind-spots.md (K-2 已覆盖 vs 仍盲, 如实)

### Fixed
- eval 评测项语义: 无上下文路径的空 trace_id 属 K-4 设计允许 (audit_trace 诚实判定 未覆盖/通过)
- 发布门 registry 核对需真实 repo_root (CLI root = 真实仓库)

## [v1.1.94] — 2026-08-25

**/help CLI 区逐命令树 + 组内对齐 (v1.1.93 补)**。

### Changed

- CLI 命令区从"每组合一行"改为 **逐命令树**: 每个子命令单独一行 + 说明
  (start/stop/... 29 个命令全部带说明, 取自 cli_factory build_parser)
- 树渲染组内对齐: 有说明的项按 CJK 显示宽度补空格 (命令列对齐, 裸续行不参与)

### 验证

- help 契约全过 · console 回归 0 新增失败 · v1.1.94


**/help 树形分层重构 (v1.1.91/92 再版)**。

### Changed

- /help 从"平铺一坨"改为 **tree 结构分层**:
  - 💬 自然语言: 6 组 (创建/产品管线/项目/变更审批/追踪) 树形展开, 每组示例带说明
  - 📁 系统命令: 4 组 (会话/项目/面板/工具), /board 子命令嵌套展示
  - 🛠 CLI 命令: 5 组每组合一行 (服务诊断/项目管理/资产员工/生产执行/系统), CJK 对齐
- 顶层 `📖 AI Factory 帮助` 收口; 组/项用 ├─/└─/│ 分支连接

### 验证

- 既有 help 契约 (系统命令:/CLI 命令/自然语言/命令名/退出会话) 全过 · console 回归 0 新增失败 · v1.1.93


**/help CLI 组标签对齐 (v1.1.91 补)**。

### Fixed

- CLI 命令组标签按 CJK 显示宽度对齐 (系统/项目管理 等短标签不再错位)

### 验证

- console 回归 0 新增失败 · v1.1.92


**/help 完整化 + 布局优化**。

### Fixed

- **命令完整**: 补 需求变更/架构审批门/审计追踪(K-4 trace) 等自然语言示例;
  CLI 命令按 5 组列全 (start/stop/.../update/init + project/create/demo/run +
  agent/skill/mcp/tools/task + exec/approval/evidence/repo/workload/router +
  audit/rag/llm/todo/help); /board 子命令单行列出 (mainline/graph/chain/timeline/
  replay/project/quality/cost/report/done/unmark/sync/docs/default)
- **布局对齐**: CJK 显示宽度感知 (east_asian_width) — 中文/命令列对齐不再错位;
  分区标题 (自然语言/系统命令/CLI 命令) 分组清晰; 系统命令显式排序 (help/status/
  project/board/cost/preview/exit) 且未列出的注册命令不丢

### 验证

- 既有 help 契约测试全过 (系统命令:/CLI 命令/自然语言/命令名/退出会话) ·
  console 回归 0 新增失败 · v1.1.91


**K-4 trace_id 贯穿 (S10-120)**: 一次请求从入口到执行全程同一 trace_id — 审计/执行/成本可追踪; audit_trace 决策链真正可用。

### Added

- **trace 上下文模块** (`audit/trace_context.py`): ContextVar (线程安全, with 退出自动恢复 — 不跨请求泄漏) — `new_trace_id()` (uuid4 hex) / `get_trace_id()` / `get_correlation_id()` (失败安全 → "") / `set_trace` / `trace_context` (context manager) / `child_correlation(trace_id)` (父子关联: 子动作 correlation = `trace_id:n`, 进程内递增线程安全)
- **AuditEmitter.emit 自动填充** (`audit/audit_emitter.py`): trace_id/correlation_id 未显式传 (或空) → 读 contextvar 自动填充 (64 发射点零改动; 显式优先不覆盖; 无上下文 → "" 旧行为零变化)
- **入口生成 trace_id**: InteractiveSession._dispatch 每用户输入包 trace_context (递归/重分发保持同一 trace) · FastAPI 请求中间件每请求 trace_id (X-Trace-ID 可选覆盖 + 响应回带) · cli_factory 命令执行入口包 trace_context · agent_runtime 执行入口包 trace_context (有上下文继承 — 链路不分裂; 策略子任务 correlation 关联)
- **执行/成本链路**: execution_records 记录 += trace_id (contextvar) · CostLedger.record 缺省 trace_id 读 contextvar (显式优先)
- **audit_trace 激活**: 审计事件 trace_id 已填充 → 审计追踪/决策链 (S10-069 现成 action) 真正可用
- **F-9 最小面**: 关键调试日志带 trace_id (审计发射 + 会话分发入口 + 执行入口 — 不铺开)
- 契约测试: `test_s10_120_trace_chain.py` 14 用例 (设计 §2 契约 1-9 + 版本断言)

### Changed

- 无上下文路径 → trace_id="" (旧行为零变化, 不伪造不泄漏); 审计封存/哈希/血缘语义不变
- 既有测试更新: 版本断言 1.1.89 → 1.1.90 (test_s10_074/test_s10_103/test_s10_104/test_s10_105/test_s10_109/test_s10_111/test_s10_119/test_confirmation_intelligence)

### 验证

- 契约测试 14 passed · 聚焦回归 (audit/session/actions/cost_ledger) 全绿 · tests/console + tests/api 全量 0 新增失败 · v1.1.90

## [v1.1.89] — 2026-08-25

**K-3 学习闭环 (S10-119, 主线 M4 全 6 项)**: 让 Agent 变强且可控 — 经验闭环 + 学习护栏 + 决策记忆 + 成本告警 + 画像分配 + L4 快照完整化 + E-2/E-3 评估驱动闭环。

### Added

- **M4-1/B-7/E-1 经验闭环** (`memory/learning_loop.py`): 执行完成后自动经验入库 (`on_execution_complete` — 护栏检查 → 确定性提取 → ExperienceStore.add, 低质量不写诚实返回) + 下次同类任务引用 (`resolve_for_task` → ExperienceHit{experience_id, summary, reason: "引用经验 X 因为 Y (相似度 0.xx)", dominant}) + 执行 prompt 注入 "引用经验 X 因为 Y" (reason 可解释); 闭环可断言: 两次同类任务 → 第二次引用第一次
- **M4-2 学习护栏** (`memory/learning_guards.py`, 最高优先级): 总开关 (默认 True, 配置可关 → 学习/引用零行为变化) / 样本可信度 (n>=3 才主导, 低样本降权) / 样本质量 (q>=0.5 才写入) / 预算上限 (超限阻断+告警) / 学习状态快照+一键回滚 (画像/经验/决策记忆)
- **M4-3 决策记忆回流 E5** (`memory/decision_memory.py`): 审批 (approved/rejected) → DECISION_LEARNED 审计 → 组织记忆落盘 decision_memory.json {decision_id,type,outcome,context,learned_at} → 下次同类审批显示 "历史同类决策: N 次, 批准率 X%" (approve_project_plan + review_approve/reject 接入)
- **M4-4/D-6 成本告警闭环**: CostLedger usage → aggregate (cost_by_task/agent) → BudgetEnforcer.check → 超预算告警 (BUDGET_WARNING/BUDGET_BLOCKED 审计, orchestrator + budget.check_and_alert) + 阻断 (execute_task 执行前检查) → 回填 (cost 关联 task/agent); /board cost <project> + /cost 成本可视化 (只读)
- **M4-5 画像优先分配 + 负载均衡** (`capability_router`): 排序扩展 (priority desc → persona desc [agent_profiles] → load asc → quality desc → version desc → id); 画像分来源 agent_profiles.json (trigger_learning/学习闭环自动刷新, 失败安全无画像 → 中性); K-1 基本逻辑不动
- **M4-6 L4 快照完整化** (`execution_replay`): 非 git 工作区目录级快照 (复制基线到 .factory_snapshots/<exec_id>-<ts>/ → 还原清空+复制回); git 路径沿用受限版; 不可快照 → ReplayError 明确
- **E-2/E-3 评估驱动修复/优化闭环** (`session/eval_loop.py`): 低分任务 → 失败分类 (确定性规则) → 修复建议 → 应用 (repair_task 机制) → 复评 → 分数提升断言 (至少一条可断言闭环)

### Changed

- `execute_task`: 执行前预算阻断检查 (项目预算 block → 明确错误) + 执行完成自动学习/画像刷新/成本回填 (全部护栏内失败安全)
- `memory_learn` / LearningLoop: Agent 画像刷新落盘 agent_profiles.json (capability_router 数据源)
- 契约测试: `test_s10_119_learning_loop.py` 29 用例 (设计 §2 契约 1-13 全覆盖)
- 既有测试更新: capability_router reason 排序文案 (M4-5) · execution_replay L4 非 git 快照契约 (原"需 git 仓库"改为"非 git 目录级快照") · 版本断言 1.1.89

### 验证

- 契约测试 29 passed · 聚焦回归 (memory/actions/capability_router/execution_replay/budget/cost_ledger/board) 全绿 · tests/console + tests/api 全量 0 新增失败 · v1.1.89

## [v1.1.88] — 2026-08-25

**Web board 质量视图接线 (K-2 补)**: render_quality 已交付但 Web 路由未接。

### Added

- **/api/board?view=quality**: fastapi_adapter 接线 (之前 fall-through 到项目首页)
- **board 导航 📊 质量 tab**: 与 项目/任务树/…/员工 并列; CLI /board quality 早已可用

### 验证

- 契约测试 +1 (nav 含质量 tab/路由) · 回归 console+api 全绿 · v1.1.88


**发现对话上下文保持 + LLM 失败响亮报错 (S10-118, Founder 实测修复)**。

### Fixed

- **逃生不再断上下文**: 发现/确认中 "项目列表" 等逃生 (passthrough) 从"清空产品流程"
  改为"挂起"——product_intent/pending 现场保留, 处理完其它意图可继续 (Founder:
  "你把控一下"后上下文断); 重分发临时摘除 product_intent 防递归
- **委托/求助口语全覆盖**: HELP_KEYWORDS 扩充 把控系 (把控/你把握/把一下关) +
  建议系 (给我一点建议/给建议/提点建议/给个方向) + 委托系 (你来想/帮我想想/你拿主意) —
  无 LLM 路径不再把 "你把控一下"/"给我一点建议" 当字段值污染 (之前被填进 core_features)
- **LLM 分流提示词强化**: discovery_intelligence help_request 示例加
  "你把控一下/给我一点建议/你来定方向", 明确 query 不含委托/求助 (防 LLM 误判)

### Changed (Founder 策略)

- **已配置 LLM 必须走 LLM, 失败响亮报错** (不再静默降级):
  - 未配置 (ReasoningUnavailable) → 确定性兜底保留
  - 已配置但调用失败 → 用户可读报错 (网络/超时/限流429/服务端5xx/鉴权401-403/
    输出无法解析), 分类确定性 (_classify_llm_error 沿异常链+http状态码+关键词)
  - 报错后发现/确认现场保留, 用户重发即可继续
- 契约测试同步: 旧"LLM 失败→规则兜底"契约改为"可读报错+状态保留"
  (test_s10_118_discovery_context_keep.py 11 用例 + 既有测试同步)

### 验证

- 契约测试 11 passed (口语覆盖/机械不污染/逃生挂起/失败报错/未配置兜底/分类单元/重试可续)
- 回归 tests/console 5299 passed / 0 failed + tests/api 84 passed
- 版本断言同步 v1.1.87


**K-2 执行质量分 + 优选 (S10-117)**: C-2 执行质量分落盘 + C-3 T5.3 多候选优选启用 + B-5 低分失败策略闭环 + B-6 PRD/工程计划质量评估。

### Added

- **执行质量分 (C-2)**: `session/execution_quality.py` — 确定性评分器 (纯规则不调 LLM):
  ExecutionQuality{score, dimensions, evaluator_version, scored_at, rules} + score_execution
  (复用 T5.3 五层思路: validation 硬条件 + patch/scope/risk/coverage; 失败 → 总分封顶 0.35
  < 低分阈值 0.5); 评分器异常 → score=None + reason (失败安全不阻断); 落盘
  execution_records.json quality 字段 (score/dimensions/version/scored_at + rules, 可审计)
- **多候选优选启用 (C-3)**: AgentRuntime 多候选路径评估明细透出 — ExecutionResult.evaluation
  (selected_candidate_id / ranking / score_breakdown / rejection_reason); 全候选失败 →
  rejection_reason 非空 (诚实拒绝不静默选最差); 单候选路径零变化 (strategy off → evaluation={})
- **失败策略闭环 (B-5)**: orchestrator._execute_with_retry 附加钩子 — 低分
  (quality.score < 0.5) 且重试耗尽 → 经 K-1 capability_router 查替代资源 → 有替代 → 换资源
  再试一次 (resource_switched + reason); 无替代 → 诚实报告 "低分无替代资源"; 不改 pass/fail
  基本行为, 不无限重试
- **路由回写**: CapabilityResource += quality_score (Optional[float], None 中性);
  route() 排序 key 扩展 (priority desc → quality desc [None 中性] → version desc →
  load asc → id); K-1 无分 fixture 行为零变化
- **PRD/工程计划质量评估 (B-6)**: score_prd + score_engineering (复用 M3d 六维思路,
  确定性规则); 落盘 PRD.quality.json + engineering.quality.json (prepare_project 侧, 失败安全)
- **展示入口 (只读)**: `/board quality [项目]` — 最近执行质量 (score/dimensions/version)
  + PRD/工程质量; 渲染后 mtime 不变 (只读铁律)
- **契约测试**: tests/console/test_s10_117_execution_quality.py (≥10: 质量分确定性/失败安全/
  多候选优选/单候选零变化/低分换资源/路由回写/PRD+工程评分/展示只读/注册表门禁)

### Changed

- 版本 1.1.85 → 1.1.86 (pyproject + FEATURES.md + 版本断言同步)
- 待办清单: K-2 / C-2 / C-3 / B-5 / B-6 标 ✅ (战役 K-2 第二战役完成);
  战役规划状态追踪 K-2 ✅ v1.1.86
- 既有测试同步: 版本断言 (1.1.86) / test_s10_116_campaign_plan (K-2 ✅)

### 验证

- 契约测试 tests/console/test_s10_117_execution_quality.py 全绿 · 聚焦回归
  (actions/agent_runtime/evaluator/orchestrator/capability_router/board + 既有执行/路由/
  评估测试) 全绿 · 全量 tests/console + tests/api 0 新增失败 · 实测: 成功/失败/低质量三类
  fixture 分数 / 多候选 ranking+rejection / 低分换资源 / PRD+工程评分 / board quality 只读


## [v1.1.85] — 2026-08-25

**K-1 能力路由 + 员工管理 (S10-116)**: B-1~B-4 统一能力路由层 + A-2 员工 tab + A-3 MCP 管理 + F-4 提示词版本化。

### Added

- **统一能力路由层 (B-4)**: `session/capability_router.py` — CapabilityResource{id,type,capabilities,
  status,load,priority,version} + CapabilityRequest + RouteDecision + CapabilityRouter.route
  (确定性: capabilities 交集 → priority desc / version desc / load asc / id 排序 → 首个 ready;
  reason 可解释命中集合 + 排序依据; 纯规则不调 LLM; status/load 只挂字段, K-2/K-3 不实现)
- **skill 路由 (B-1)**: objective 关键词规则表 → 能力需求 → 路由选中 skill; developer.py 注入改造
  ("全部 skills" → "路由选中 + reason"); 无匹配 → 全注入兜底 (向后兼容零变化)
- **agent 路由 (B-2)**: select_agent 升级 — params.agent_id 优先 + 旧关键词逐字节保留
  (前端/flutter/ui/界面 → flutter-dev) + 新 capability 匹配 (多 agent 且关键词未命中);
  AgentRegistry.to_capability_resources (capabilities = skills + supported_tasks 推导, 只读)
- **MCP 路由 + 管理 (B-3/A-3)**: objective 工具关键词 → MCP tool 选择 (Mock 诚实标注);
  `factory mcp list|connect|remove` CLI — 复用 ConsoleService MCP API (remove 新增
  remove_mcp_connection); CLI 注册表同步 (P0-10)
- **board 员工 tab (A-2)**: `_board_nav` 新增 "👥 员工" 视图 (`/api/board?view=employees`) —
  只读渲染 Agent 列表 (装配 ✅/⚠️缺skill) + Skill 列表 + 7 角色定义 (真引擎/规则 + 装配状态)
  + 缺失提示; 渲染后 mtime 不变 (只读铁律)
- **提示词版本管理 (F-4)**: ROLE_DEFINITIONS 8 角色 prompt += prompt_version=1.0.0 /
  changed_at / change_summary (可追溯, 不改 prompt 语义)
- **契约测试**: tests/console/test_s10_116_capability_router.py (≥10: 路由确定性/reason/
  skill 注入/agent 旧行为+新匹配/MCP 路由+CLI/board 只读/F-4/注册表门禁/回归)

### Changed

- 版本 1.1.84 → 1.1.85 (pyproject + FEATURES.md + 版本断言同步)
- 待办清单: K-1 / B-1~B-4 / A-2/A-3 / F-4 标 ✅ (战役 K-1 第一战役完成)
- 既有测试同步: test_console_cli (mcp 子命令注册表) / test_s10_116_campaign_plan
  (K-1 ✅) / 版本断言 (1.1.85) / test_s10_114_skill_activation (注入改路由选中断言)

### 验证

- 契约测试 tests/console/test_s10_116_capability_router.py 全绿 · 聚焦回归
  (agents/actions/board/cli/expert_factory + 既有 agent/skill/mcp/board 测试) 全绿 ·
  全量 tests/console + tests/api 0 新增失败 · 实测: 路由确定性+reason / 注入改造 /
  factory mcp list|connect|remove / board 员工 tab 渲染后 mtime 不变


## [v1.1.84] — 2026-08-25


**战役规划 K 系列落盘 + board 可见**。

### Added

- **战役规划 (统一路线)**: A~J 周边 + 主线 M4-M7/P0 合并为 10 个战役 (K-1~K-10) —
  唯一事实源 docs/战役规划-统一路线.md (重叠合并表/总览/每战役验收标准/执行规则/状态追踪)
- **待办清单 K 系列分组**: board 首组可见 (K-1 能力路由 → K-10 远期), 旧编号 A~J/M 保留可追溯
- **board 解析扩展**: _parse_backlog 支持 K- 前缀, 战役卡片渲染
- **总体计划同步**: 当前状态/进行中/路线图/状态追踪 更新至 v1.1.84 + K 系列

### 验证

- 契约测试 tests/console/test_s10_116_campaign_plan.py 4 passed
  (K 系列解析/文档存在/旧编号不丢失/board 渲染) · 版本断言同步 v1.1.84


**J-1 生命周期状态单一来源 (S10-115)**: project.json.status 为唯一事实源, 消除
product.json / project.json / execution_state.json 三轨漂移（写侧统一入口 + 防回退 +
存量对账; 读侧 board 对账可见）。

### Added

- **统一写入口 set_project_lifecycle** (`session/lifecycle_store.py`): 原子写三处
  (project.json.status canonical + product.json.status + execution_state.json.lifecycle)
  + 词汇校验 (∈ Lifecycle.STATUSES) + 防回退守卫 (单调前进, force=True 仅显式例外)
  + 失败安全 (损坏文件不崩不臆造)
- **存量对账** `factory project reconcile [--dry-run]`: canonical 判定
  (①project.json.status ②product.json.status 映射 ③execution_state.lifecycle
  ④全无/非法 → 跳过如实报告) + 修复前每项目快照 `.status_snapshot_<ts>.json` (三处原值)
- **LEGACY_STATUS_MAP**: project_created→product_defined / prd_ready→engineering_ready /
  draft→idea / confirmed→product_defined (对账/守卫兼容)
- **状态一致性对账 (J-1 读侧)**: board 新增只读三轨对账 — 每个项目读
  product.json / project.json / execution_state.json 三处状态, 以 project.json.status
  为事实源 (canonical), product.json / execution_state 为镜像; 漂移/缺失实时标红
- **监控面板**: 主线面板新增「⚠️ 状态一致性」区块 (漂移数 + 缺 project.json 数 +
  逐项目漂移明细, 如 日记: product=prd_ready ≠ project=development)
- **契约测试**: tests/console/test_s10_115_lifecycle_single_source.py (写侧 ≥8:
  写点枚举/一致性/防回退/对账修复/词汇映射/统一入口/board 读取/回归) +
  tests/console/test_s10_115_board_consistency.py 12 用例 (读侧)

### Changed

- **写点全部改走统一入口**: orchestrator._set_lifecycle 委托 (加 execution_state 同步 +
  守卫) · 执行状态/验收 (accept_project) 三处同步 · actions.approve_project_plan 审批通过
  改走 set_project_lifecycle · service.confirm_project 保留 org 镜像 lifecycle=confirmed,
  status 缺省 → 统一入口补 canonical=product_defined
- **generate_prd 防回退**: canonical 存在 → 不写 product.status (development 项目重生成
  PRD 不再被降级); 无 canonical → product.status=engineering_ready
- **create_product**: product.status 落盘值 project_created → product_defined (Lifecycle 词汇)
- **展示口径统一**: 项目列表/状态分布/生命周期验收阶段全部改读 canonical
  (project.json.status 优先, 回退 product.json), 不再直接展示 product.json 漂移值

### Fixed

- 状态双轨漂移不再被掩盖: 日记 (product=prd_ready vs project=development) 等实测漂移
  对账可见 + 可一次性确定性修复 (快照先行, 只修可判定)

### 验证

- 写侧契约 ≥8 passed · 读侧契约 12 passed · 回归 tests/console + tests/api 0 新增失败
  · 版本断言同步 v1.1.83


**M5-1 执行重放引擎 + Skill 真调用**。

### Added

- **M5-1 执行重放引擎 (S10-113)**: ReplayEngine — dry-run 时间线重建
  (execution_records + audit 事件按 timestamp 合并, 耗时 = 相邻时间戳差) /
  re-exec 同输入重跑 (input_snapshot 还原 → 新 exec_id 记录) / compare 对比报告
  (步骤/结果/耗时/产物真实 diff, --save 落盘 docs/sprint10/) / L4 快照回滚
  (项目目录 git 快照, 受限: 需 git 仓库项目目录)
- **执行记录 input_snapshot**: execute_task 记录补全完整输入 (intent/action/
  params/context 摘要) — 未来可重放; 旧记录无快照 → re-exec 明确报错不瞎跑
- **入口**: /board replay <exec_id> (--re-exec / --compare <id2> / --save) +
  自然语言 "重跑 <exec_id>" → replay_exec 意图路由 (intent.py + router.py)
- **Skill 真调用**: 外部注册 skill 装配生效 + 执行注入 prompt (不再只是标签)

### Fixed

- **_default_skill_exists 合并 skills.json**: 外部注册 skill (factory skill add)
  装配校验生效 (之前只查内置 EXPERT_SKILLS/core, 外部注册无效)
- **执行注入 skills**: cli.cmd_exec_run 读 agents.json → AgentInstance.skills →
  developer.build_prompt 注入 "You have skills: ..." (Agent 能力声明进 prompt);
  无 skills 向后兼容 (prompt 不含注入)
- AgentInstance 加 skills 字段

### 验证

- 契约测试 tests/console/test_s10_113_execution_replay.py 25 passed
  (dry-run/re-exec/对比/记录完善/入口/L4) · 版本断言同步 v1.1.82 ·
  全量 console+api 0 新增失败
- 6 新契约测试 (外部skill装配/内置/注入/兼容/AgentInstance/cli读取) · exec+console 相关 1327 passed

## [v1.1.81] — 2026-08-25

**P0-10 注册表一致性 + P0-11 对称路径一致性（防遗漏机制）**。

### Added

- tests/console/test_s10_112_registry_consistency.py — 5 类注册表一致性测试
  (CLI 命令/意图/action/事件/API, 数据从实现动态读取, 断言两两一致)
- tests/console/test_s10_112_symmetric_paths.py — 对称路径一致性测试
  (conversation vs discovery 同输入同推进/同字段; CLI vs API 双入口:
  agent/skill/project list ↔ /api/agents|skills|projects, board 文档 ↔ docs 配置命令)

### Fixed

- 版本漂移: pyproject 1.1.79 vs CHANGELOG v1.1.80 (1a8ecee 声称 v1.1.80 但
  pyproject 未同步) → pyproject 同步 1.1.81
- 意图注册表漂移: 37 个关键词意图只靠 S10-082 同名兜底, 未显式声明路由
  → DEFAULT_ROUTES 补全显式同名映射 (路由解析逐字节不变)
- Action 敏感注册表漂移: registry metadata sensitive=True 的 accept_project/
  org_manage/repair_task/team_execute 只声明未强制 (会话确认门漏接, 与各自
  docstring "确认门" 口径漂移) → 补入会话确认门; create_project action 已强制
  但 registry 未标 sensitive → 补标 (create_product 会话内由 conversation 接管)
- 事件注册表漂移: delivery.py 实际发射 PATCH_APPLIED/CODE_VALIDATED/
  DELIVERY_COMPLETED/DELIVERY_FAILED 但漏注册 → AuditEmitter 静默丢弃
  → 补入 EVENT_TYPES (审计记录与实现一致)

### 验证

- 2 个新测试文件 17 passed · 版本断言同步 1.1.81 · 全量回归 0 新增失败

## [v1.1.80] — 2026-08-25

**A-1 补齐 7 角色 Skill 资产（员工管理计划第一步）**。

### Added

- skills.json 补齐 11 个 skill: product_management/requirement_analysis/
  product_documentation/market_research/competitive_analysis/ux_design/
  software_architecture/software_testing/test_planning/frontend_development/
  backend_development (现 12 个含 flutter)
- 7 角色 (pm/market/competitive/ux/architect/qa/prd) ExpertFactory 装配全部
  成功 (不再缺 skill 走兜底)

### Fixed

- 测试隔离: TestAgentSkillManage 注入 data_dir 到 tmp (修复此前写污染
  ~/.factory/skills.json)

### 验证

- 3 相关测试 passed · 装配验证 7/7 ✅

## [v1.1.79] — 2026-08-25

**Board 待办清单解析支持任意章节（员工管理计划可见）**。

### Changed

- _parse_backlog 章节正则支持任意组 (M2/员工管理/长期...), 任务 id 支持 A- 前缀;
  员工管理路线计划 (A-1~A-4) 出现在 board 周边任务
- 修复章节正则 (长期/企业级 不再被误拆成 "长")

### 验证

- 170 相关回归 passed · 全量回归 0 新增失败

## [v1.1.78] — 2026-08-24

**M3 收尾三件套（S10-111）: ux/qa 真引擎 + PRD 深度化 / ChangeControl 需求变更回流 / 工程计划架构审批门**。

### Added

- **M3-5 UX/QA 真引擎 + PRD 深度化**: ux/qa 角色从模板占位改真引擎 —
  ux 按 ProductIntent(user/core_features/platform) 生成每功能具体用户流程
  (3-5 步) + 页面结构 + 信息架构; qa 生成单元/集成/E2E/安全/性能五层测试 +
  每功能用例方向 + 验证命令; PRD 追加 "User Stories" (每功能一条) +
  "Acceptance Criteria" (每功能 2-3 条) — 无 LLM 确定性兜底真实产出
- **M3-6 ChangeControl 需求变更回流**: `/project change <slug> "加导出"` +
  自然语言 "给XX项目加个导出功能" → propose (规则解析 request/reason) →
  impact (关键词匹配 PRD 章节/任务/依赖, 手算可枚举 + 过度波及收敛) →
  ConfirmationGate y/N → y: PRD v2 (变更记录) + DecomposeEngine 拆变更 →
  新任务合并 tasks.json/plan.json (+execution_plan.json); n: 不写不建, rejected
- **M3-7 工程计划架构审批门**: prepare_project → status=pending_arch_review +
  arch_review{summary, requested_at}; "批准工程计划" y → execution_ready;
  n → pending + feedback (重新 prepare 覆盖); execute_project 非
  execution_ready 明确阻断 "工程计划待架构审批"

### 验证

- 14 新契约测试 (M3-5/6/7 各 ≥3 + 版本 v1.1.78) · 全量回归 0 新增失败

---

**Agent/Skill 管理命令 + API（Founder: agent list 不能执行, help 不全, 需管理）**。

### Added

- **agent/skill 子命令**: factory agent list|add|remove (--id --role --skills) ·
  factory skill list|add|remove (--id --name --category) — 修 agent list 报错
- **help 补全**: factory help 加"常用命令用法"区块 (agent/skill/tools/llm/project 等)
- **API**: GET /api/agents · GET /api/skills (清单, 与 CLI 同数据源)
- 修复 agents.json/skills.json 嵌套读取 + 写入循环引用

### 验证

- 3 新契约测试 (agent add/list/remove + skill add/list + help 用法) · 全量回归 0 新增失败

## [v1.1.77] — 2026-08-24

**项目清单多维度（Founder: 管线/状态含义不清, 是否考虑其他维度）**。

### Changed

- /project 清单列: 旧 "管线(artifacts数)/状态(project.json)" → 新
  "生命周期(5/11 卡点)/任务进度(x/y)/最近更新"
- 复用 board 生命周期判定 + 任务进度 (统一数据口径)
- PRD 列保留

### 验证

- 1 新契约测试 (多维度 brief) · 全量回归 0 新增失败

## [v1.1.76] — 2026-08-24

**项目删除功能 + 删除审批 + AI 执行记录展示（Founder 测试反馈）**。

### Added

- **项目删除**: 意图解析 ("删除全部未命名产品"/"删除项目 X") + actions.delete_project
  (删目录 + org 记录 + PROJECT_DELETED 审计) + /project delete <id|全部未命名> 命令
- **删除审批**: delete_project 纳入 ConfirmationGate 敏感集合 — 删除前显示
  目标清单 + y/N 确认 (危险操作)
- **AI 执行记录**: 单项目视图加"⚙ AI 执行记录"区块 (execution_records.json
  按项目任务名过滤, 显示时间/Agent/任务/结果)

### 验证

- 5 新契约测试 (删除全部未命名/单个/未知/执行记录过滤/生命周期含执行记录) · 全量回归 0 新增失败

## [v1.1.75] — 2026-08-24

**Board 文档树修复: 去重 + 目录上文件下 A-Z + 排除示例目录（Founder: 乱）**。

### Fixed

- **树渲染重复 bug**: 目录节点渲染了两行 dkids (子内容双份, 嵌套指数膨胀
  647→3834), 删除重复行, 渲染文件数 = 实际文件数
- **排除示例/演示目录**: demo/ examples/ unused/ 不再作为文档混入
- **排序确认**: 同级目录在上(名排序) 文件在下(A-Z), 各目录内同规则

### 验证

- 2 新契约测试 (渲染无重复/目录上文件下A-Z) · 全量回归 0 新增失败

## [v1.1.74] — 2026-08-24

**Board 文档配置页修复: 保存可用 + 刷新/重置按钮（Founder: 保存没反应）**。

### Fixed

- **保存 JS 修复**: f-string 里 dirs.join('\n') 被渲染成真换行 → JS 语法错误,
  保存按钮点击无响应; 改为字面转义 (\n), 保存正常
- **保存后反馈**: 成功 → "✅ 已保存 (N 目录, N 扩展名)" + 1.2s 自动跳转文档页;
  失败/网络错误 → 明确提示
- **新增按钮**: 🔄 刷新文档 (跳转文档页) + ↻ 重置表单 (重载配置页)

### 验证

- 2 新契约测试 (JS 转义/刷新按钮) · 全量回归 0 新增失败

## [v1.1.73] — 2026-08-24

**Board 文档管理可配置: 多目录 + 可配扩展名 + 设置页（Founder 重新设计）**。

### Added

- **文档配置** (docs_config.json): dirs (多个文档目录) + exts (支持扩展名,
  默认 md/json/doc/docx; PPT/Excel 等需额外配置)
- **多目录展示**: 每个配置目录一棵树 (📂 目录名 + 树)
- **设置功能**: Web 配置页 (/api/board/docs/config, 表单保存) + CLI
  (/board docs list|add-dir|add-ext|rm-dir); 文档页 ⚙ 配置入口
- 系统目录模式含固定核心资产 (中文标签), 扫描文件 extra 标记修复

### 验证

- 5 新契约测试 (默认配置/写配置/多目录+扩展名过滤/配置页/配置链接) · 全量回归 0 新增失败

## [v1.1.72] — 2026-08-24

**Board 文档管理重新设计: 默认折叠 + 紧凑行 + 类型筛选（Founder: 平铺难受, 需设计）**。

### Changed

- **目录默认折叠** (▸): docs(489) 等大目录不再刷屏, 点击展开
- **紧凑文件行**: 图标+文件名 (路径 hover), 大小右置, 小查看按钮;
  去掉冗余路径文字
- **类型筛选**: 全部/📄文档(md)/📦数据(json)/⚙配置(yaml)/📝文本(txt) 按钮
- 搜索与筛选联动 (data-name/data-kind)
- 目录行 hover 反馈, 子目录缩进虚线

### 验证

- 测试同步 (默认折叠断言) · 全量回归 0 新增失败

## [v1.1.71] — 2026-08-24

**Board 文档管理: 文件树 + 搜索 + 隐藏过滤（Founder）**。

### Changed

- **隐藏文件/目录过滤**: . 开头 ( .github/.git/.secret 等) 一律不展示
- **文件树形式**: 目录树可展开/折叠 (📁 目录 ▾/▸ + 文件行), 取代平铺
- **搜索功能**: 顶部搜索框, 输入即时过滤 (按文件名/路径/中文标签)
- 树文件行显示中文标签 (核心资产如"需求文档") + 路径
- 为项目级 RAG 预留 (隐藏过滤 + 树 + 搜索, 后续 RAG 复用)

### 验证

- 3 新契约测试 (隐藏过滤/树结构/HTML 树+搜索) · 全量回归 0 新增失败

## [v1.1.70] — 2026-08-24

**Board 文档管理指向项目实际目录/git 仓库（Founder: 应是实际目录或 git 地址）**。

### Changed

- 项目 product.json 支持 workspace_dir (实际目录) + repo_url (git 地址)
- 文档管理优先扫描 workspace_dir (真实仓库 README/docs/方案书等),
  无则系统存储目录; 顶部显示 📂 目录 + 🌐 git
- workspace_dir 扫描只显示文档类 (.md/.json/.txt/.yaml 等), 排除源码/垃圾
  (.git/$SMOKE_ROOT/__pycache__/node_modules/.venv/build/dist 等)
- AI Factory 自身项目配置 workspace_dir=/Users/Shared/work/ai-software-factory
  + repo_url=github.com/shenlongze/ai-software-factory
- doc_view 路径安全基于实际根目录

### 验证

- 4 新契约测试 (workspace_dir 优先/repo_url/工作目录仅文档/HTML 显示目录git) · 全量回归 0 新增失败

## [v1.1.69] — 2026-08-24

**Board 文档管理显示全部文件类型（Founder: docs 下其他文件也要显示, 暂不过滤）**。

### Changed

- 扫描去掉扩展名过滤: 项目目录全部文件 (.md/.json/.txt/.png/.yaml/.py 等) 都列出
- 非文本类型 (.png 等) 显示"—" (无查看链接); 点击查看 → "该类型暂不支持在线预览"
- 文本类型 (.md/.json/.txt) 正常查看

### 验证

- 3 新契约测试 (全类型扫描/HTML 查看标记/非文本提示) · 全量回归 0 新增失败

## [v1.1.68] — 2026-08-24

**Board 文档管理完整目录树（Founder: 根目录不只 README, docs 下还有其他文件）**。

### Changed

- 文档管理改为**完整目录树**: 全部文件 (核心资产 + 扫描文档) 按文件夹分组,
  根目录显示所有根文件 (product.json/PRD.md/plan.json/README.md 等, 不再分栏)
- 每文件夹显示文件数 (📁 根目录 (6)), docs/specs 等子目录各自区块
- 文档总数提示

### 验证

- 测试同步 (文件夹分组断言) · 全量回归 0 新增失败

## [v1.1.67] — 2026-08-24

**Board 文档管理按文件夹展示（Founder: 要文件夹显示, 项目下全部文档）**。

### Changed

- list_project_docs 扫描文档带 folder 字段 (父目录, 根目录="")
- 渲染按文件夹分组: 📁 根目录 / 📁 docs/ / 📁 specs/ 各区块, 项目下全部文档
  按目录结构展示 (非平铺)

### 验证

- 2 新契约测试 (folder 字段/HTML 文件夹分组) · 全量回归 0 新增失败

## [v1.1.66] — 2026-08-24

**Board 文档管理扫描真实文件: README/docs 展示（Founder: 项目 readme/docs 没展示）**。

### Added

- **文档扫描**: list_project_docs 扫描项目目录全部真实文档 (README.md / docs/ 子目录 /
  其他 .md/.json/.txt, 排除 .git 与固定资产), 分组展示"核心资产 + 其他文档"
- **查看任意项目内文档**: doc 端点支持 README/docs 等, 路径组件级安全校验
  (is_relative_to 修复 startswith 误匹配: projects/a 曾误匹配 audit_events)
- AI Factory 自身项目补 README.md + docs/开发文档.md (真实内容来自仓库)

### 验证

- 3 新契约测试 (扫描 README/docs 排除 .git / 分组 / 任意文档查看+穿越防护) · 全量回归 0 新增失败

## [v1.1.65] — 2026-08-24

**Board 数据实事求是: 数据来源标注 + 剔除臆造数据（Founder 核心要求）**。

### Changed

- **数据来源标注** (_data_source_html): 任务树/依赖图/任务链/文档 各视图顶部
  显示数据来源 (tasks.json/plan.json 的 meta: source/generated_by/note),
  明确区分"执行系统记录" vs "待办清单解析/手动登记"
- **剔除臆造数据**: AI Factory 自身 plan.json 重生成 —
  去掉全部 est_minutes=30 (无依据估时) + 去掉组内臆造依赖边,
  只保留有依据的组间里程碑顺序 (M2→M3→M4→M5→M6→M7→P0, 6 条边)
- plan.json/tasks.json 加 meta 来源字段 (source/generated_by/note)

### 验证

- 3 新契约测试 (meta 读取/来源 HTML/各视图含来源) · 全量回归 0 新增失败

## [v1.1.64] — 2026-08-24

**Board 任务树: 模块卡片分隔 + L1 组标题（Founder: 模块太密, 标题看不懂）**。

### Changed

- **模块卡片分隔**: 每个 L1 模块 (M2/M3/M4/M5/M6/M7/P0) 独立卡片 (标题栏 + 内容,
  深色背景 + 边框 + 间距), 模块间不再挤在一起
- **L1 组标题**: 从待办清单解析 '## M2 员工内核' → 显示 "M2 员工内核",
  不再显示无意义的 "M2 M2待办"
- L 徽章样式 (小标签)

### 验证

- 3 新契约测试 (组标题解析/模块卡片/子任务不重复平铺) · 全量回归 0 新增失败

## [v1.1.63] — 2026-08-24

**Board 任务树递归化 + 任务细化（Founder: 层级不够要 L1-L4, 重点是细化任务）**。

### Added

- **递归任务树 (L1-L4+)**: epic(L1) → feature(L2) → task(L3) → 子任务(L4+),
  L 徽章 + 缩进 + 展开/折叠 (▾/▸)
- **任务细化**: `/board task split <slug> <任务ID> <子任务1,子任务2>` (CLI) +
  POST `/api/board/split?project=&task=&names=` (Web 任务行"细化"按钮) —
  递归拆子任务 (parent 引用, 写回 tasks.json/execution_state)
- **数据**: task.parent 引用 + depth 递归 (L 层+1); 读回退 tasks.json/execution_state

### 验证

- 4 新契约测试 (拆分创建子任务/未知任务/递归树 L4/HTML L 标签+细化按钮) · 全量回归 0 新增失败

## [v1.1.62] — 2026-08-24

**Board 任务链格式优化（Founder: 看着乱, 需要格式）**。

### Changed

- **名称清洗**: 去掉 ** 加粗 markdown 标记 (_clean_md_name)
- **名称完整显示**: 不再截断 14 字符, 卡片内换行 (word-break), hover 完整 title
- **状态色**: 节点按任务状态着色 (done 绿 / failed 红 / running 蓝)
- **P0 自然序**: plan.json 生成用自然序 (P0-1→P0-2→...→P0-11, 修复字典序 P0-10 在前)
- 卡片布局优化: min-width 150px / max-width 220px / 箭头不挤压

### 验证

- 3 新契约测试 (清洗/无 markdown 标记/状态色) · 全量回归 0 新增失败

## [v1.1.61] — 2026-08-24

**Board 默认项目（Founder: 可选择默认项目）**。

### Added

- **默认项目设置**: `/board default <slug>` (CLI) + POST `/api/board/default?project=` (Web)
  + 项目列表/单项目页 "⭐ 设为默认" 链接; 存储 <workspace>/board_default_project
- **首页优先**: render_project_home 默认项目 > 会话当前项目 > 项目列表
- **默认标记**: 项目列表卡片 ⭐默认 (金色高亮) + 单项目页 ⭐ 设为默认项目 链接

### 验证

- 4 新契约测试 (读写/首页优先/列表标记/单项目链接) · 全量回归 0 新增失败

## [v1.1.60] — 2026-08-24

**Board 项目文档管理 + 任务逻辑增强（Founder: 需要文档管理; 任务不能堆）**。

### Added

- **项目文档管理**（📚 文档 tab, `/api/board/docs?project=`）: 9 类文档资产清单
  (产品定义/需求/工程/任务/执行/验证/修复/依赖/项目) + 状态/大小/更新时间
- **文档查看**（`/api/board/doc?project=&doc=`）: markdown 渲染 / JSON 格式化,
  文件名白名单防目录穿越
- **任务逻辑增强（不堆任务）**: 任务树任务行加
  ① 依赖标记 (`依赖: db→api`) ② 关键路径 ★ ③ 项目任务时间线 (audit 事件
  TASK_*/TEST_* 按时间排列)
- plan.json fallback: demo 等仅依赖计划的示例项目也能显示任务树依赖/关键

### 验证

- 7 新契约测试 (文档清单/HTML/查看 md/查看 json+穿越防护/依赖映射/树+关键/时间线) · 全量回归 0 新增失败

## [v1.1.59] — 2026-08-24

**Board 汇报/AI 主线面板也支持项目选择（Founder: 都需要）**。

### Fixed

- **汇报页导航跟随项目**: render_report_html nav 用 project_id, 选择器选中当前项目,
  report tab 带 ?project=
- **AI 主线面板带项目选择器**: render_board_html 加 project 参数, 缺省读会话当前
  项目 (session_state), 选择器正确选中; 可随时切到项目视图
- 修正 render_board_html 导航 active 键 (main → mainline) 与项目列表/单项目
  active 键 (projects → project), 统一 _board_nav 键体系

### 验证

- 2 新契约测试 (AI主线选择器选中当前/汇报导航跟随) · 全量回归 0 新增失败

## [v1.1.58] — 2026-08-24

**Board 生命线/汇报项目化（Founder 选方案 A: 凡有 project_id 维度即跟随项目选择）**。

### Added

- **生命线项目过滤**: `/api/board/timeline?project=<slug>` + CLI `/board timeline <slug>`
  只显示该项目审计事件 (按 project_id); 无项目时全局
- **项目汇报**: `/api/board?view=report&project=<slug>` + CLI `/board report <slug>`
  markdown 项目汇报 (生命周期/任务状态/文档产物/最近事件); 无项目时仍为 AI 主线汇报
- **导航跟随**: 生命线/汇报 tab 有项目时带 ?project=, 选项目后全面板切换上下文

### 验证

- 5 新契约测试 (timeline 过滤/HTML 过滤/项目汇报内容/report 项目化/导航跟随) · 全量回归 0 新增失败

## [v1.1.57] — 2026-08-24

**Board 修复: 项目选择器与 URL 一致 — 不再"选墨笺/URL 是 demo"**。

### Fixed

- 选择器选中态: URL 项目不在注册列表 (demo 等示例/未注册) → 显式加入
  "slug (示例/未注册)" 选项并选中; 不再因无匹配项默认选第一个项目
  (浏览器行为), 消除界面与 URL 不一致的误导
- 选择器切换: 按当前视图 route 跳转 (tasks?project=/view=project&project=),
  选项目后 URL 即变为所选项目

### 验证

- 3 新契约测试 (未注册项目选中/已注册选中/route 按视图) · 全量回归 0 新增失败

## [v1.1.56] — 2026-08-24

**Board 修复: 示例项目 demo 误报"项目不存在" + 导航无项目不再 fallback demo**。

### Fixed

- 任务树项目存在性: 有 product.json 或任务资产 (tasks/execution_state/plan) 均视为
  存在 — demo 等仅有 plan.json 的示例项目显示"暂无任务"（诚实）, 不再误报"项目不存在"
- 导航无项目时: 任务树/依赖图/任务链 tab 指向项目列表引导（选择是第一步）,
  不再 fallback 到 demo 示例

### 验证

- 4 新契约测试 (plan-only 项目/完全不存在/无项目导航/有项目导航) · 全量回归 0 新增失败

## [v1.1.55] — 2026-08-24

**Board 生命线可读化（Founder: 看不懂, 英文粘连+重复刷屏）**。

### Changed

- **事件类型中文标签**（EVENT_LABELS 20+ 映射）: DISCOVERY_CONFIRMED→需求确认,
  PRODUCT_CREATED→产品创建, TASK_STARTED→任务开始 等; 未知类型保留原名
- **对象名解析**: project_id→项目名 (读 product.json), task/agent 同; 不再裸 ID
- **高频降噪**: DISCOVERY_CONFIRMED (产品发现确认, 占 94%) 折叠为一行
  "需求确认 ×N (已折叠)"; 核心事件 (任务/产物/计划/测试/审批/失败) 单独显示
- **同秒聚合**: 同秒同类型同对象事件合并显示 ×N
- CLI 文本版 (render_timeline) 同步优化

### 验证

- 4 新契约测试 (中文映射/对象名/折叠+中文/HTML 可读) · 全量回归 0 新增失败

## [v1.1.54] — 2026-08-24

**Board 信息架构调整: 项目选择第一步, 面板第二步（Founder 核心反馈）**。

### Changed

- **默认首页改为项目视图**: /api/board 有当前项目 → 该项目全生命周期视图;
  无 → 项目列表引导。AI Factory 主线面板 (AI 自身开发进度) 降级为显式
  `?view=mainline`, 不再是默认首页
- **项目选择器置顶放大**（第一步）: 导航第一行大 select "📁 选择项目:",
  第二行才是面板 tab (项目/任务树/依赖图/任务链/生命线/汇报)
- **面板 tab 跟随项目**: 选项目后 tab 全部切换上下文 (不再默认 demo)

### 验证

- 4 新契约测试 (首页=当前项目 / 首页回退列表 / 大选择器置顶 / 主线显式) · 全量回归 0 新增失败

## [v1.1.53] — 2026-08-24

**Board 刷新间隔可选: 5s/15s/30s/60s/关闭（Founder）**。

### Added

- **刷新间隔选择器**（导航 select）: 所有视图页可选 5s/15s/30s/60s/关闭,
  切换后 URL 带 ?refresh=N (0=关闭)
- **自动刷新 JS 化**（`_auto_refresh_script`）: 替换固定 meta refresh —
  主线默认 30s, 单项目/任务树默认 15s, 其余默认关闭; 用户可覆盖
- 默认值: 主线 30 / 单项目 15 / 任务树 15 / graph/chain/timeline/report/列表 0

### 验证

- 5 新契约测试 (选项齐全/select 渲染/script 默认值/8 页全覆盖/默认刷新) · 全量回归 0 新增失败

## [v1.1.52] — 2026-08-24

**Board 项目选择完成: 全局项目选择器 + 数据准确/实时/同步（Founder）**。

### Added

- **全局项目选择器**（`_board_nav` + `_project_select_html`）: 所有视图页导航含
  select dropdown, 切换项目后跳转当前视图的对应项目 (graph/chain/tasks) 或
  单项目视图; 当前项目选中态
- **数据实时**: 单项目视图 + 任务树 15s 自动刷新 (主线 30s + summary 5s 已有)
- **数据同步**: 项目列表/选择器标记会话当前项目 (读 session_state.json);
  导航链接项目上下文传递 (不再默认 demo)
- **数据准确**: 全部实时读盘 (product.json/execution_state/session_state), 无缓存

### 验证

- 5 新契约测试 (选择器含当前/路由按视图/当前标记/自动刷新) · 全量回归 0 新增失败

## [v1.1.51] — 2026-08-24

**Board: 导航返回修复 + 任务树视图 + 任务状态汇总（完善任务）**。

### Added

- **共享导航统一**（`_board_nav`）: 所有视图页含返回主线面板 + 任务树 tab; 修复
  切换菜单后无法返回 (graph/chain/timeline/report 及空态分支此前无导航)
- **项目任务树**（`/api/board/tasks?project=`）: epic → feature → task 层级可视化,
  状态色点 (✅🔵❌⬜) + 状态汇总
- **任务状态汇总**: 项目视图显示 ✅完成/🔵进行中/❌失败/⬜待办 计数

### 验证

- 6 新契约测试 (导航含返回/全部页面含 nav 含空态/状态计数/任务树分组/生命周期页汇总) · 全量回归 0 新增失败

## [v1.1.50] — 2026-08-24

**Board 完善: 监控聚合 + 实时刷新 + SDK 第四数据源 + Sprint 判定放宽 + 项目任务清单**。

### Added

- **项目监控聚合**（`/api/board/summary` + 主线面板总览）: 项目数/状态分布/生命周期均值/
  进行中任务/失败任务; Web 每 5s 增量刷新（不整页刷新, 轻量 JSON）
- **§22 SDK 任务第四数据源**（`_parse_sdk_tasks`）: 方案书 §22.3 4 阶段路线
  （SDK-1 内核收尾 → SDK-4 商业化）进 board 文本+HTML
- **Sprint 完成判定放宽**: acceptance/completion/final 任一证据即完成
  （16/96 → 53/99, 早期 Sprint 不再虚低）
- **项目内任务清单视图**: 生命周期页显示任务列表（状态标记 ✅/🔵/❌/⬜ + agent）,
  文本+HTML; 上限 20 防刷屏

### 验证

- 7 新契约测试 (dashboard 聚合 / SDK 解析 / Sprint 判定 / 任务清单 / HTML 含监控) · 全量回归 0 新增失败

## [v1.1.49] — 2026-08-24

**Board 单项目管理视图（全生命周期, S10-110）: /board project 只读查看单项目进度**。

### Added

- **单项目管理视图**（`/board project <slug>` + Web `/api/board?view=project&project=`）:
  全生命周期 11 段进度条（发现→确认→PRD→工程→开发→测试→验收→交付→部署→运维→更新）
  + 文档产物 + 任务进度 + 更新时间; 当前卡点标注
- **项目列表 select**（`/board project` 无参 + Web `?view=projects`）: slug/名/状态/时间,
  点击卡片进入单项目视图
- **生命周期阶段映射**（确定性）: 1-7 段由现有资产判定 (product.json/PRD.md/
  engineering.json/tasks.json/validation/status); 8-11 段（交付/部署/运维/更新）
  占位"未开始"（待部署运维功能落地填充）
- **项目隔离铁律**: 只读 projects/<slug>/ 该项目文件; 无显式项目 → 空态提示,
  绝不猜项目/扫描兜底; 空壳目录 (无 product.json) 从列表排除

### 验证

- 12 契约测试 (阶段映射手算 / 列表隔离 / 空态 / 只读 mtime / 会话集成) · 全量回归 0 新增失败

## [v1.1.48] — 2026-08-24

**需求分析字段错位修复 (T9, Founder 实测复现)**: 问痛点答"给大学生用"被强填 problem /
"支持扫码记账和月度报表"被强填 user / "可以"被强填 core_features。

### Fixed

- **需求分析字段错位 (确定性内容归类, 不依赖 LLM)**: 发现阶段回答先经
  `_resolve_answer_field` 语义判定 — 命中 user/core_features/problem 模式且该字段
  未填 → 填匹配字段 (多命中优先级 user > core_features > problem); 未命中 → 填当前
  字段 (正常回答零变化, 逐字节不变); LLM field_answer 路径与机械单字段路径共用
- **确认词不当字段值**: 整句为确认词 (APPROVE_WORDS + y/yes) 且当前字段未填 → 不填,
  提示 "产品定义还不完整, 还缺 {字段}, 请先补充" (state 保持发现, 不推进)
- 批量模式不受影响 (分号多字段按顺序填)

### 验证

- 契约测试 test_s10_109_field_routing (≥8 用例) 全绿 · env -u 无 LLM 路径同生效 ·
  全量 console 回归 0 新增失败

## [v1.1.47] — 2026-08-24

**CLI 交互修复 + 方向键历史 (Founder 实测: 方向键变乱码 /exitt)**。

### Added

- **方向键历史/行编辑** (readline 标准库, 零依赖): ↑↓ 调历史 / ←→ 行内编辑;
  历史持久化到 <workspace>/history; 无 readline (Windows) 时 ANSI 转义清理兜底
  (方向键不再产生 ^[[A 乱码、不再拼出 /exitt 误命令)

### Fixed

- **发现阶段"确认+动作"短语** ("可以，先出prd文档"/"先出PRD"): 产品定义不完整时
  确定性提示缺失字段 (不再被 LLM 当字段回答 / 盲目触发创建)
- **generate_prd 扫描兜底写错项目** (数据安全): 无显式项目 (current_project/
  product_intent) 时安全报错, 不把 PRD 写进"最新项目" (实测复现写入旧项目)
- **/project 读错路径**: 自定义 workspace 会话项目清单跟随工作区 (不再硬编码 ~/.factory)

### 验证

- 全量 12349+ passed / 0 failed · PTY 实测方向键历史调出 /help · /exitt 不再出现

## [v1.1.46] — 2026-08-24

**factory --version 更新提示**: 检查是否存在可更新版本（Founder）。

### Added

- `factory --version` 显示版本后检查更新:
  - 📦 落后远程 N 提交 → 提示 factory update
  - 🚀 本地领先远程 N 提交 → 诚实显示"无远程更新"
  - ✅ 已是最新
  - 未 fetch 过 → 引导 factory update --check
- ahead/behind 区分（不误报"可更新"当本地领先）· 快速检查不主动网络（用本地引用）

### 验证

- --version: "🚀 本地领先远程 81 提交（无远程更新, 已是最新）"


**update HTTP API**: /api/system/status + /api/system/update（Founder: 要补 update 的 HTTP API）。

### Added

- **GET /api/system/status** — 系统状态（版本 + 服务清单 + git head/脏标记）
- **POST /api/system/update[?module=core|console|exec|org]** — 触发更新（git pull + pip install -e .）
  - 返回步骤结果（每步 ok/detail）· 失败安全（单步失败不崩）
  - 审计（GOVERNANCE_CHECK 事件记录触发）
- 仓库根定位（git/pip 在代码仓库运行, 非数据目录）

### 验证

- status: version 1.1.44 + git head ✅
- update: git pull ✅ + pip install ✅（ok: true）


**factory update 增强**: 进度条 + 变更 list（Founder: 增加进度条, 完成后给变更list）。

### Added

- **步骤进度条** — update 显示 [1/2] git pull → [2/2] pip install（✅/⚠️）
- **变更 list** — update 完成后从 CHANGELOG 读当前版本条目（本次变更清单）
- 结果摘要: 代码/依赖状态 + 错误提示（失败安全）

### 验证

- update --check 正常 · 步骤进度/变更 list 逻辑就绪（SyntaxWarning 修复）


**factory update 命令**: 整体/模块更新（Founder: 增加整体更新命令, 模块可单独更新）。

### Added

- **factory update --check** — 只读检查（当前版本 + git 状态）
- **factory update** — 整体更新（git pull + pip install -e .）
- **factory update <模块>** — 指定模块更新（core/console/exec/org; 单体仓库随整体更新,
  模块独立版本见 §2.4 设计预留）
- 命令体系: 系统域（§11.6）· 失败安全（git/pip 失败提示不崩）

### 验证

- --check 显示版本+git状态 · 未知模块 rc2 明确错误


**board 无数据引导 + demo 示例**: 依赖图/任务链未生成时显示引导, 导航带示例（Founder: 都没有数据）。

### Fixed

- 主面板导航带 demo 示例（依赖图(示例)/任务链(示例), ?project=demo）
- graph/chain 无 plan.json 时引导: 未生成计划 + 真实数据来源（执行 M3b）+ demo 链接
- 真相: 真实项目需执行 M3b（拆解→关键路径）才生成 plan.json

### 验证

- 导航含 graph?project=demo · graph 无项目显示引导（未生成计划/demo 示例图）


**board 各种图集成**: 主面板导航 tabs（主线/依赖图/任务链/生命线/汇报 一个入口）。

### Added

- **主面板导航条**（`board.py` render_board_html）— 5 tabs: 主线/依赖图/任务链/生命线/汇报
- **/api/board/timeline**（`fastapi_adapter.py`）— 生命线 HTML（时间轴, 事件类型配色: 完成绿/运行橙/失败红）
- **/api/board?view=report** — 汇报 HTML 视图（markdown → 可读页面）
- render_timeline_html / render_report_html

### 验证

- 主面板导航含 graph/chain/timeline/report ✅ · 汇报视图 ✅ · 生命线 ✅


**board 多源加载（设计文档全部任务）**: Sprint + 章节 + 待办清单（Founder: 现在不全）。

### Added

- **Sprint 任务加载**（`board.py`）— 扫描 docs/sprint10/ 96 个 S10 Sprint
  （完成=有 acceptance 验收报告证据）
- **章节任务加载**（§1.4 状态表）— 22 章 + 附录, 各带 ✅/🚧 状态 + 待补
- render_board 合并: 待办清单(M/P0) + Sprint(S10) + 章节(§1.4)
- 修复 §1.4 解析（过滤 §1.4.5 层级表格行）

### 说明（诚实）

- Sprint 完成判断=acceptance 文件存在（低估: 很多验收在 Hermes 消息未落盘）
- §22.6 SDK 任务待加（后续）


**自动钩子: 主线状态自动同步**（Founder: 需要 — 数据准确实时, 不靠手动记）。

### Added

- **/board sync**（`board.py`）— 从代码证据自动推断主线完成并标记
  （代码存在: decomposer→M3-1, critical_path→M3-2, scheduler→M3-3/4）
  幂等（已标跳过）· 只标证据强项（诚实不误标 M3-5/6/7）
- **会话启动自动 sync**（`session.py`）— 进会话主线状态即真实
  （代码证据确认完成 → 自动标记 + 提示; 不依赖手动 /board done 记忆）

### 验证

- 会话启动自动同步（M3 4/7 真实）· /board sync 幂等


**偏离提醒**: 会话启动提示主线未完成（Founder 核心痛点: 脱离主线, 做多周边, 线没走完）。

### Added

- **会话启动主线检查**（`session.py`）— banner 后提示未完成主线
  ```
  ⚠️ 主线未完成: M3(4/7) M4(0/6) M5(0/8) M6(0/1) M7(0/2) P0(0/11)
     建议: 优先推进主线 · /board 看全景 · /board report --save 汇报 Hermes
  ```
- 主线全完成不提示（不啰嗦）· 提醒失败不阻断会话

### 验证

- 会话启动即显示主线未完成提醒（M3 4/7 等真实状态）


**主线控制机制（从仪表盘到控制系统）**: /board done/unmark + 汇报落盘 + 主线状态真实化。

### Added

- **/board done <id> / unmark <id>**（`board.py`）— 标记主线任务完成/取消
  （更新待办清单行内 ✅, board 进度实时准确）
- **/board report --save** — 汇报落盘到 docs/sprint10/progress-report-*.md
  （同步 Hermes 的素材, 无需手动复制）
- **主线状态真实化**: 待办清单按真实交付标记（M3-1/2/3/4 ✅ —
  M3a 拆解/M3b 关键路径/M3c 调度/M3e 动态分配）

### 验证

- done/unmark 更新待办清单 ✅ · report --save 生成 docs/sprint10/progress-report ✅
- M3 主线 4/7（真实状态）


**board 状态分布图 + 交互（hover/筛选）**: 分布条 + 筛选按钮 + hover 高亮（Founder）。

### Added

- **状态分布条**（`board.py`）— 完成绿/未完成灰/周边 三色分布 + 图例
- **筛选按钮**（内联 JS, 无外部依赖）— 全部/主线/周边/已完成/未完成/进行中
- **hover 交互** — 卡片上浮 + 阴影, 任务行 hover 高亮
- 卡片 data-kind/data-status 属性（筛选用）

### 验证

- dist-bar/f-btn/data-kind/li:hover/script 全部渲染
- 纯 CSS/JS（离线可用, 不引外部 CDN）


**board 视觉增强**: graph/chain HTML 可视化 + 自动刷新（Founder: 来, 开始）。

### Added

- **/api/board/graph?project=X** — 任务依赖图 HTML（节点卡片 + CRITICAL★ 红色高亮 + 依赖边）
- **/api/board/chain?project=X** — 任务链 HTML（关键路径 ★关键节点 ▲汇聚点 + 总工期, 手机自适应竖排）
- **/api/board 自动刷新**（30s meta refresh, 实时监控）
- build_app 加 factory_root（graph/chain 读项目 plan.json 的数据根）

### 验证

- graph: db★/api★/fe★/test★ 红色节点 + extra 普通 + 依赖边
- chain: ★db→★api→★fe→★▲test + 总工期 12min


**/api/board HTML 可视化面板**: 进度条/标签/分组卡片, 浏览器自适应（Founder: 升级为 HTML 可视化）。

### Added

- **render_board_html**（`board.py`）— HTML 面板（纯标准库生成, 无模板依赖）
  - 进度条（bar 百分比）· 标签色块（P0红/P1橙/主线蓝/周边灰）· 分组卡片
  - 响应式（grid auto-fill, 桌面/手机/Pad 自适应）
- **api_board 返回 HTMLResponse**（`fastapi_adapter.py`）— /api/board 浏览器直接看面板
- 底部显示版本 + 会话 /board 更多视图提示

### 验证

- /api/board 返回完整 HTML（进度条 6/41 + 分组卡片 + 标签）


**backend 启动修复（2 个 bug）**: /api/board 可访问。

### Fixed

- **fastapi_adapter __version__ 导入** — `from ... import __version__` 相对导入解析到
  仓库根 factory_console 别名包（无 __version__）→ ImportError 导致 backend 启动失败
  → 改为直接读 pyproject.toml（独立于包, 不依赖相对导入）
- **api_board 模块导入** — `from ..session.board` 相对导入层级错（解析成 web.session）
  → 改用 _console_import("session.board")（源码/部署态双兼容）

### 验证

- backend 启动成功（8011 LISTEN, health OK）
- /api/board 返回完整面板（主线 6/41 + M2✅ + M3-M7/P0/长期）


**board 增强**: 任务链(关键路径) + 关键节点 + --report 汇报导出（Founder: 需要, 还有任务链/无序图/关键节点）。

### Added

- **/board chain [项目]**（`board.py`）— 任务链（关键路径 critical_path, ★关键节点 ▲汇聚点 + 总工期）
- **/board report** — 给 Hermes 的 markdown 汇报（主线完成/进行中/未开始 + 周边 + 建议下一步）
- /board 说明更新（chain/report 子命令）

### 验证

- 任务链: db★→api★→fe★→test★▲（关键 4 节点 + 汇聚 1 + 工期 12min）
- report: markdown 汇报（M2 ✅ 主线完成）


**factory help 命令总览**: 按域分类列出全部命令（§11.6 落地, Founder: 命令在哪查看）。

### Added

- **factory help**（`cli_factory.py`）— 按 6 类域分组列出命令（非字母序）
  - 系统/资源/数据/执行/组织/展示 + 其他（动态从 parser 读, 新增自动出现）
  - 会话命令提示 + 自然语言提示 + 单命令 --help 指引
- 查看命令的 4 个入口:
  factory help（按域）· factory --help（字母序）· /help（会话）· factory <命令> --help


**命令体系总纲（§11.6）+ llm/todo 命令落地**: 域×动词 统一结构, 命令再多不混乱。

### Added

- **§11.6 命令体系总纲**（方案书）— `factory <域> <动词>` 统一结构
  - 5 域: 系统/资源/数据/执行/展示 · 标准动词集(list/show/create/start/stop...)
  - factory help 总览 · 新增=新域+标准动词 · LLM 意图映射(用户不记命令)
- **factory llm list** — LLM 清单（provider/models, 资源域）
- **factory todo list** — 主线任务清单（待办清单, 数据域, 复用 board 渲染）
- 多端访问衔接: factory start 统一启动 + 打印地址

### 测试

- help 显示 llm/todo · llm 未配置明确提示 · todo 渲染主线面板


**service list 显示访问地址**: board 懒加载服务的 url + 访问提示（Founder: "都不知道在哪"）。

### Fixed

- **BoardService.status 加 url**（`cli_services.py`）— `http://127.0.0.1:<backend_port>/api/board`
- **note 访问指引**: 会话 /board · Web /api/board（需 backend 运行）
- `factory service list` 现在显示:
  ```
  board  running  (http://127.0.0.1:8011/api/board)
  ```


**会话 Markdown 渲染 + /preview + 多行输入**（S10-105）:
PRD/文档输出经 rich.Markdown 渲染 (标题/列表/表格/代码块可读, 不再看源码);
`/preview PRD.md` 渲染显示文件; 行尾 `\` 续行拼接多行输入 (prompt_toolkit
缺失 → input() 降级, 诚实)。启发式保守 — 非 markdown 纯文本零变化。
注: /preview 命令注册随 S10-106 提交先行落盘, 本版本补齐渲染层/会话接线/测试/docs。

### Added

- **会话 Markdown 渲染**（`session/renderer.py`）— `looks_like_markdown(text)`
  强信号保守判断 (含 ``` 围栏 / 任一行 ^#{1,6} 标题 / 任一行含 | 表格; 列表标记
  不算 — 发现/进度消息保持纯文本) + `render_message(text)` (rich 可 import 且
  是 markdown → `Console().print(Markdown(text))`; 否则 print 原样 — 诚实降级,
  rich 非终端自动去 ANSI)
- **/preview 命令**（`session/commands.py` PreviewCommand, 随 v1.1.27 落盘）:
  `/preview PRD.md` → 路径解析 (绝对直接用; 相对 → cwd → workspace → 项目目录
  → data_dir 兜底) → 读取 → render_message; 无参/文件不存在/读失败 → 友好错误
  rc 2 (不崩)
- **多行输入**（`session/session.py`）— `_read_input_line(prompt)`: 行尾 `\`
  → 续行 (提示 `… `) 直到无 `\`, 拼接 `\n`; run() 的 input 改用它; 拼接结果
  作为一条输入进既有 _dispatch (多行需求天然支持 \n)
- 测试: `tests/console/test_s10_105_markdown_preview.py` (契约 1-7)

### Changed

- `session.py` 用户面消息 print 点接入 render_message: chat 回答 (L281/L321)、
  action 结果 renderer 输出 (L345)、产品流消息 (L270/L288); 错误/退出/分隔线
  等不接 (保持原样)

### Fixed

- 提交树 v1.1.27 中 commands.py 已 import render_message 但 renderer.py 未含
  该函数 → 本版本补齐 (修复 ImportError, 会话可正常启动)
- PRD/文档输出在会话中显示源码 (markdown 原文) → 现在 rich 渲染可读
- 粘贴长需求/多行文本无法输入 → 行尾 `\` 续行拼接 (prompt_toolkit 缺失
  降级 input(), 不伪造)

### Tests

- 新增 `tests/console/test_s10_105_markdown_preview.py`（契约 1-7 全绿）
- 版本断言 v1.1.27 → v1.1.28（`test_s10_074_deployment` / `test_s10_103_command_routing`
  / `test_s10_104_action_coverage` / `test_confirmation_intelligence` / `test_s10_105_markdown_preview`）;
  消息输出断言全部保持 `in` 包含 (markdown 渲染后非终端无 ANSI)
- `test_session_completion` 默认命令表断言更新: +/preview (S10-105) +/board (S10-106)

---
## [v1.1.28] — 2026-08-24

**服务生命周期管理（§2.13）+ board 服务落地**: 服务注册/发现/运行/执行/治理/监控 6 阶段规则 + board 懒加载服务。

### Added

- **§2.13 服务生命周期管理**（方案书）— 注册/发现/运行(已有) + 执行/治理/监控(设计)
  - 随启动组件装配: 注册+懒加载 ≠ 全部常驻; 失败隔离 + 热插拔
- **BoardService**（`cli_services.py`）— board 注册进 Services Registry
  - `factory service list` 可见 · status 懒加载 · 会话 /board + /api/board 端点
- 未来 dashboard/通知/日志 同机制注册（ServiceDef + register 一行）

### 测试

- 服务注册验证: list 含 board · status running(懒加载)


**任务监控面板 /board**: todolist + 进度条 + 标签 + 依赖图 + 生命线（Founder 需求）。

### Added

- **/board**（`session/board.py` + `commands.py`）— 主线 todolist + 进度条 + 标签
  - 主线(M2-M7/P0) vs 周边(长期) 分组 · 组级 ✅ 识别 · rich 渲染降级纯文本
- **/board graph [项目]** — 任务依赖图（plan.json tasks/edges/critical_path, CRITICAL=★）
- **/board timeline** — 生命线（audit_events 最近事件, 时间→事件→对象）
- 数据源: 待办清单（主线）+ DashboardCollector 数据层 + plan.json + audit_events

### 测试

- 相关回归 通过（会话/CLI 测试）· 面板失败安全（数据缺失/损坏容错）


**会话 Markdown 渲染 + /preview + 多行输入**（S10-105）:
PRD/文档输出经 rich.Markdown 渲染 (标题/列表/表格/代码块可读, 不再看源码);
`/preview PRD.md` 渲染显示文件; 行尾 `\` 续行拼接多行输入 (prompt_toolkit
缺失 → input() 降级, 诚实)。启发式保守 — 非 markdown 纯文本零变化。

### Added

- **会话 Markdown 渲染**（`session/renderer.py`）— `looks_like_markdown(text)`
  强信号保守判断 (含 ``` 围栏 / 任一行 ^#{1,6} 标题 / 任一行含 | 表格; 列表标记
  不算 — 发现/进度消息保持纯文本) + `render_message(text)` (rich 可 import 且
  是 markdown → `Console().print(Markdown(text))`; 否则 print 原样 — 诚实降级,
  rich 非终端自动去 ANSI)
- **/preview 命令**（`session/commands.py`）— `PreviewCommand`:
  `/preview PRD.md` → 路径解析 (绝对直接用; 相对 → cwd → workspace → 项目目录
  → data_dir 兜底) → 读取 → render_message; 无参/文件不存在/读失败 → 友好错误
  rc 2 (不崩); 注册进 build_default_registry
- **多行输入**（`session/session.py`）— `_read_input_line(prompt)`: 行尾 `\`
  → 续行 (提示 `… `) 直到无 `\`, 拼接 `\n`; run() 的 input 改用它; 拼接结果
  作为一条输入进既有 _dispatch (多行需求天然支持 \n)
- 测试: `tests/console/test_s10_105_markdown_preview.py` (契约 1-7)

### Changed

- `session.py` 用户面消息 print 点接入 render_message: chat 回答 (L281/L321)、
  action 结果 renderer 输出 (L345)、产品流消息 (L270/L288); 错误/退出/分隔线
  等不接 (保持原样)

### Fixed

- PRD/文档输出在会话中显示源码 (markdown 原文) → 现在 rich 渲染可读
- 粘贴长需求/多行文本无法输入 → 行尾 `\` 续行拼接 (prompt_toolkit 缺失
  降级 input(), 不伪造)

### Tests

- 新增 `tests/console/test_s10_105_markdown_preview.py`（契约 1-7 全绿）
- 版本断言 v1.1.25 → v1.1.26（`test_s10_074_deployment` / `test_s10_103_command_routing`
  / `test_s10_104_action_coverage` / `test_confirmation_intelligence`）; 消息输出断言
  全部保持 `in` 包含 (markdown 渲染后非终端无 ANSI)

---
## [v1.1.25] — 2026-08-24

**确认阶段 next_action 全覆盖 + 会话分割线 + 删除/清空字段指令**（S10-104）:
"产出份prd文档"/"生成PRD"/"出个html"/"出份功能清单" 不再被当改名 — 类型扩展
next_action {prd/feature_list/html/docs} (LLM 分类为主 + 规则补全变体, 无确认前缀
= 隐含确认+下一步); 每轮回复间加分割线 (REPL 层纯装饰); "把核心功能删掉"/"清空目标用户"
→ 字段清空 → 重新确认/追问 (绝不当改名)。

### Added

- **直接动作短语规则**（`session/discovery_guide.py`）— `DIRECT_ACTION_PATTERNS`
  (prd/feature_list/html/docs 正则) + `match_direct_action(norm)` (lower 后匹配,
  返回首个命中): "产出份prd文档"→prd / "生成PRD"→prd / "出个html"→html /
  "出份功能清单"→feature_list / "文档"→docs — 确定性, 无确认前缀也命中
- **LLM 补充分类**（`session/discovery_intelligence.py`）— `analyze_confirmation`
  prompt 更新: next_action 词汇 {prd/feature_list/html/docs} + 变体示例;
  approve_next 允许无确认前缀 (纯动作请求 = 隐含确认 + 下一步);
  `VALID_NEXT_ACTIONS` 扩展 (develop/create 保留 S10-102 兼容)
- **删除/清空指令**（`session/conversation.py`, 确定性）— `_parse_delete_command`
  (两序匹配, 复用 `_EDIT_FIELD_ALIASES`: (把|将)?别名+删除动词 /
  删除动词+别名) + `_apply_delete_command`: 字段有值 → 清空 (core_features → [];
  其余 → "") → 必填字段 → 迁移 DISCOVERY + pending=[field] + 追问; 可选/其它 →
  重进确认 (摘要更新); 字段收集期同步支持 (重问); 绝不当改名
- **会话分割线**（`session.py`）— `SEPARATOR = "─" * 46`, run() 每轮
  `_dispatch` 后打印 (退出/空输入不打印); 非交互 CLI 不受影响
- **宿主 next_action 信号**（`session.py`）— feature_list/html/docs →
  消息追加 `"[已记录] 将生成{label} — 产出引擎 backlog"` (不阻断创建, 产出引擎
  backlog); prd → generate_prd 既有
- 测试: `tests/console/test_s10_104_action_coverage.py` (契约 1-9)

### Fixed

- "产出份prd文档"/"生成PRD"/"出个html"/"出份功能清单" 被当改名 → 现在 approved +
  对应 next_action (名称不被覆盖)
- "把核心功能删掉"/"清空目标用户" 被当改名 → 现在字段清空 → 重新确认/追问
- 多轮回复间无视觉分隔 → 每轮回复后加分割线

### Changed

- `handle_product_confirm` 分流顺序: RENAME_RE → **DIRECT_ACTION** → 确认+下一步 →
  纯确认 → 澄清 → **删除指令** → 取消 → 委托 → LLM → 改名兜底 ("改名叫X" 最优先,
  不被动作规则抢)
- `ConversationResponse.next_action` 词汇扩展 {prd, feature_list, html, docs}
  (develop/create 保留兼容)

### Tests

- 新增 `tests/console/test_s10_104_action_coverage.py`（契约 1-9 全绿）
- 既有更新: `test_confirmation_intelligence.test_invalid_next_action_normalized`
  (html 现为合法 next_action, 改用非法值 pdf 断言归一) + 新增
  `test_new_next_actions_accepted` / `test_prompt_contains_new_next_action_variants`;
  版本断言 v1.1.24 → v1.1.25（`test_s10_074_deployment` / `test_confirmation_intelligence`
  / `test_s10_103_command_routing`）

---

## [v1.1.24] — 2026-08-24

**发现流程命令分流 + CLI 输入健壮性**（S10-103）: 发现/确认两路径中 "/status"/"/help"
不再被当字段、也不死胡同 — slash → passthrough 交回宿主命令注册表执行; "exit"/"quit"/
"再见"/"退出会话"/"拜拜"/"结束" → 优雅退出 (exit_requested → running=False);
"退出" 语义不变 (仍 = 取消发现, 向后兼容); CLI: project 无子命令提示补 status;
create project 无 --name → 明确错误 rc 2。

### Added

- **共享退出命令集**（`session/discovery_guide.py`）— `EXIT_COMMANDS` frozenset
  （exit/quit/退出/退出会话/再见/拜拜/结束）: 单一来源, `session.py` 改为从此导入
  （集合内容不变; conversation 不能 import session — 循环依赖）
- **conversation 命令分流**（`conversation.py`, 确定性不依赖 LLM）—
  `_command_escape(text)`: slash → `passthrough=True`（宿主重分发, 不再死胡同）;
  EXIT_COMMANDS → `exit_requested=True`; `ConversationResponse += exit_requested`;
  接入 `handle_product_answer` / `handle_product_confirm`（`_product_control` 之后、
  字段收集之前 — "退出" 仍由控制短语先处理 = 取消发现, 向后兼容）; `handle()` 顶部
  slash 分支改 passthrough + 产品流程前 EXIT 检查
- **宿主退出接线**（`session.py`）— `_dispatch` 产品流分支新增 `exit_requested` →
  `print("已退出会话 — 再见!")` + `self.running = False`（slash 经既有 passthrough
  重分发 → registry.execute）

### Fixed

- 发现/确认中 `/status` `/help` 被当字段或死胡同 → 现在正常执行命令
- 发现/确认中 `exit` `quit` 被当字段推进 → 现在优雅退出会话
- `factory project` 无子命令提示漏 `status` → 提示补全
  `(create / list / rename / status)`
- `factory create project` 不强制 `--name` → 现在缺失时明确错误 `rc 2`
  （错误: create project 需要 --name <项目名>）

### Changed

- `session.py` `EXIT_COMMANDS` 本地定义 → `from .discovery_guide import EXIT_COMMANDS`
  （集合内容不变, 既有退出行为零变化）
- `conversation.handle()` slash 分支: 死胡同消息 → `passthrough=True`（宿主重分发）

### Tests

- 新增 `tests/console/test_s10_103_command_routing.py`（契约 1-9 全绿）
- 既有更新: `test_session_conversation.test_handle_slash_keeps_state`（slash 断言改为
  passthrough, 注释原因）; 版本断言 v1.1.23 → v1.1.24
  （`test_s10_074_deployment` / `test_confirmation_intelligence`）

---

## [v1.1.23] — 2026-08-24

**确认阶段智能分流 + 求助词全覆盖**（S10-102）: "可以，先出prd文档"/"？" 不再被当产品名 —
确认/确认+下一步/改名/澄清/取消/委托 六类分流; "没 想法" 等口语变体不再填进字段; 宿主
PRD 接线。

### Added

- **确认分流确定性表**（`session/discovery_guide.py` 扩展）— 两路径/可测试唯一来源:
  - `normalize_help_text` 去全部空白（半角/全角空格/tab/换行 — "没 想法"→"没想法"）;
    `HELP_KEYWORDS` += 随便/你定/你看吧/你决定/听你的/你来定/都行/都可以/无所谓/你推荐/
    推荐个/出个主意/想不出来/没想法了/不知道做什么/不知道做啥/帮我拿主意/你帮我定/
    都听你的/怎么都行
  - `APPROVE_WORDS`（y/yes/是/确认/同意/可以/好/好的/行/行吧/ok/okay/没问题/就这样/
    批准/就这么办/妥/搞/做/上）· `APPROVE_NEXT_ACTIONS`（prd/develop/create 动作关键词）·
    `RENAME_RE`（改名叫X/名字改成X/改名为X/把名字改成X/重命名为X/名字改为X）·
    `CLARIFY_WORDS`（？/为什么/啥意思/什么意思/解释一下/不明白/没懂/能改吗…）·
    `CONFIRM_DELEGATE_WORDS`（随便/你定/你看吧/你决定/听你的/你来定/都行/都可以/
    无所谓/你看着办/都听你的/怎么都行）
  - 匹配助手: `split_confirm_first` / `match_approve` / `match_approve_next` /
    `match_rename` / `match_clarify` / `match_delegate`
- **analyzer 确认分类**（`discovery_intelligence.py`）— `ConfirmationAnalysis`
  {category: approve|approve_next|rename|clarify|cancel|delegate|other, next_action,
  rename_to, reason} + `analyze_confirmation(text, product_summary=)`（宽容解析链 +
  schema 校验, 失败 → `ConfirmationLLMError`）
- **conversation 分流重构**（`handle_product_confirm`, 确定性表 → LLM → 改名兜底）:
  控制短语 → 创建项目短语 → 明确改名 → 确认+下一步 → 纯确认 → 澄清 → 取消 → 委托 →
  LLM 分类 → 裸文本改名兜底; `ConversationResponse.next_action`（approved +
  next_action 携带信号）; `_clarify_confirmation` 重展示摘要 + 解释选项（不改名不确认）
- **求助词归一化**（`conversation.py` + `discovery.py` 两路径对称）— `_is_help_request`
  改用 `normalize_help_text` + 新词表（"没 想法" → 建议流, 不填字段）
- **宿主 PRD 接线**（`session.py`）— `resp.next_action == "prd"` → 创建成功后执行
  `generate_prd`（复用 context.product_intent/current_project）→ 消息追加
  "已生成 PRD: projects/<slug>/PRD.md"; 失败 → 注明原因（不阻断创建）;
  develop/create 只传信号, 宿主执行留待后续

### Fixed

- **确认阶段误改名**（Founder 实测）: "可以，先出prd文档" 整句被当产品名 →
  识别为 确认+下一步（approved + next_action=prd）, 名称不被覆盖; "？" 被当名称 →
  智能澄清（重展示摘要 + 解释选项）
- **求助词漏网**（Founder 实测）: "没 想法"（带空格）填进 core_features="想法" →
  去空白归一化 + 词表全覆盖 → 建议流不填字段

### 测试

- 新 `tests/console/test_confirmation_intelligence.py` 34 用例（计划 §2 契约点 1-11:
  确认+下一步/澄清不改名/向后兼容 y·N·改名叫X·裸文本/确认词不当事名/委托词双阶段/
  求助空白变体两路径/LLM 分类路由/无 LLM 兜底真实/宿主 PRD 接线成功+失败/版本断言）
- `tests/console/test_discovery_guide.py` 扩展（+15: normalize_help_text/新词表/
  确认表与匹配助手单元/两路径"没 想法"→建议流）
- 全量 console 回归: 0 新增失败（v1.1.22 基线 4826 passed / 1 skipped 之上）

## [v1.1.22] — 2026-08-24

**产品发现引导体验**（S10-101）: 确定性进度/生命周期 + 中间字段智能追问 + 求助建议填入 —
conversation 与 DiscoverySession 两路径同步。

### Added

- **共享引导模块**（新 `session/discovery_guide.py`）— 两路径唯一来源:
  - `lifecycle_line` 生命周期行（发现→确认→创建→PRD→工程→开发, 当前阶段 `[ ]` 标出）+
    `format_progress` 必填进度（"产品定义 X/3: 字段✅/待填", 用 FIELD_LABELS 中文名）—
    纯状态计算, 无 LLM 也显示（确定性）
  - `enhanced_line` DiscoverySession 增强字段可选提示（使用场景/MVP范围/非功能要求, 已填 ✅,
    无待填省略）
  - `HELP_KEYWORDS` 求助关键词确定性硬闸 + `DEFAULT_SUGGESTIONS` 每字段确定性建议
    （无 LLM 兜底 — 诚实降级, 非伪造 LLM）
- **analyzer 契约扩展**（`discovery_intelligence.py`）— `VALID_CATEGORIES` += `help_request`
  （优先级: 控制指令 > 查询 > 求助 > 字段回答 > 产品描述）; 输出契约 += `suggestions`
  {field, items, note}; field_answer 时若还有必填缺失 → `smart_questions` 给出下一个最重要
  缺失字段的追问（带理由）
- **两路径集成**（`conversation.py` + `discovery.py`, 对称）:
  - 每个发现阶段消息前缀 `lifecycle_line` + `format_progress`（批量/编辑/重问等分支统一）;
    READY 3/3 + current=确认
  - 求助流: HELP_KEYWORDS 硬闸（LLM 前）→ LLM `help_request` + suggestions / 默认建议
    → 展示 → 挂起 proposal {field, items} → 用户 y 全填 / 1-3 单选 / 自定义填入 → 进度更新;
    求助输入绝不当字段内容收下
  - 中间字段: field_answer apply 后下一问优先 `analysis.smart_questions[0]`（带理由）,
    空/失败 → 机械模板; system_question 多轮合并（v1.1.19）保持不变

### 测试

- 新 `tests/console/test_discovery_guide.py` 43 用例（计划 §2 契约点 1-9: 进度确定性/推进/
  中间字段智能/求助 LLM+关键词兜底/不当字段/选择自定义/无 LLM 零变化语义/两路径一致 +
  模块单元）
- 两路径新增用例: `test_discovery_llm_intelligence.py`（+4 求助流/中间字段）·
  `test_discovery_session_llm.py`（+4 同）
- 既有测试更新（仅精确消息断言, 逐条记录）:
  - `test_discovery_llm_intelligence.py::test_prompt_contains_priority_and_history` —
    prompt 优先级有意变更（求助 > 字段回答）
  - `test_discovery_session_llm.py::test_field_answer_fills_current_only` —
    消息断言更新为 S10-101 进度前缀格式
- 全量 console 回归: 4826 passed / 1 skipped / 0 新增失败（7 个既有环境类失败为沙箱写
  ~/.factory/端口检测/wheel 构建, 沙箱外全绿）

### Fixed

- **DiscoverySession 首问进度前缀**（S10-101 验收修复）: `_guide_message` 幂等（body 已带
  `流程:` 生命周期行 → 原样返回）+ `_next_question()` 统一装饰 `question` — `start()`
  `questions[0].question` / `actions.discovery_start` 渲染与 conversation 路径同步带进度/
  生命周期前缀; `_last_system_question`/`_llm_question_text` 保持原始问题（LLM
  system_question 上下文干净, 不双重前缀）


**DiscoverySession 同步 LLM 化**（S10-100）: "开始做X/我想做X" 发现路径与 conversation 路径行为对齐 —
LLM 一次产出 + 智能追问 + 理解摘要 + 主动分析, 无 LLM 规则兜底（逐字段零变化）。

### Added

- **DiscoverySession LLM 集成**（`discovery.py`）— 复用 `DiscoveryIntentAnalyzer`（同 conversation 模式）
  - `start("开始做个记账App")` → LLM 提取 7 字段一次填 → 必填齐直达 READY /
    缺则智能追问 1 条（带 "为什么还问" 理由）
  - `process_user_input` LLM 分流: product_description 提取合并（只填缺失不覆盖, v1.1.19 边界）·
    field_answer 并入既有 apply（当前字段）· control(取消类) → cancel ·
    control(非取消)/query → 不当作字段重问当前问题（模型层不逃生）
  - 确认门: 理解摘要首行 + 需求摘要 + 建议名称候选 + 主动建议 + 确认提示（ai_generated 诚实标记）;
    无 LLM → 现有消息逐字节不变
  - 命名 LLM-gated: 临时名 + analyzer 可用 → suggest_names 候选1设名 + 展示候选;
    无 LLM → 临时名保留
  - 持久化: to_dict/from_dict 新增 `_last_system_question/_ai_generated/_understanding/_proactive`
    （旧会话文件缺省兼容, 不崩）
- **analyzer 契约扩展**（`discovery_intelligence.py`）— `EXTRACTION_FIELDS` +=
  `usage_scenarios/mvp_scope/non_functional_requirements`（可选键, 明确提到才填, 否则留空）;
  prompt 输出 schema 同步 + 规则行; 归一化补默认; conversation 路径只读 5 键, 零行为变化

### 测试

- `tests/console/test_discovery_session_llm.py` 26 用例（一次产出/智能追问带理由/回答并入不覆盖/
  理解摘要+主动分析/无 LLM 零变化/控制查询不当字段/非法输出降级/持久化 round-trip/命名/analyzer 扩展）
- 既有 108 discovery + 35 analyzer + conversation 契约测试 0 破



**LLMIntentParser — 普通对话 LLM 理解意图**（S10-046 §3 Q1 预留扩展点落地）: 每轮对话 LLM 介入。

### Added

- **LLMIntentParser**（`llm_intent.py`）— 自然语言 → LLM 理解 → 注册意图类型 + 参数
  - 只映射注册意图（安全边界, 不生成任意命令）· 低置信(<0.4)/unknown → None
  - 无 key/LLM 失败/非法 JSON → None（规则兜底, 诚实降级）
- **会话装配**（`session.py`）— intent_parser 默认 LLM + `_rule_parser` 规则兜底
  - 真实 LLM 验证: "建个公司叫测试科技"→org_manage · "查一下现在有哪些项目"→list_projects
    "帮我修一下登录的bug"→run_task · "把记账项目挂到财务部"→org_manage
- 纯命令 (/help) 仍走 slash（不该 LLM）

### 测试

- `tests/console/test_llm_intent_parser.py` 8 用例（理解/unknown/安全边界/低置信/无key/失败/非法JSON/code fence）
- 32 相关 passed（无破坏）


**发现阶段多轮字段合并边界修复**（S10-099 遗留改进）: 用户对智能追问的回答被 LLM 当成新产品描述覆盖字段。

### Fixed

- **prompt 注入"系统上一轮问题"**（`discovery_intelligence.py`）— LLM 知道"本轮是对上一问题的回答"→ category=field_answer, 只填对应字段, 不当作新描述
- **conversation 记录追问轮次**（`conversation.py`）— `_last_system_question` 在智能/机械追问时记录, 传入 analyze; 新发现重置
- 验证: "手机上没有顺手又好看的 markdown 编辑器" → 并入 problem, 不再覆盖 name（真实 LLM 实测）

### 测试

- `test_discovery_llm_intelligence.py` +2 用例（system_question 注入 + 回答并入不覆盖）→ 35 passed


**组织管理对话接入**: "建个公司/建部门/把项目挂到部门" → LLM 理解 + 规则兜底 → org CLI（§1.4.5）。

### Added

- **org_manage action**（`actions.py`）— 自然语言组织操作 → 操作序列 → org CLI (create+link)
  - LLM 理解复合句（"成立软件公司建个后端部门" → 多操作序列）
  - 规则兜底（无 LLM/key: 建公司/建部门/挂项目 关键词）
  - 未识别 → 明确请求澄清（不猜测）
- **INTENT_ORG_MANAGE**（`intent.py`）— 建公司/建部门/挂项目 关键词规则
- **路由**（`router.py`）— org_manage → org_manage action

### 测试

- `tests/console/test_org_manage_action.py` 7 用例（意图/路由/规则落盘/未识别）
- 无 LLM 诚实降级（规则兜底, 不伪造理解）


**统一 create 入口**: `factory create <type>` 包装 company/department/project — 便捷铁律落地（§1.4.5）。

### Added

- **`factory create company|department|project`**（`cli_factory.py`）— 一个入口创建任意层
  - company: --name [--template] · department: --company --name · project: --name [--company --departments --goal]
  - project 无 repo 可建（默认数据目录）· 关联公司/部门（可选, Solo 最简）
- 便捷铁律: 前期只建 project 即可用; 组织可选增强; 渐进式挂接（project link）

### 测试

- `tests/console/test_cli_factory_create.py` 6 用例（三类型/Solo/错误路径）
- 与 org 数据模型（v1.1.16）衔接: 项目→公司/部门 关联


### Added

- **产品发现阶段 LLM 深度介入 (S10-099)** — 用户描述 → LLM 意图理解 → 结构化提取
  （替代逐字段追问）→ 智能追问（理解为什么缺）→ 主动分析（平台/竞品/范围）→
  LLM 理解摘要确认（"我理解你要做 X, 给 Y 用, 核心是 A/B/C, 对吗"）；无 LLM/key →
  现有状态机零变化（诚实降级, 不伪造 LLM 理解）。
  - **`session/discovery_intelligence.py`（新）** — `DiscoveryIntentAnalyzer`：
    意图优先级（控制指令 > 查询 > 字段回答 > 产品描述）+ 结构化提取
    {problem, user, core_features, name, platform} + 缺失原因 + 智能追问（≤3,
    优先 1 条）+ 主动分析 + 理解摘要；默认复用 `ReasoningProvider._default_llm_fn()`
    装配（同命名修复 bcc1b14 模式）；JSON 宽容解析链（剥 code fence →
    `json.loads` → `{...}` 子串回退）+ schema 校验；任何失败 →
    `DiscoveryLLMError` → 规则兜底。
  - **`conversation.py` 最小集成** — `start_product_discovery` 初始描述即解析
    （必填齐直入确认 / 缺则智能追问）；`handle_product_answer` 确定性 `_product_control`
    硬闸之后按 LLM category 分流（control→既有控制行为 / query→逃生 /
    product_description→提取合并 / field_answer→既有逐字段）；
    `_enter_product_confirmation` 展示 LLM 理解摘要 + 主动分析（仅 LLM 真产出时,
    `ai_generated` 诚实标注）。
  - **`ConversationResponse` 新增可选字段** `understanding` / `proactive` /
    `ai_generated`（缺省零影响, 前端/日志可区分）。
  - **契约测试** — `tests/console/test_discovery_llm_intelligence.py`（mock LLM
    注入, 不依赖真实 key；覆盖计划 §5 契约点 1-7）。

### Fixed

- **产品发现"太模板化"根因** — 用户初始自然描述只存 `raw` 从不解析 → 逐字段机械
  追问。修复: LLM 可用时初始描述即理解提取, 一次产出结构化定义（"我想做个
  markdown 编辑器..." 一次直达确认）; "整理一下" 类模糊控制不再被当字段（LLM
  分类 control → 整理不创建）; 无 LLM/key → 规则状态机逐字节不变（诚实降级）。

---

## [v1.1.16] — 2026-08-24

**组织×工作正交数据模型**: Project 关联公司/部门（渐进式, 多对多可选）— 从"单层项目工具"迈向"公司 OS"（§1.4.5）。

### Added

- **Project.company_id + department_ids**（`org/projects.py`）— 归属公司 + 关联部门（多对多可选, 默认值向后兼容）
- **register 支持 --company/--departments**（`org/cli.py`）— 注册项目即可关联组织（可选, Solo 最简）
- **company department create**（`org/cli.py`）— Department 模型补 CLI（渐进式建部门）
- **project link**（`org/cli.py`）— 项目挂接/解绑部门（渐进式: 先项目后组织, 无损升级）
- **_dispatch 嵌套子命令**（`org/cli.py`）— company department create 展平分发

### 测试

- `tests/org/test_org_project_org_link.py` 5 用例（字段默认/注册关联/link/unlink/错误路径）
- org 全量 861 passed · 向后兼容（旧项目零破坏）


### Fixed

- **产品命名 LLM 未接线（S10-081 设计缺口）** — `conversation.py` 调用
  `suggest_names` 时硬编码 `llm_fn=None`，导致 LLM 命名 prompt 从未生效，
  产品名永远走 deterministic 规则提取（"markdown编辑器需"式模板化根因）。
  修复: 接上 `ReasoningProvider._default_llm_fn()`，无 provider/key → 诚实回退
  deterministic（不伪造 LLM 结论）。40 相关测试通过。

**M3e 调度器接管真实执行 + 动态分配 (S10-097)**: M3 收尾 — M3a-d 计划层产物
正式驱动真实执行 (不再走旧 TaskTree 顺序路径)。

### Added

- **`orchestrator.execute_project(mode="m3")` 全链分支** — DecomposeEngine
  (复合→原子) → CriticalPathEngine (关键路径, 落盘 plan.json/dependencies.json)
  → TaskScheduler (依赖就绪轮次 + 同文件冲突 ConflictResolver 串行) → 每轮
  AgentMatcher 实时动态分配 → ExecutionLoop 执行 (复用 `_execute_with_retry` +
  Validator) → 每任务 EvidenceBundle 落盘 evidence/ (M1a 复用) → 审计 → 下一轮。
  默认 `mode="solo"` 旧路径零变化; 输出同既有结果结构 + `state.m3 = {rounds,
  assignments, evidence}`。
- **动态分配 M3-4** — 每轮就绪叶子 `AgentMatcher.match` 实时匹配 (skill × 历史
  成功率, 复用 agents.py 不修改); 分配落盘 `state.m3.assignments`
  [{round, task, agent_id}]; 空注册表 → 无匹配诚实报告 (不伪造分配)。
- **审计 5 事件** — `EXECUTION_ROUND_STARTED` / `EXECUTION_TASK_ASSIGNED` /
  `EXECUTION_TASK_COMPLETED` / `EXECUTION_ROUND_COMPLETED` /
  `EXECUTION_M3_DEGRADED` (注册表 + 真实发射)。
- **失败安全** — 单任务失败不中断整链 (标记 failed, 后续轮次继续); M3 链任何
  异常 → 降级 solo 顺序执行 (`EXECUTION_M3_DEGRADED` + `state.m3.degraded=True`
  诚实标注, 不伪造 M3 执行)。
- **契约测试** — `tests/console/test_m3e_full_chain.py`: 全链真实执行 (复合任务
  → M3 链 → 真实执行 → 项目目录产物) / 动态分配断言 / 旧路径零变化 / 单任务
  失败不中断 / 冲突串行 (同文件不同轮) / 失败回退 solo。

### 边界 (S10-097 §8, 未做)

- ❌ 轮内并行线程化 (轮内仍依序, 线程后置)
- ❌ 原子沙箱改造 / M3f / M3g (后续)


**M3d 拆解质量评估 + LLM 深度拆解 (S10-095)**: M3 三部曲之后补上**质量门控** —
拆解完先验质量（六维确定性评分），不合格诚实降级，不伪造 LLM 质量；同时
LLM 深度拆解升级为结构化产出并接入门控。

### Added

- **DecompositionEvaluator** (`session/decomposition_evaluator.py`) —
  `evaluate(decomposition, task, context)` → `{score, dims{完整性25/粒度20/
  依赖20/可行性15/可测性10/风险10}, decision, reasons}`; 六维确定性规则
  （完整性=core_features 覆盖 / 粒度=原子四条件通过率 / 依赖=cycle_detect+
  关键路径合理性 / 可行性=agent∈capabilities / 可测性=verify_cmd 覆盖率 /
  风险=risks 标注存在），score=Σ(维×权重)。
- **四档行动** — ≥0.9 `adopt`; 0.7-0.9 `adjust`（`adjust()` 自动修正: 补缺失
  feature / 补默认 verify_cmd / 修剪依赖环 → 修正后采用，标注 adjusted）;
  <0.7 `reject`（回退确定性技术层模板, 诚实降级）; <0.5 `ask_user`（返回
  questions, REPL 层处理后重评）。
- **decomposer 最小集成** — `decompose()` 后置评估（`evaluator` 可注入,
  `evaluate_after` 默认开）; `llm_fn` 产出结构化 `{tasks:[{id,name,
  requirement,depends_on,verify_cmd,est,risks}], summary}` → 质量门控;
  无 LLM → 确定性 leaves 照常评估（不跳过）; reject/ask_user → 确定性兜底。
- **落盘 + 审计** — `evaluation{score,dims,decision,reasons}` 进
  `decomposition.json` state + evidence 证据包（`EvidenceBundle.evaluation`）;
  审计事件 2 个: `EVAL_COMPLETED` / `EVAL_REJECTED_FALLBACK`（EVENT_TYPES
  52→54）。
- **契约测试** `tests/console/test_m3d_evaluator.py` — 17 例: 六维手算对照 /
  好拆解 adopt / 差拆解 reject 回退 / ask_user questions / adjust 自动修正 /
  无 LLM 照常评估 / evidence+审计落盘 / 向后兼容（评估器可选、M3a 零变化）。


**M3c 并行调度执行 (M3-3, S10-090)**: 原子任务不再简单顺序跑 — 消费
plan.json (M3b 依赖边) + execution_state → 依赖就绪队列 + 同文件冲突串行化 +
并发上限分桶 → 调度轮次 (rounds) 落盘 schedule.json (可审计可回放)。

### Added

- **TaskScheduler** (`session/scheduler.py`) — `schedule(plan, state,
  max_concurrency=1, agent_matcher=None, conflict_resolver=None)` →
  `{rounds, order, conflicts, state}`; `ready_tasks(completed)` 入度=0 就绪;
  并发分桶 (`_concurrency_bucket`, max_c=1 → 每轮单任务 = 旧顺序零变化)。
- **冲突串行化复用** — 同 `target_file` 冲突检测 → `ConflictResolver.resolve`
  (S10-057, 不修改核心) → 冲突任务不同轮 + `conflicts[]` 记录
  `{task, reason, resolution}`。
- **失败安全** — 环 / 无 plan → 降级顺序执行 (`schedule.json` + 执行状态
  `degraded=True` 诚实标注, 不伪造并行)。
- **落盘** — `projects/<slug>/schedule.json` `{rounds, order, conflicts,
  max_concurrency, created_at}` (可审计)。
- **orchestrator parallel 模式** — `execute_project(mode="parallel",
  max_concurrency=N)`: 消费 plan.json → rounds 依序执行 (同轮内按现有执行链
  跑); 默认 solo 完全不变 (零新增落盘字段, state.schedule 仅 parallel 非空)。
- **契约测试** `tests/console/test_m3c_scheduler.py` — 6 种手算对照 (无依赖
  并行 / 单链 4 轮串行 / 汇聚先并行后串行 / 同文件冲突串行 / 并发上限分桶 /
  max_c=1 向后兼容) + 落盘 + 环降级 + orchestrator parallel 集成。

---

## [v1.1.12] — 2026-08-23

**M3b 关键路径标注 (M3-2, S10-090)**: M3a 原子叶子（树关系）补上横向依赖边
(DAG) + 关键路径（最长链 CRITICAL 标注）+ merge 汇聚点 + 整链预估 —
"拆到不能拆" 之后告诉执行层哪些任务在最长链上、哪些是汇聚点（计划层标注,
不调度）。

### Added

- **CriticalPathEngine** (`session/critical_path.py`) — 依赖边推断 + 关键路径
  算法 + merge 标注 + 落盘 `projects/<slug>/plan.json` + `dependencies.json`。
- **依赖边推断 4 来源** (设计 §1) — ① 技术层确定性链（同 feature:
  db→api→frontend→test, 硬编码模板兜底）② 跨 feature 共享（共享 target_file /
  共享模块目录, 确定性检测）③ LLM 注入点 `llm_fn(leaves, edges)`（失败 → 跳过,
  不伪造）④ 落盘 dependencies.json 复用（`load_dependencies` 回注）。
- **关键路径算法** (设计 §2) — 复用 `dependencies.py` `add_dependency`（成环
  逐条拒绝 + 审计）→ `topological_order` → `dist[task]=max(dist[dep])+est`
  → 最长链回溯 → `estimated_duration`。
- **merge point** (设计 §4) — 入度 ≥ 2 节点 → `merges[]`（只标注, 不调度）。
- **CRITICAL 落盘** — `plan.json.tasks[]` 每任务 `critical: bool`（关键路径上
  = True）+ `summary_text` CLI 展示。
- **失败安全铁律** — 环 → 拒绝 + `PLAN_KEYPATH_COMPUTED(status=cycle_rejected)`
  审计, 不产出关键路径（诚实不伪造）; LLM 失败 → 确定性技术层链; 异常 →
  部分结果 + error; 落盘故障 → None。
- **审计事件 2 个** — PLAN_KEYPATH_COMPUTED / PLAN_MERGE_MARKED
  (`audit/audit_event.py` EVENT_TYPES 50→52)。
- **actions.execute_project 接线** — 拆解后前置标注（`FACTORY_CRITICAL_PATH=0`
  关闭, 默认开; 失败安全不中断执行; data 附 critical_path 摘要 + message 附
  summary_text）。
- **契约测试** `tests/console/test_m3b_critical_path.py` — 16 用例: 5 种 DAG
  （单链/分叉/汇聚/环/无依赖）手算对照 + 技术层链 + 共享/LLM 推断 + 落盘 +
  审计事件 + M3a 无依赖边向后兼容。

### 边界（不做）

- M3-3 并行调度执行 / M3-4 动态 Agent 分配 / 质量评估 — 后续 Sprint。
- `dependencies.py` 核心零修改（只读复用）。
- 向后兼容: M3a decompose 无依赖边输入 → 默认技术层链（不崩溃）。

---

## [v1.1.11] — 2026-08-23

**M3a 递归原子拆解引擎 (Sprint, S10-090)**: 复合任务 → 原子叶子（单 Agent /
单文件单工具 / 可验证 / ≤10min）— "拆到不能拆" 直接提高执行成功率（"一步一个坑"
根因 = 任务粒度太粗）。

### Added

- **DecomposeEngine** (`session/decomposer.py`) — 递归拆解: `decompose(task,
  product, capabilities, llm_fn)` → {leaves, tree, state} + 落盘
  `projects/<slug>/decomposition.json`。
- **原子判定四条件** (§3.7.3) — 确定性优先 + LLM 注入点: ① 单 Agent（能力表
  候选=1）② 单文件（target_file 提取）③ 可验证（语言→验证命令映射）④ ≤10min
  （关键词启发）。
- **拆分单向推进** `_split_mode: root→features→technical→final` — 防同层反复
  拆死循环; final 层仍不原子 → `atomic(unverified)` 诚实标注（能力边界, 不伪造）。
- **递归防护** — `_max_depth=5` + `_max_tasks=64` + 祖先链环检测 →
  `DECOMPOSE_CYCLE_REJECTED` 审计事件。
- **失败安全铁律** — LLM 失败/无 LLM → 确定性拆分非空; 异常 → 部分结果 + error。
- **审计事件 5 个** — DECOMPOSE_STARTED / ATOMIC / SPLIT / CYCLE_REJECTED /
  COMPLETED (`audit/audit_event.py` EVENT_TYPES 45→50)。
- **actions.execute_project 接线** — 执行前拆解（`FACTORY_DECOMPOSE=0` 关闭,
  默认开; 失败安全不中断执行; data 附 decomposition 摘要）。
- **契约测试** `tests/console/test_m3a_decomposer.py` — 11 用例: 四条件断言 /
  深度收敛 / 成环拒绝 / 无 LLM 降级 / 深度上限诚实 / 状态落盘 / 旧流程兼容。

### 边界（不做）

- M3-2 关键路径 / M3-3 并行调度 / M3-4 动态分配 / 质量评估 — 后续 Sprint。
- 非叶子节点编排 Loop 仅接口/事件占位（M3b+）。
- 向后兼容: 旧 TaskTree/FeatureTaskGenerator 流程不破坏。


**专家真干活 (Sprint, S10-088)**: 生产路径接真实 LLM + 专家交接消费上一产出 +
PRD 消费专家资产 + 专家团队落盘 — M2→M1 消费链打通 (Claude M2 评估: "骨架诚实、
产出未兑现" 的下一刀)。

### Added

- **product_pipeline 生产路径接 LLM** (T1) — `actions.product_pipeline` 装配
  `ReasoningProvider._default_llm_fn()` (有 providers.json + key → 真调 7 专家);
  无 LLM → 确定性兜底非空 (诚实, 不静默)。`llm_fn` 注入点保留 (测试/生产同路径)。
- **HandoffBus 交接消费上一产出正文** (T2) — `route` 每步经
  `ArtifactRegistry.read` 读上一资产 content, 作为 produce 第 4 参传入;
  `ProductPipeline._produce` prompt 嵌 `上一资产内容: <前 2000 字>` (而非仅 id);
  血缘双字段 (parent_artifact + parent_event_id) 保留。
- **prepare_project 消费专家 prd 资产** (T3) — 项目存在 HandoffBus 产出的
  `prd` 资产 (created_by=agt-*) → 用专家产出生成 PRD.md (M2→M1 打通);
  无专家资产 → 规则兜底 (向后兼容)。
- **build_team 落盘专家注册表** (T4) — `ExpertFactory.build_team` 装配后
  `registry.add` 落盘 agents.json (persist=True 默认, 项目内 agents.json 含 7 个
  agt-*); `persist=False` 保留不自动落盘选项。
- **真实产出断言** (T5) — 注入 fake llm_fn → market/全 7 资产含 LLM 真实内容
  (非 "待补充/规则占位" 段落)。

### Validation

- `我要做CRM` → `让PM分析` → 7 专家 LLM 产出 + 互引 → `准备开发` → PRD.md 含专家内容
- 全量回归 0 failed (runtime flaky 除外); 版本断言 v1.1.10 同步
  (pyproject/install.sh/docs/CHANGELOG/test_s10_074_deployment.py)



**M2 员工内核 (Sprint)**: "我要做CRM" → 7 个真实 Agent 实体交接产出 —
用 AgentEntity/ExpertFactory/HandoffBus 替换"7 个 prompt 换提示词"的单模型循环。

### Added

- **`session/agent_entity.py`** (A1) — AgentEntity 专家身份模型
  (id/role/industry/provider{id,model}/system_prompt/skills/knowledge_ref/
  workflow_ref/memory_ref/tools/evaluation_ref/profile): `agt-` 前缀 id
  (agt-<industry>-<role>-<n>), to_dict/from_dict roundtrip, 缺必填字段明确报错;
  provider 可空 (无 LLM → 确定性兜底可用)。
- **`session/agent_registry.py`** (A2) — 工厂层专家注册表
  (add/get/list/remove/next_id): 行业命名空间 it.* / ops.* 隔离, 同 role 多
  provider 并存 (id 唯一), agents.json 键值持久化。
- **`session/expert_factory.py`** (A3) — 专家装配器: assemble(role, industry,
  skills, knowledge_ref, workflow_ref, provider) → AgentEntity; 校验 skill 存在
  / workflow 可执行 / knowledge 可挂载, 缺 skill 明确报错 (不静默); build_team
  装配 7 软件行业专家; 无 LLM → deterministic_content 确定性兜底非空。
- **`session/handoff_bus.py`** (A4) — 交接总线: send/route (PM→Market→
  Competitive→UX→Architect→QA→SeniorPM); 消息 {from, to, artifacts[],
  decisions[], constraints[]}; 血缘双字段 metadata.parent_artifact +
  parent_event_id; 冲突 → ConflictResolver → ReviewGate 挂起等审批
  (status=pending_review); 消息落盘 m2_handoffs.json。
- **product_pipeline 接线** (A5) — "让PM分析" 走真 Agent 链:
  ExpertFactory.assemble + HandoffBus 替换 7-prompt 循环; 每资产
  created_by=agent_id (agt- 前缀); M1 资产类型/版本递增/审计血缘零回归。
- **`tests/console/test_m2_agent_core.py`** (M2-6) — A1-A5 契约测试套件
  (schema/接口/血缘/错误码, 36 passed)。

### Validation

- `让PM分析` → 7 资产互引 (parent_artifact 链), 每资产 created_by 以 agt- 开头;
- 引用不存在 skill → ExpertAssemblyError 明确报错; 无 LLM 环境 → 各角色确定性
  兜底非空; 冲突交接 → ReviewGate 挂起等审批;
- M1 链路 (repo/evidence/approval/backlog) 零回归。

---
## [v1.1.8] — 2026-08-21

**M1 闭环补全 (Sprint)**: 从证据到签字到落地最后一公里 — approve 后不再死路。
采纳 Claude 审查 P0/P1: approval apply 接入主 CLI + demo 全 dependency + 解析
失败模板提示 + evidence/approval 交叉引用。

### Added

- **`factory approval apply <id> [--project <dir>]`** (T1, P0) — 薄代理
  `ApprovalGate.apply` (主 CLI 经 exec CLI 同源 `cmd_exec_approval_apply`):
  仅 **APPROVED** 可应用 patch 到目标项目; 未批准/已拒绝 → 硬拒绝 (不绕过
  门禁); 已应用 → 拒绝重复应用 (幂等); 非 git 目标 → 响亮错误 (应用前须
  可审计)。
- **decide approve 后提示下一步** (T1, P0) — 审批通过后打印
  「已批准。下一步: factory approval apply <id> --project <repo> 可应用」,
  演示闭环不再死路。
- **demo/repo issues.json 默认全 dependency** (T2, P0) — 3 个 dependency issue
  (缺少 requests / 缺少 httpx / 升级 flask 到 3.0.0), 无 LLM 也 3/3 确定性
  修完; 演示完整闭环: 3/3 修完 + approve + apply 落地。
- **无 LLM skipped 文案优化** (T2) — bug/feature 未配置 LLM 时明确提示
  「需要 LLM(未配置)。配置后可用 factory init 解锁 bug/feature 修复」。
- **dependency 标题解析失败模板提示** (T3, P1) — 无法解析时报告提示
  「标题无法解析, 建议改成 `缺少 X 依赖` 或 `升级 X 到 V`」。
- **evidence/approval 交叉引用** (T4, Minor) — `approval list` 每行附证据包
  id; `evidence show` 附关联审批状态 (请求 input.evidence_bundle_id 锚点);
  修复 EvidenceStore.list() 排序 (文件名 uuid 字典序 ≠ 创建序 → 按
  created_at), 保证证据包↔审批一一对应不串包。

### Validation

- 实测 demo 完整闭环: `factory workload backlog --project demo/repo` →
  3/3 fixed (各自独立证据包 + pending 审批) → `factory approval list` (每行
  附证据包) → `factory approval decide <id> approve` (提示下一步) →
  `factory approval apply <id> --project demo/repo` (patch 真实落地) →
  `factory evidence show` (附审批状态); 重复 apply 硬拒绝。
- 新增测试: tests/console/test_approval_apply.py (10) + test_workload_backlog
  新增 5 (3/3 fixed / demo 默认全 dependency / 无 LLM 文案 / 解析失败模板 /
  交叉引用); 全量回归 0 failed (runtime 沙箱 flaky 除外)。

---

## [v1.1.7] — 2026-08-20

**M1b 积压清道夫 (E3 第一个可售卖工作负载)**: 分诊 → 执行 → 证据包 → 审批 → 报告
+ M1a Review 3 个 Minor 修复。

### Added

- **`factory workload backlog --project <dir>`** — BacklogSweeper 积压清道夫
  (`session/workloads/backlog_sweeper.py`): 读取项目 `issues.json`
  ([{id,title,type}]) → 分诊 (bug/feature/dependency → 修复策略) → 对每个
  issue 执行 (复用 RepoModeRunner Execution Kernel → Sandbox patch + pytest)
  → 组装 EvidenceBundle (diff+测试+日志+决策+变更文件, 落盘
  `projects/<slug>/evidence/`) → 自动请求审批 (复用 ApprovalGate) → 运行报告
  (`projects/<slug>/sweeps/sweep-*.json`)。
- **确定性依赖修复** — `DependencyPatchGenerator`: 真实分析 requirements.txt /
  pyproject.toml, 生成可应用 unified diff (无 LLM 也能「干完一件看得见的活」);
  bug/feature 走 LLM patch (无 LLM → 诚实 skipped, 不伪造)。
- **`factory workload status --project <dir>`** — 最近一次清道夫运行报告 (只读)。
- **`factory approval list [--project X]` / `factory approval decide <id> approve|reject`**
  (T2, Minor #2) — 待审批列表 + 审批决策, 复用 exec ApprovalGate (终态落库 +
  org.execution.approved 审计), 与 `factory-exec approval` 同源。
- **EvidenceBundle 接入普通执行** (T3, Minor #3) — `execute_project`/`resume`
  完成后自动组装证据包 (`EvidenceBuilder.from_execution_result`, 复用
  from_repo_result 模式), `factory evidence list` 可见。
- **logs 字段填充** (T4, Minor #1) — 组装证据包时填充执行日志 (执行事件摘要:
  理解/计划/patch/测试; 任务队列/验证/终态), 失败安全。
- **demo/repo** — BacklogSweeper 演示仓库 (main.py + 测试 + requirements.txt +
  issues.json: dependency 可确定性修复, feature/bug 需 LLM)。

### Validation

- 实测: `factory workload backlog --project demo/repo` → ISS-001 dependency 真实
  修复 (requirements.txt 变更 + 测试✅) + 证据包可见 + pending 审批; approval
  list/decide 全链路可用。
- 新增 31 测试 (test_workload_backlog 20 / test_evidence_attach 7 /
  test_approval_decide 9 含注册); 全量回归 0 failed。

---

## [v1.1.7] — 2026-08-21

**产品方案书 v3.0（终极版）合并**: 完整产品方案书更新为终极版（2656 行，12 章：
复杂任务拆解/多Agent编排/审计可观测/治理合规/学习进化/RAG/工具生态/行业工厂/
全部交互场景/演进路线/术语表），旧版独有章节（战略愿景/领域智能架构/生态对比/
附录）保留为 §十三 不丢失。
另: M1b 依赖修复收尾（中文升级句式 + 版本满足幂等, backlog_sweeper.py）。

---

**M1 内核切片（AI Company OS 第一块地基）**: 存量仓库模式 + 工具发现 + 真 MCP 客户端。

### Added

- **`factory repo <path> <目标> [--patch]`** — 存量仓库模式: 理解(core/understanding) →
  计划(LLM 或确定性) → patch 应用(Sandbox 副本, 原仓库零影响) → pytest 验证。
- **`factory tools list`** — 发现本机 AI CLI (codex/hermes/openclaw/claude) +
  MCP server 配置 (~/.codex/config.toml / ~/.claude.json / .mcp.json)。
- **StdioMCPClient** — 真 MCP stdio 客户端 (JSON-RPC 2024-11-05, 不绑第三方 SDK);
  工具是增强层, 任何任务不依赖外部 CLI 完成。
- **core_loader** — 延迟加载 factory-core/factory-exec (对齐 actions 模式)。

### Validation

- 实测: 临时 git 仓库 + patch → 变更文件 + pytest 通过; tools 发现 3 CLI + 2 MCP。
- 新增 21 测试; tests/console+exec 5791 passed; 全仓库 11805 passed。

---

**S10-084 Product Intelligence Pipeline (P0)**: 从 Idea 到 PRD 的多角色资产链。

### Added

- **ArtifactRegistry** (`session/artifact_registry.py`): 版本化资产注册表
  (`projects/<slug>/artifacts/<type>/v<n>/artifact.md + artifact.json`, v+1 递增,
  旧版本保留 — 渐进明细/变更前提)。
- **ProductPipeline** (`session/pipeline_runner.py`): 7 角色资产链
  (PM→product / Market→market_analysis / Competitive→competitive_analysis /
  UX→ux_flow / Architect→architecture / QA→test_plan / SeniorPM→prd),
  LLM 可用 → 角色 prompt; 失败/无 LLM → deterministic 兜底 (复用既有引擎)。
- **审计血缘**: 每资产 `ARTIFACT_CREATED` 事件 (artifact_reference + parent_event_id 链)。
- **discovery.md 落盘**: "先帮我整理需求，不要创建项目" → 需求快照落盘为
  discovery 资产 (draft), 不创建项目。
- **入口**: 意图 `让PM分析/产品管线` + action `product_pipeline` + 路由。

### Validation

- 新增 8 测试 (registry 3 + pipeline 3 + action/intent 2 + discovery 1)。
- `tests/console` 全量通过 (4488, 含既有回归); 全仓库 11760+ passed。

### Notes

- 需求变更与渐进明细闭环 (ChangeProposal → 影响分析 → 审批 → 资产 v+1 →
  ReplanningEngine) 为 P1, 见 docs/sprint10/S10-084-plan.md §4。

---

**Discovery 沟通修复 (S10-082 遗留问题 #1 落地)**: 产品发现流程不再把一切输入当字段答案,
控制指令/查询/编辑与字段回答分层处理。

### Added

- **控制短语 (非答案)**: 发现/确认阶段识别 `取消` / `整理需求不创建` / `项目列表` / `创建项目`
  等指令, 不再被吞成字段答案 (问题/用户/核心功能)。
- **批量问题模式**: `问题有点多` → 一次性列出剩余必填问题; 支持 `问题:...; 用户:...; 功能:...`
  一次填充多个字段 (自动去标签前缀)。
- **修改已有信息**: `把目标用户改成创业公司` / `修改一下，功能改成X` 更新已填字段
  (发现阶段与确认阶段均支持, 确认阶段普通文本仍是改名)。
- **创建引导**: 信息不足时 `现在创建项目` → 列出还缺字段并询问是否补充 (不再创建空名项目)。

### Fixed

- 发现阶段输入其它意图 (`我现在有哪些项目` 等) 时, 产品流程让位, 原输入走普通意图链。

### Validation

- 新增边界测试覆盖: 正常发现/多段填充不重问、用户打断→项目查询、创建引导、
  任意阶段取消、修改已有信息 (含反例不误判)。
- `tests/console` 全量通过 (4470+ 用例, 含既有回归)。

---
## [v1.0.0-rc1] — 2026-08-07

首个发布候选: **AI Software Factory v1.0 全能力落地**。Core + Extension + Intelligence
+ Human Console 四层齐备, 真实项目 (MarkPad) 走通完整生命周期, 4111 后端测试 +
92 前端测试全绿。

### Architecture

- **Core 冻结 (8 项通用原语)**: 状态管理 · 生命周期 · 调度 · 执行抽象 · 事件审计 ·
  恢复 · 观测基础 · 组织 — `events/ tasks/ workflows/ agents/ assignment/ execution/
  runtime/ runtimes/ recovery/ orchestration/ validation/ metrics/ dashboard/ project/
  workspace/ cli/`。冻结后不修改 Core 行为, 新能力一律走 Extension 声明式注册。
  冻结审查: [docs/architecture-freeze-2026-08.md](./docs/architecture-freeze-2026-08.md)。
- **Extension 系统 (声明式注册, 零 Core 破坏)**: `understanding/ product/ providers/
  git/ change/ changeflow/` — 依赖面仅 `events` + 区内, 删除任一 Extension 不影响
  Core 运行 (有测试断言, 如 `test_product_removal.py`)。
- **Intelligence 层 (只读复用, 决策/推荐/经验)**: `intelligence/` — Decision
  (决策链 + Evidence 六来源强制 + Risk R1–R5 + Approval 绑定)、Recommendation
  (四因素可解释评分 0.35/0.30/0.20/0.15)、Experience (五域 + 30 天半衰期衰减)。
- **Human Console (人在环上)**: `factory-console/` — React 7 页面 + FastAPI
  8 只读 GET 路由, Simple/Expert 双模式, 零写 API (人工审批走 CLI 决策动词)。

### Capabilities

- **Idea → Development 生命周期**: 12 阶段模型 (docs/lifecycle-model.md) 中 6–9
  完整实现, 1–5 由 Product Intelligence 承接, 10–11 部分支撑。software_project
  8 阶段链: `idea → research → prd → [approval] → ui → [approval] → architecture
  → task`。`factory demo markpad` 一键走通 (docs/demo-guide.md)。
- **Decision Intelligence (Phase 9c / 10A-2)**: 决策链 (Product → Architecture →
  Task Plan)、Evidence 六来源强制、Approval 状态机 (5 态终态可逆, 高风险自动绑定
  人工审批)、三类挡板 (产品冲突/架构变更/Scope 扩展)。
- **Provider Intelligence (Phase 8A–8B3)**: LLM Provider 抽象 (统一 I/O + Adapter +
  Registry)、四因素可解释推荐 (Capability/Cost/Performance/Experience)、Cost/Usage/
  Performance 聚合, 换 Provider = 改配置。
- **Experience Loop (Phase 10A-4)**: 成功/失败/审批经验五域沉淀, 30 天半衰期新鲜度
  衰减, 推荐回馈 "影响但不支配" (冷启动中性分, 不惩罚新候选)。
- **可观测与恢复**: 事件是唯一事实源 (append-only SQLite), Dashboard 20 视图,
  六域指标, checkpoint + 事件回放断点续跑。
- **CLI**: 23 命令组 / 77 叶子命令。

### Validation

- **MarkPad 真实项目验证 (Phase 12B)**: 表格编辑器增强需求走通
  `Idea→Research→PRD→[审批]→UI→[审批]→Architecture→Task→Experience` 完整闭环 —
  **34 事件 / 6 Artifacts / 2 经验 / 2 次人工审批 / Core 零修改**。
  详见 [docs/real-world-validation.md](./docs/real-world-validation.md)。
- **测试**: **4111 pytest 全绿** (24 个域, 基线只增不减) + **92 Vitest** (Web UI
  12 文件)。分域明细见 [docs/quality-report.md](./docs/quality-report.md)。
- **架构冻结审计 (2026-08-06)**: 四层依赖单向向下、无循环 import、Extension 隔离
  复核通过 (docs/system-architecture-review.md)。
- **流程**: Phase 0 → 14B, **48 次提交**, 每阶段独立可交付、可回退;
  ADR-0001–0035 (docs/adr/), 设计文档 30+ 篇。

### Known limitations (v1.0.0-rc1 边界)

本版本为**单机、单人、开源核心**里程碑, 以下能力明确不在 v1.0 范围:

- **无 SaaS / 多租户托管**: 无云端托管服务, 无租户隔离、无账号体系; 部署与运维由使用者自理。
- **无身份认证/授权**: CLI 与 Human Console 均为本机信任模型, 无登录、无 RBAC;
  请勿直接暴露到公网。
- **无支付/计费**: 不包含用量计费、账单、订阅; Provider 成本仅用于推荐评分与观测。
- **无市场 (Marketplace)**: 无 Skill/Agent/Workflow 的在线分发市场; 共享靠 git 分发
  + Extension 声明式注册。
- **反馈闭环为设计稿**: docs/feedback-model.md 定义接口契约, 采集/分类后台留待未来
  Feedback 阶段实现 (本阶段不落库、不建服务)。

---

## 版本记录约定

- 自 v1.0.0-rc1 起维护本文件; 每阶段交付追加一节 (Keep a Changelog:
  Added / Changed / Fixed / Removed)。
- 测试基线随阶段只增不减 (pytest 全量绿 + Vitest 全量绿为合入门槛)。

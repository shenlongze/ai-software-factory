# S10-112 Hermes 提示词 — P0-10 注册表一致性 + P0-11 对称路径一致性

> 用途: 复制给 Hermes，独立核对注册表 vs 实现 → 修不一致 → 契约测试固化。
> 主线: 待办清单 P0-10/P0-11（Founder 担忧"改不全有遗漏"）。

---

## 任务标题
**S10-112 P0-10 注册表一致性测试 + P0-11 对称路径一致性测试**

## 背景（Founder 核心担忧）

Founder 长期担心"**改不全、有遗漏**"（新增命令没同步测试/文档、改了 A 忘了 B、
CLI/API 不对称）。P0-10/P0-11 就是**防遗漏机制**：任何注册表漂移或对称路径
不一致 → 测试红 → 强制同步。

当前基线: v1.1.80 · 全量 ~12500 passed · M3 主线 7/7 · 员工管理 A-1 完成。

---

## 规格

### P0-10 注册表一致性测试套件

**目标**: 断言"注册表 vs 实现"一致 — 新增命令/意图/action/事件/API 必须同步
注册表, 否则测试红。

**覆盖 5 类注册表, 各 ≥1 测试**:

1. **CLI 命令注册表** (`factory-console/cli_factory.py` build_parser):
   - 断言 `factory help` 输出包含全部子命令 (从 parser 动态读)
   - 断言 test_console_cli.py 的 subcommands 集合 == parser choices (防新增命令漏同步)
2. **意图注册表** (`factory-console/session/intent.py` _KEYWORD_RULES + intent_type):
   - 断言 router.DEFAULT_ROUTES 覆盖全部意图 (防新增意图漏路由)
   - 断言新意图有 action 注册 (build_default_actions)
3. **Action 注册表** (`build_default_actions`):
   - 断言 router 引用的 action 名都在 registry (防路由断链)
   - 断言敏感 action (SENSITIVE_ACTIONS) 集合 == registry 中 sensitive 标记
4. **事件注册表** (audit event types):
   - 断言 audit_events 记录的事件类型与 event 枚举/文档一致 (防新增事件漏记录)
5. **API 端点注册表** (fastapi_adapter):
   - 断言 CAPABILITY_MATRIX 的 API 列 ↔ 实际路由存在 (防能力声明但 API 缺失)
   - 断言 web 写路由白名单测试覆盖全部 POST/PATCH/DELETE (已有 test_write_routes, 扩展)

**实现**: 新建 `tests/console/test_s10_112_registry_consistency.py`,
注册表数据从**实现动态读取** (build_parser / DEFAULT_ROUTES / build_default_actions /
audit event 枚举 / app.routes), 断言两两一致。

### P0-11 对称路径一致性测试

**目标**: 同场景下 conversation/discovery、CLI/API 行为对齐 — 改一个对称实现,
另一个必须同步验证。

**覆盖**:

1. **conversation vs discovery** (两条产品发现路径):
   - 同输入 → 同状态推进 (start_product_discovery vs conversation.start)
   - 同字段提取/追问结果 (字段归类一致)
2. **CLI vs API** (同能力双入口):
   - agent list ↔ GET /api/agents
   - skill list ↔ GET /api/skills
   - project list ↔ GET /api/projects
   - board 文档 ↔ docs 配置命令
   - 断言: CLI 输出结构 == API 返回结构 (同数据源)

**实现**: 新建 `tests/console/test_s10_112_symmetric_paths.py`,
每个对称路径一个测试 (同 fixture 数据, 双入口断言一致)。

---

## 范围声明（硬边界）

- ✅ 只加: 2 个契约测试文件 (registry_consistency + symmetric_paths) + 修复测试
  发现的不一致 (若有)
- ❌ 不改: 业务功能、UI、调度器、M3a-d、board 渲染
- ❌ 不扩展: 不做新功能、不做 RAG、不做执行重放
- 统一修改: 测试 + 修复 + CHANGELOG + 版本断言 + FEATURES.md 同 Sprint

## 验收标准（Hermes 独立验证）

1. P0-10: 5 类注册表各 ≥1 测试, 全部通过 (注册表 vs 实现一致)
2. P0-11: 对称路径各 ≥1 测试 (conversation/discovery + CLI/API 双入口)
3. **发现的不一致已修复** (如实报告: 发现哪些不一致 → 修了什么)
4. 全量回归 0 新增失败 · 版本 v1.1.81 (pyproject + 断言 + CHANGELOG + FEATURES)
5. 待办清单 P0-10/P0-11 标 ✅

## Codex 指令摘要

> 实现 P0-10 注册表一致性 + P0-11 对称路径一致性测试: ①CLI命令/意图/action/事件/
> API 五类注册表从实现动态读取, 断言与注册表一致 (防新增漏同步); ②conversation/
> discovery、CLI/API 对称路径同场景双入口断言对齐。修复测试发现的不一致。
> 全量回归 0 失败, v1.1.81。不乱改、不扩展。

## 诚实纪律

- 如实报告发现的不一致 (不隐瞒漂移点) — 这正是本 Sprint 的价值
- 测试必须真实断言 (不允许空断言/跳过)
- 若注册表设计本身有缺 (某类无注册表) → 报告并建议 (不硬造)

# S10-112 — P0-10 注册表一致性 + P0-11 对称路径一致性：实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-25 | 前置: v1.1.80 (CHANGELOG) · M3 主线 7/7
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 架构设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-112 提示词（P0-10/P0-11 防遗漏机制）

---

## 0. 现状审计（CTO 独立复核）

| 注册表 | 位置 |
|---|---|
| CLI 命令 | cli_factory.py `build_parser()` (L3182); test_console_cli.py subcommands 集合 |
| 意图 | intent.py `_KEYWORD_RULES` (L124); router.py `DEFAULT_ROUTES` (L17, dict intent→action, 含点号 action 名) |
| Action | actions.py `build_default_actions()` (L3580, 条目含 "sensitive": True/False) + ConfirmationGate.sensitive_actions |
| 事件 | audit/audit_event.py `EVENT_TYPES` (33 个) + audit_emitter 使用 |
| API | web/backend/fastapi_adapter.py (路由表 + 实际注册) |

**已发现的漂移（预置线索, 测试应抓出）**: pyproject=1.1.79 vs CHANGELOG v1.1.80 (commit 1a8ecee 声称 1.1.80 但 pyproject 未同步) — P0-10 类漂移实证。
待办清单 P0-10/P0-11 行存在 (L89-90)。基线: 全量 ~12500 passed (console+api)。

## 1. P0-10 注册表一致性（tests/console/test_s10_112_registry_consistency.py）

数据**从实现动态读取** (build_parser / DEFAULT_ROUTES / build_default_actions / EVENT_TYPES / app.routes), 禁止硬编码快照:

1. **CLI 命令**: build_parser() 枚举子命令 choices ↔ test_console_cli.subcommands 集合 两两相等
   (新增命令漏测试 → 红)
2. **意图**: _KEYWORD_RULES 产生的全部 intent_type ⊆ DEFAULT_ROUTES keys; DEFAULT_ROUTES 的 intent 均有
   意图规则可达 (反向: 新意图无路由 → 红)
3. **Action**: DEFAULT_ROUTES 引用的 action 名全部在 build_default_actions() registry;
   registry 中 "sensitive": True 集合 == ConfirmationGate.sensitive_actions (漂移 → 红)
4. **事件**: EVENT_TYPES 全部被 audit_emitter 引用或文档化; 文档/枚举一致性 (audit 相关 docs 列出的事件 ⊆ EVENT_TYPES)
5. **API**: fastapi_adapter 注册的实际路由 (app.routes) ↔ CAPABILITY_MATRIX API 列宣称的端点;
   POST/PATCH/DELETE 写路由全部在 web 写路由白名单 (新增写端点漏白名单 → 红)

每类 ≥1 测试 (真断言, 禁空断言/跳过; 某类无注册表 → 报告建议, 不硬造)。

## 2. P0-11 对称路径一致性（tests/console/test_s10_112_symmetric_paths.py）

1. **conversation vs discovery**: 同输入序列 ("我想做个记账App"→逐字段→确认) → 两路径状态推进一致
   (DISCOVERY→PRODUCT_CONFIRMATION/READY)、同字段提取结果 (problem/user/core_features 同值)
2. **CLI vs API 双入口**: 
   - agent list ↔ GET /api/agents — 同数据源, 输出结构一致
   - skill list ↔ /api/skills
   - project list ↔ /api/projects
   - board 文档 ↔ docs 配置命令 — 文档宣称的命令存在
   每个对称路径一个测试。

## 3. 修复测试发现的不一致（如实报告）

- 测试跑红 → 定位漂移 → 最小修复 (注册表/文档/实现同步)
- **版本漂移修复**: pyproject 1.1.79 → 1.1.81 (CHANGELOG 已 1.1.80; 如实记录 1.1.80 声称未同步)
- 报告格式: 发现哪些漂移 → 修了什么 → 哪些保留 (设计如此, 非漂移)

## 4. 版本与发布

- pyproject → `1.1.81`; CHANGELOG v1.1.81 (Fixed/Added: P0-10/P0-11 + 修复的漂移); 版本断言同步;
  docs/FEATURES.md (头版本 + P0-10/P0-11 行 🚧→✅); docs/sprint10/待办清单-已发现未落地.md L89-90 标 ✅

## 5. Codex 实施范围

**Allowed/Files**:
- NEW `tests/console/test_s10_112_registry_consistency.py`
- NEW `tests/console/test_s10_112_symmetric_paths.py`
- 修复测试发现的漂移 (涉及文件如实报告, 最小改动)
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / docs/FEATURES.md / docs/sprint10/待办清单-已发现未落地.md

**Forbidden（硬边界）**:
- 不改业务功能 / UI / 调度器 / M3a-d / board 渲染
- 不做新功能 / RAG / 执行重放
- 禁 git add -A (工作区他方未提交文件绝不扫入); 禁新增第三方依赖
- 禁空断言/跳过测试; 禁 stub/fake 注册表数据 (必须动态读取实现)

**Validation**:
- `pytest tests/console/test_s10_112_registry_consistency.py tests/console/test_s10_112_symmetric_paths.py -q` 全绿
- env -u 全量 console+api 0 新增失败 (基线 ~12500)
- 实测: 5 类注册表测试真断言通过; 对称路径双入口一致
- commit: `test(S10-112): P0-10 注册表一致性 + P0-11 对称路径一致性 — 防遗漏机制, v1.1.81`

## 6. 验收标准（Hermes 独立验证）

- [ ] P0-10: 5 类注册表各 ≥1 测试全部通过
- [ ] P0-11: conversation/discovery + CLI/API 双入口各 ≥1 测试
- [ ] 发现的不一致已修复 (如实报告: 发现什么 → 修了什么)
- [ ] 全量回归 0 新增失败 · v1.1.81
- [ ] 待办清单 P0-10/P0-11 标 ✅

# S10-009 Quality Report

> **角色**: Software Quality Engineer (独立质量审计 — 不修代码)
> **基线**: 22b9b01 (S10-009 完成: 6 Task, pytest 6817)
> **日期**: 2026-08-11
> **判定**: ✅ **PASS** (10/10 项专项审计通过; 四门全过; 1 项 P2 边界缺陷记录为 Risk, 不阻塞交付)

---

## Test Scope (审计范围/命令)

| 门 | 命令 | 结果 | 证据 |
|:--:|------|:----:|------|
| 门1 全量 | `.venv/bin/pytest -q` | ✅ **6817 passed, 0 failed** (170s) | `/tmp/s10_009_pytest_full.log` 尾部: `6817 passed, 4 warnings in 170.03s`; `PYTEST_EXIT=0` |
| 门2 前端 | `cd factory-console/web/frontend && npx vitest run` | ✅ **26 files / 305 tests passed** | `Test Files 26 passed (26) / Tests 305 passed (305)` |
| 门2 类型 | `npx tsc --noEmit` | ✅ **0 error** | `TSC_EXIT=0`, 无输出 (node_modules 噪音已过滤) |
| 门3 功能 | ad-hoc 独立审计脚本 (真实装配, /tmp) | ✅ **58/58 checks passed** | `/tmp/s10_009_qa_audit_entity.py` (见 Passed 节逐项) |
| 门4 范围 | `git diff 8958110~1..HEAD --stat` (S10-009 全链) | ✅ **core/runtime/desktop = 0** | 19 文件变更全部位于 `docs/` `factory-console/` `factory-org/org/` `tests/`; `-- factory-core/ factory-runtime/ desktop/` 输出为空 |

**专项测试文件 (既有 canonical, fresh 运行)**:

| 文件 | 命令 | 结果 |
|------|------|:----:|
| tests/org/test_project_entity.py + test_project_lifecycle_flow.py + test_project_space.py | `.venv/bin/pytest tests/org/... -q` | ✅ 70 passed |
| tests/console/test_console_project_draft.py + test_console_project_confirm.py + test_console_lifecycle_acceptance.py | `.venv/bin/pytest tests/console/... -q` | ✅ 73 passed |

**审计方法**: 读码 (org/projects.py, org/space.py, factory-console/service.py) + 真实运行 — ad-hoc 脚本 `/tmp/s10_009_qa_audit_entity.py` (唯一 basename) 用 `build_console_service` 真实装配 (org ProjectStore + ProjectSpaceStore + EventLogger 落盘临时 factory root), 独立于既有测试断言 10 项审计; 不修改项目任何文件。

---

## Passed (10 项逐项 ✅ + 证据)

### 1. Domain Model 正确性 ✅
`factory-org/org/projects.py` ProjectState 枚举 + Project 模型:
- 13 成员 = 9 新态 (draft/discovery/product_defined/design/architecture/confirmed/development/release/maintain) + 4 旧态 (idea/active/maintained/archived), 值全部正确
- Project 新字段带默认值: `slug=""` `draft=False` `discovery=None` `bindings=None` `metadata={}` (旧数据零破坏)
- `ProjectState.parse` 大小写不敏感宽容解析; 非法值抛 ValueError
- PROJECT_TRANSITIONS 单向无环; `archived` 终态 (无出边)
- **实测**: 脚本 A1.1–A1.8 全 PASS (成员列表、默认值、parse、无环、终态)

### 2. 生命周期状态转换完整性 ✅
- 全链 draft→discovery→product_defined→design→architecture→confirmed→development→release→maintain→archived 逐跳实测通过
- console 真实旅程: create_draft (DISCOVERY+draft=True) → save_discovery_answer×2 → complete_discovery (PRODUCT_DEFINED) → org 层逐跳至 ARCHIVED
- 旧链兼容: idea→active→maintained→archived 逐跳通过
- **实测**: 脚本 A2.1–A2.7 全 PASS; 既有测试 `test_project_lifecycle_flow.py` (全链 step-by-step + 到 archived + 事件 payload + updated_at 递增) 全绿

### 3. 非法状态转换拒绝 ✅
- 跳级拒绝: draft→design, draft→product_defined → ValueError
- 回退拒绝: discovery→draft → ValueError
- 跨链拒绝: discovery→idea → ValueError
- 终态后流转拒绝: archived→maintain, archived→development → ValueError
- confirm 状态约束: idea 态 confirm → `ProjectConfirmConflictError` (409); confirmed 后不同 name 重复确认 → 同 409
- slug 冲突预检: 目标目录已存在 → `ProjectConfirmConflictError` (409, 事务前零变更)
- **实测**: 脚本 A3.1–A3.8 全 PASS (输出含 `ProjectConfirmConflictError: slug already exists: ai-note`)

### 4. 旧数据兼容 ✅
- 手工构造 S10-009 前旧形状 `projects.json` (无 slug/draft/discovery/bindings/metadata 字段, lifecycle=idea/active) → ProjectStore 加载 2 条正常, 旧 lifecycle 值宽容解析, 新字段默认值填充
- 懒迁移: 旧项目 (仅 org 记录, 零 workspace 目录) → `service.list_projects()` 首次访问 `migrate_legacy` 回填 `workspace/projects/scorepocket/project.json` 镜像 (幂等, 二次调用 0)
- **实测**: 脚本 A4.1–A4.4 全 PASS; 既有测试 `test_legacy_*` (list/get 读取 + PATCH/DELETE/start 不破坏) 全绿

### 5. Directory Source Of Truth ✅
- `workspace/projects/{slug}/project.json` 读写: `save_project` → `load_project` 全字段一致
- 信源优先: 手改 project.json 的 name → `load_project` 反映新值 (读取路径不依赖 index 缓存)
- 12 骨架子目录 (idea/discovery/product/design/architecture/workflow-instance/source/artifacts/knowledge/runtime/logs/management) 全部创建
- **实测**: 脚本 A5.1–A5.3 全 PASS

### 6. Index Recovery ✅
- 场景 4: 删除 `workspace/projects.json` → `list_index` 返回 `{}` (缓存语义) → `load_project` 不受影响 (目录信源优先) → `rebuild_index` 目录扫描恢复 id→slug → `get_slug` 未命中自愈重建
- **实测**: 脚本 A6.1–A6.5 全 PASS (rebuild 恢复 `{'P-SRC': 'sourceproj', ...}`); 既有测试 `test_index_*` 3 条全绿

### 7. Rename Transaction ✅
- confirm 事务: 写 project.json (旧目录内) → `os.replace` 原子整目录 rename → index 重建 → org 镜像保存
- 实测: confirm("Notewise") → 旧目录 `unnamed-project-*` 消失, `notewise/` 出现; 新 project.json name/slug/lifecycle=confirmed/draft=False 正确; 索引 id→notewise; org 镜像同步 (id 稳定); **idea/conversation.json + discovery/conversation.json + idea/idea.md 3 文件随目录移动逐字节一致 (零丢失)**
- 幂等: 同 name/slug 重复 confirm → 零变更返回
- **实测**: 脚本 A7.1–A7.8 全 PASS; 既有测试 `test_console_project_confirm.py` (29 用例场景 2) 全绿

### 8. Rollback ✅
- 注入 A (rename_space 首调抛 OSError — 写信源成功后失败): → `ConfirmTransactionError` (503 语义); 回滚后旧目录仍在、新目录不存在、project.json/索引/org 镜像**逐字节还原**
- 注入 B (rebuild_index 首调抛 — rename 成功后失败): → `ConfirmTransactionError`; 回滚执行**目录 rename 还原** (新目录消失、旧目录回) + 三处逐字节还原
- 空间资产未丢失 (idea/conversation.json 仍在旧目录)
- **实测**: 脚本 A8.1–A8.9 全 PASS (快照→提交→回滚闭环, 注入 2 种失败点)

### 9. Persistence Integrity ✅
- 3 轮 discovery 问答 + complete_discovery (product-definition.md) + confirm rename 后: `discovery/conversation.json` (qa_count=3)、`idea/conversation.json`、`product-definition.md` 与新目录内**逐字节一致**
- 新目录 project.json 携带 discovery 镜像 (`product_definition: discovery/product-definition.md`); org Project.discovery 字段镜像同步 (status=completed)
- **实测**: 脚本 A9.1–A9.5 全 PASS; 既有测试 `test_confirm_preserves_idea_and_discovery_conversation` 全绿

### 10. Regression ✅
- 门1 全量 pytest: **6817 passed, 0 failed** (与基线 6817 完全一致, 零新增失败)
- 门2 vitest: 305 passed; tsc: 0 error
- 门4 范围: S10-009 全链 19 文件变更, `factory-core/` `factory-runtime/` `desktop/` **零改动** (符合冻结铁律; org/console/tests/docs 允许范围)

---

## Failed (逐项 ❌ + 证据 + 影响)

**无 ❌ 项。** 10/10 项专项审计全部通过; 全量测试零失败。

---

## Risk (未覆盖/边界/未来风险)

| # | 风险 | 证据 (真实运行) | 严重度 | 影响 |
|:-:|------|------|:------:|------|
| R1 | **同秒创建 draft slug 碰撞**: `create_draft_project` 的 slug 基于秒级时间戳 `unnamed-project-%Y%m%d-%H%M%S`。同一秒连续创建两个 draft → 两个项目 id 不同但推导 slug 相同 → `ensure_space` 幂等 (已存在不覆盖) → **第二个项目 get_slug 永久 None → complete_discovery/confirm 全部返回 None (HTTP 404 语义), 无恢复路径** (PATCH rename 只改 org 记录不重建目录) | 复现脚本: draft A `P-51b538c3` slug=unnamed-project-20260811-023834 (complete ✅); 同秒 draft B `P-4faa1a42` **slug=None** (complete ❌ None, confirm ❌ None); index 仅含 A | P2 (中) | 人工使用概率低 (AI 问答间隔 >1s); **自动化/脚本批量创建必现**。org 记录不损坏 (诚实失败不崩溃), 但第二个项目功能不可用。**建议**: slug 加项目 id 片段或随机后缀 (如 `unnamed-project-<ts>-<id8>`) |
| R2 | **confirm 事务部分失败时回滚为尽力而为**: `_confirm_rollback` 任一步异常静默吞掉 (设计: 主异常优先上抛) — 极端磁盘故障下可能残留中间态 (如 rename 已还原但字节还原失败) | 代码审计 service.py:877-905; 注入测试 A8 两种失败点均成功逐字节还原 (未触发回滚自身失败路径) | P3 (低) | 回滚自身失败概率极低; 建议未来在日志记录回滚失败详情 (当前静默) |
| R3 | **目录信源与 org 镜像双写一致性**: 同一 Project 记录存两处 (project.json 信源 + org/projects.json 镜像), 任何一处被外部手改会漂移 (读取以目录信源为准, org 镜像用于 list 聚合) | 代码审计 + A5.2 信源优先实测 | P3 (低) | 单写路径 (service 层) 保证一致; 仅外部直接改文件会漂移 |
| R4 | **未覆盖**: 审计未覆盖 HTTP 层并发 (两请求同秒 POST /projects — 与 R1 同源); 未做 rename 目标目录在事务提交瞬间被外部抢占的竞态测试 (os.replace 目录目标已存在 → OSError → 已由 A8.1 注入路径覆盖回滚) | 推断 | P3 (低) | 建议 R1 修复后补并发测试 |

---

## Recommendation (修复建议 + 结论)

**结论: ✅ PASS — S10-009 可交付。**

- 四门全过: pytest 6817 ✅ / vitest 305 ✅ / tsc 0 ✅ / 范围 core·runtime·desktop = 0 ✅
- 10/10 专项审计 ✅ (Domain/状态转换/非法拒绝/旧数据/目录信源/Index Recovery/Rename 事务/Rollback/持久化完整/回归), 全部真实运行证据 (58 项独立断言 + 既有 canonical 测试 143 用例)
- Rename 事务 + Rollback 是 S10-009 最复杂部分, 实测两种失败注入点均逐字节还原, 质量扎实

**建议 (不阻塞, 优先级排序)**:
1. **P2 — 修复 R1** slug 碰撞: draft 名或 slug 引入项目 id 片段 (如 `unnamed-project-<ts>-<id后8位>`), 并补一条"同秒批量创建"回归测试 (当前无覆盖 — 既有场景 1 只建单个 draft)
2. P3 — 评估 R2: 回滚失败时记录日志 (不静默), 便于极端故障排查
3. P3 — 文档化 R3 双写一致性边界 (外部禁止直接改 workspace/projects/{slug}/project.json)

**证据文件** (均为真实运行输出):
- `/tmp/s10_009_pytest_full.log` — 全量 6817 passed
- `/tmp/s10_009_qa_audit_entity.py` — 独立审计脚本 58/58 (A1–A9)
- 碰撞复现输出 (R1): draft B `get_slug=None → complete/confirm None`

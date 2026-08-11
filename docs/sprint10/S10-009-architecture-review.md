# S10-009 Architecture Review

> 角色: Software Architect (只读审查, 零代码修改) | 日期: 2026-08-11
> 基线: 22b9b01 (S10-009 完成, 全量 pytest 6817 绿)
> 设计基准: docs/design/project-lifecycle.md + project-management-system.md +
> execution-engine.md + AF-PRD-v1.md
> 审查对象: Project Entity 未来扩展性 (Backlog/Epic/Feature/Story/Task/Sprint/
> Workflow Instance/Runtime/Logs/Metadata) + 目录结构合规 + 扩展阻塞点 +
> 迁移兼容 + API 可扩展 + 并发安全

---

## Scope

只读架构审查 (不修代码)。审查范围:

| 维度 | 审查内容 |
|------|----------|
| Project Entity | 字段扩展 (slug/draft/discovery/bindings/metadata) 是否支撑 S10-010/011/012 |
| 目录结构 | `workspace/projects/{slug}/` 三类 + management/ 与 project-lifecycle.md §四 合规性 |
| 扩展阻塞点 | 未来加 Backlog/Sprint/Task/Workflow Instance 是否需改现有结构 (破坏性?) |
| 迁移兼容 | lazy migration (目录信源 + org 镜像) 是否阻塞未来结构变更 |
| API 可扩展 | /api/projects 系列端点是否够用; 未来 management 端点挂载点 |
| 数据流/并发 | 目录信源 + index 缓存; 原子写/锁是否满足未来并发 (S10-011 多 Agent) |

证据代码范围:
- `factory-org/org/projects.py` (854 行 — Project/Sprint/Stage/Artifact/ProjectTaskLink 模型 + ProjectStore + ProjectLifecycle)
- `factory-org/org/space.py` (259 行 — ProjectSpaceStore 目录信源 + index 缓存 + lazy migration)
- `factory-org/org/store.py` (327 行 — _SectionStore 原子写)
- `factory-org/org/workflow.py` (WorkflowLifecycle 组织编排壳)
- `factory-console/service.py` (2568 行 — draft/discovery/confirm 事务/懒迁移)
- `factory-console/api/projects.py` (615 行 — 路由函数)
- `factory-console/web/backend/fastapi_adapter.py` (1046 行 — FastAPI 薄层装配/路由)
- `tests/org/test_project_entity.py` + `tests/console/test_console_lifecycle_acceptance.py`

---

## Findings (逐项)

### 1. Project Entity 未来支持

| # | 项 | 结论 | 证据 |
|---|-----|:----:|------|
| 1.1 | **Backlog/Epic/Feature/Story/Task** | ✅ 预留 | `management/` 目录已建 (`space.py:44`); 设计指定独立文件 `management/backlog/{epic,feature,story,task}.json` (project-management-system.md §十) — **独立文件, 不动 Project 模型**, 零冲突 |
| 1.2 | **Sprint (Task Reference 模型)** | ✅ 已具备 | `Sprint` 模型已存在 (`projects.py:319-326`): `tasks: list[str]` = **Task id 引用列表** — 与 design "Sprint 引用 Task 不包含, Task 属于 Backlog" (project-management-system.md §二) 完全一致; `SprintSection` 持久化 (projects.py:449) |
| 1.3 | **Sprint 字段完整性** | ⚠️ 待扩展 | 现 Sprint 仅 `id/project_id/name/tasks`; PRD §4.5 要求 `{goal, planning, task_references, daily_progress, review}` — S10-010 需加 4 字段 (带默认值, 零破坏) |
| 1.4 | **Epic/Feature/Story/Task 模型** | ⚠️ 未建 (预期) | S10-010 新建 org 模型 (参照 Sprint/ProjectTaskLink 模式); `ProjectTaskLink` (projects.py:429-436) 已提供项目↔Core Task 引用通道, Core Task 冻结不破坏 |
| 1.5 | **Workflow Instance binding** | ✅ 字段预留 | `Project.bindings: dict | None` (projects.py:298), 设计结构 `{workflow_ref, version, parameters}` (project-lifecycle.md §三/§七); ⚠️ 无写入逻辑 — confirm 事务不写 bindings (completion Next #3 已列) |
| 1.6 | **Runtime/Logs 写路径** | ✅ 目录预留 | `runtime/` + `logs/` 已建 (space.py:42-43); 无写路径 (S10-011 才有) — 增量 mkdir 即用, 零破坏 |
| 1.7 | **Metadata 自由扩展** | ✅ 已具备 | `Project.metadata: dict[str, Any]` (projects.py:299), 测试覆盖 (`test_project_entity.py`: `test_new_fields_settable`/`test_metadata_none_normalized`) — 任意键值, JSON 友好 |

### 2. 目录结构合规 (project-lifecycle.md §四)

| # | 项 | 结论 | 证据 |
|---|-----|:----:|------|
| 2.1 | 三类 + management/ 根目录 | ✅ 合规 | `SPACE_DIRS` 12 目录 (space.py:32-45): 产品资产 8 类 (idea/discovery/product/design/architecture/source/artifacts/knowledge) + runtime/ + logs/ + management/ + workflow-instance/ |
| 2.2 | runtime/ 内部骨架 | ⚠️ 缺失 | 设计 §四/PRD §4.9: runtime/ 下 `agent-execution/skill-execution/mcp-calls/workflow-instances/state/context` — 实现只有空 `runtime/` 根目录 (S10-011 建, 增量无破坏) |
| 2.3 | logs/ 命名偏差 | ⚠️ 文档不一致 | 设计 §四 写 `log/`, 实现 `logs/` (space.py:43 注释自认 "log = Audit Data"; 命名与设计文档不一致 — 低危, 建议修订设计文档或定别名) |
| 2.4 | workflow-instance/ 位置偏差 | ⚠️ 设计偏差 | 实现放**顶层** (space.py:38), 设计 §四 放 `runtime/workflow-instances/` 子目录 — 顶层与产品资产同级; 影响: S10-011 写实例状态时需定落位, 建议按设计收敛或显式决策 |
| 2.5 | management/ 内部骨架 | ⚠️ 未建 (预期) | design §十: roadmap.md/milestone.json/sprint//backlog//risk.json/metrics.json/decisions.json — 目录已建, 内部文件 S10-010 落; 增量创建零破坏 |
| 2.6 | 索引/隔离 | ✅ 合规 | `workspace/projects.json` index 纯缓存可重建 (space.py:9-10, 219-237); 每项目独立目录, 禁止跨项目污染 (space.py:13-14) |

### 3. 扩展阻塞点 (具体到字段/文件/API)

| # | 阻塞点 | 位置 | 影响 | 是否破坏性 |
|---|--------|------|------|:----:|
| 3.1 | `Project` 继承 `_OrgModel` **extra="forbid"** | models.py:54 + 测试 `test_extra_field_forbidden` | project.json 顶层新增字段必须**先扩 Project 模型** (带默认值) 否则 `CorruptOrgStoreError`/ValidationError | ⚠️ 非阻塞 — 有纪律即可: 项目级字段→模型扩展+兼容测试; **management 域状态→独立文件 (不进 project.json 顶层)**; metadata dict 可绕过 |
| 3.2 | org 记录 ↔ 目录信源 **双写一致性** | service.py PATCH rename (961-1004) 只写 org store, 不写 `{slug}/project.json` 镜像 | **目录信源陈旧** (name 不同步); confirm/懒迁移会重写, 但期间 list (org 源) 与目录 (信源) 不一致 | ⚠️ 已知 (completion Known #1) — S10-010 需目录级 rename 一致性 |
| 3.3 | DELETE 不清理 workspace 目录 + **rebuild_index 幽灵复活** | service.py delete (1006-1044) 只清 org+workflow_runs+chat; space.py rebuild_index (219-237) 扫描所有含 project.json 的目录 | 已删项目孤儿目录 `{slug}/` 保留 → rebuild_index/get_slug 自愈时**重新索引已删 id** → 幽灵项目复活风险 (未来目录信源为主时必然暴露) | ⚠️ 已知 (completion Known #2) — S10-010 数据治理必做 |
| 3.4 | `GET /api/projects/{id}` 详情端点未注册 | fastapi_adapter 路由表 (394-590) | 设计 §五 定义的详情端点 (含 discovery/bindings 投影) 缺失; 现以 /lifecycle+/run-status+/timeline 组合读取 | ⚠️ 已知 (completion Known #4) — 前端详情页驱动时补, 零结构变更 |
| 3.5 | `GET /api/projects/{id}/bindings` 端点未注册 | 同上 | 设计 §五 已定义; bindings 落库 (Next #3) 后需配套读取端点 | ⚠️ S10-010 补 |
| 3.6 | 状态机扩展 | PROJECT_TRANSITIONS dict (projects.py:208-222) | 加状态 = dict 加成员 + ProjectState 枚举加值 — 单点扩展, 旧值宽容解析 | ✅ 无阻塞 |
| 3.7 | 未来 management 端点挂载 | fastapi_adapter 薄层 | `/api/projects/{id}/backlog|sprints|tasks` 直接新增 api/ 模块 + adapter 注册 (api/projects.py 同模式) — 零冲突 | ✅ 无阻塞 |

### 4. 迁移兼容 (lazy migration)

| # | 项 | 结论 | 证据 |
|---|-----|:----:|------|
| 4.1 | lazy migration 触发 | ✅ 已修复 | list_projects 入口 (service.py:301) + project_exists 入口 (completion: S10-009-006 修复 gap) → `space.migrate_legacy` 回填 |
| 4.2 | 幂等性 | ✅ | 已存在目录跳过 (space.py:247-259); 重复读取零额外写 |
| 4.3 | 旧值/旧字段兼容 | ✅ | ProjectState.parse 宽容 (projects.py:92-103); slug/draft/discovery/bindings/metadata 全部带默认值 (projects.py:295-299); 测试 test_new_field_defaults |
| 4.4 | **是否阻塞未来结构变更** | ✅ 不阻塞 | 新目录 mkdir exist_ok 幂等 (space.py:124-130); 新增骨架/文件不触发迁移重写; 但 **双写源 (org 镜像 + 目录信源) 的长期一致性维护成本** (见 3.2/3.3) 是 S10-010 需明确"单一写者"规则的根因 |

### 5. API 可扩展性

| # | 项 | 结论 | 证据 |
|---|-----|:----:|------|
| 5.1 | 现有端点覆盖 | ✅ | GET/POST /api/projects, /suggest, /{id}/discovery/answer|complete, /{id}/confirm, PATCH/DELETE /{id}, /{id}/lifecycle, /{id}/run-status, /{id}/timeline, /{id}/workflow, /{id}/runtimes, /{id}/start, /{id}/chat (fastapi_adapter 26-77 注释 + 394-590) |
| 5.2 | 未来端点挂载 | ✅ 无结构阻塞 | 薄层 adapter 模式: 新 api/ 模块 (如 api/management.py) + adapter 注册即可; 与既有端点无路径冲突 (backlog/sprints/tasks 为 {id} 子路径) |
| 5.3 | 缺失端点 | ⚠️ 2 个 | GET /api/projects/{id} 详情 + GET /{id}/bindings (设计 §五 已定义, 待 S10-010/前端详情页驱动) |
| 5.4 | 错误语义契约 | ✅ 规范 | 400/404/409/503 语义分层清晰 (service.py:745-753 注释; api/projects.py 各函数 docstring) — 未来端点可复用同一契约风格 |

### 6. 数据流 / 并发安全

| # | 项 | 结论 | 证据 |
|---|-----|:----:|------|
| 6.1 | 单文件原子写 | ✅ | tmp + os.replace (store.py:103-113, space.py:132-141, 196-203) — 单文件永不半写 |
| 6.2 | 目录 rename 原子 | ✅ | os.replace 整目录 (space.py:103-114) — confirm 事务核心原语 |
| 6.3 | confirm 事务回滚 | ✅ | 快照 (service.py:865-875) + 逐字节回滚 (878-905); slug 唯一/状态约束预检失败零变更 (795-805) |
| 6.4 | **无锁 read-modify-write (丢失更新风险)** | ⚠️ 缺口 | `_SectionStore.save()` (store.py:117-121: read_all → modify → write) 无锁; `save_discovery_answer` (service.py:561-582: read_json → append → write_json) 无锁 → **两个并发 answer 追加丢条目** (last-write-wins) |
| 6.5 | **confirm 事务无互斥** | ⚠️ 缺口 | 两并发 confirm 同项目: 均过预检 → 后写覆盖; rename 与并发写入方竞态 (旧 slug 写入 → FileNotFoundError → 失败安全但请求丢失) |
| 6.6 | index 缓存并发 | ⚠️ 低危 | 并发 rebuild_index 幂等但重复写 (内容一致, 最后写者胜 — 无损坏); get_slug 未命中自愈无锁 |
| 6.7 | 现状边界 | ✅ 当前安全 | 单进程单用户 console; workflow_runner._RUNNING_LOCK (workflow_runner.py:59) 仅内存级单进程互斥 — 够当前用 |
| 6.8 | **S10-011 前置条件** | ❌ 未满足 | 多 Agent 并行写 runtime/management (execution-engine.md §三 并行执行, PRD §4.7 Max Parallel 5) → 必须引入 **per-project 文件锁或单写者队列** (fcntl/filelock), 否则丢失更新/竞态必现 |

---

## Future Readiness (S10-010 / 011 / 012)

| 未来 Sprint | 项 | 结论 | 需扩展内容 (位置) |
|------------|-----|:----:|------------------|
| **S10-010** Project Management | Backlog/Epic/Feature/Story/Task | ⚠️ 需扩展, **零破坏** | 新建 org management 模型 + `management/backlog/*.json` + `management/` 内部骨架 (roadmap/milestone/sprint/risk/metrics/decisions) |
| | Sprint 完整字段 | ⚠️ 需扩展 | Sprint 模型 + `goal/planning/daily_progress/review` (projects.py:319, 带默认值) |
| | bindings 落库 | ⚠️ 需扩展 | confirm 后写 `bindings` (project.json 或 management/bindings.json) + GET /{id}/bindings 端点 |
| | 详情端点 | ⚠️ 需扩展 | GET /api/projects/{id} (含 discovery/bindings 投影) |
| | PATCH rename 目录一致性 | ⚠️ 需修复 | update_project 双写 org + `{slug}/project.json` 镜像 (service.py:961-1004) |
| | DELETE 孤儿目录治理 | ⚠️ 需修复 | delete_project 清理 `workspace/projects/{slug}/` + 孤儿扫描 (幽灵复活, 3.3) |
| **S10-011** Execution Engine | runtime/ 子目录 + 写路径 | ⚠️ 需扩展 | `runtime/{agent-execution,skill-execution,mcp-calls,workflow-instances,state,context}` (增量 mkdir); workflow-instance/ 落位决策 (2.4) |
| | **并发写安全** | ❌ **阻塞** | per-project 文件锁/单写者队列 — 先于多 Agent 并行落地 (6.4/6.5/6.8) |
| | Task 绑定 | ✅ 零改动 | ProjectTaskLink + Sprint.tasks 引用模型已就位 (execution-engine.md §八: project_id+sprint_id+task_id 绑定) |
| **S10-012** UI | 详情/管理页面数据源 | ⚠️ 需扩展 (后端已预留) | 消费 S10-010 新增端点; 后端零结构变更 |
| | 目录信源前端列表 | ✅ 零改动 | list = workspace ∪ org 并集同 id 合并已实现 (service.py:292-364) |

**结论**: S10-010 需 6 项扩展 (均非破坏性); S10-011 有 1 项**前置阻塞** (并发写锁); S10-012 零后端结构变更。

---

## Blockers (未来扩展阻塞清单)

| # | 位置 | 影响 | 建议 |
|---|------|------|------|
| B1 | `store.py:117-121` + `service.py:561-582` — 无锁 read-modify-write (org _SectionStore.save / discovery answer 追加) | S10-011 多 Agent 并发写 → 丢失更新 (并发 answer 丢条目; 并发任务状态流转丢更新) | S10-011 前引入 per-project 文件锁 (fcntl.flock / filelock) 或单写者队列; 锁粒度 = project 级, 覆盖 org store + space 写路径 |
| B2 | `service.py:732-863` — confirm 事务无互斥 | 并发 confirm 同项目 → 后写覆盖; 事务与并发读写竞态 | 与 B1 同锁; 事务内持锁 (预检→提交→释放) |
| B3 | `service.py:1006-1044` + `space.py:219-237` — DELETE 不清理目录 + rebuild_index 扫回孤儿 | 已删项目幽灵复活 (目录信源为主后必现) | S10-010 数据治理: DELETE 级联清理 `workspace/projects/{slug}/` + 孤儿目录扫描任务 |
| B4 | `service.py:961-1004` — PATCH rename 不更新目录镜像 | 目录信源 (project.json) name/slug 陈旧, 与 org 镜像不一致 | S10-010: update_project 双写或明确"目录为唯一信源"后统一写路径 |
| B5 | `space.py:38` — workflow-instance/ 顶层 vs 设计 runtime/ 子目录 | S10-011 写实例状态时落位不明; 与 PRD §4.9 目录契约不一致 | 修订设计文档或显式 ADR 决策落位 (二选一), 避免 S10-011 返工 |

---

## Conclusion

**PASS (有条件)** — S10-009 的 Project Entity 为 S10-010/011/012 预留了正确的扩展点:
- ✅ 目录骨架 (12 目录) + `metadata` 自由扩展 + `bindings`/`discovery` 字段预留 + Task Reference 模型 (Sprint.tasks 引用) — 均与设计基准对齐
- ✅ lazy migration 幂等不阻塞未来结构变更; 旧值/旧字段零破坏
- ✅ API 薄层模式支持 management 端点无冲突挂载; confirm 事务 (快照/回滚/预检) 实现规范
- ⚠️ 3 项已知问题 (PATCH rename 目录一致性 / DELETE 孤儿目录 / 详情端点缺失) 已在 completion Known Issues 诚实记录
- ❌ 1 项未来前置阻塞: **并发写无锁** (B1/B2) — 当前单进程安全, S10-011 多 Agent 并行前必须解决; 另 B5 目录落位偏差需在设计层收敛

**建议 (按优先级)**:
1. S10-010 计划内消化 B3/B4 (数据一致性) + Sprint 字段扩展 + bindings 落库 + 详情/bindings 端点
2. S10-011 启动前完成 B1/B2 (per-project 文件锁) — 这是唯一硬性前置
3. 近期修订 project-lifecycle.md: `log/`→`logs/` 命名、`workflow-instance/` 落位 (B5), 消除文档与实现偏差

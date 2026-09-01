# AI Factory Data Foundation Contract

> 版本: v2 | 日期: 2026-09-01
> 原则: **真实代码是什么, 就报告什么。** 无法从代码证明的 → UNKNOWN/GAP。
> 本轮不做 SQLite/DB 迁移。冻结 JSON 事实体系边界, 为未来演进留替换点。

---

## 1. Data Foundation Principles

1. **ONE FACT, ONE SSOT** — 任何业务事实只有一个权威来源; 允许 SSOT/Projection/Cache/Index/History/Audit/Log/Runtime State 并存, 但后者不得冒充事实源。
2. **project_id (P-xxx) 是全局统一关联键** — 跨 Domain 关联唯一标识; 禁止模块自造另一套 Project Identity。
3. **JSON 是当前 Persistence 实现, 不是业务契约** — 业务代码不得把 `~/.factory/org/projects.json` 等路径/结构当 API。
4. **LLM output ≠ Execution Fact** (P0-001) — 执行事实必须有 ToolCall+ToolResult 证据。
5. **WebUI 是 View, 不是 SSOT**。
6. **最小必要抽象** — 现有 Store 已承担 Repository 职责则复用, 不套新抽象层。
7. **失败安全** — 所有读取路径缺文件/损坏 → None/空 (永不抛); 写路径失败 → 明确错误/回滚点。

## 2. Domain Model (真实存在的 Domain 对象)

| Domain | 持久化位置 | Store / Owner | 状态 |
| --- | --- | --- | --- |
| Project | `org/projects.json` | `org.projects.ProjectStore` | ✅ |
| Task / Epic / Feature | `workspace/projects/{id}/management/backlog/{task,epic,feature}.json` | `org.management.TaskSection/EpicSection/FeatureSection` | ✅ |
| Session / Message | `console_sessions.json` | `console_sessions.SessionStore` | ✅ |
| Run | `workflow_runs/{project_id}/{run_id}/progress.json` (+`report.json`) | `workflow_runner.Recorder` | ✅ |
| Node / NodeRun | 项目目录 `execution_state.json` | `session.exec_state` / orchestrator | ✅ |
| Artifact | `org/artifacts.json` + 项目目录产物 | `org.artifact.ArtifactStore` | ✅ |
| Requirement | `requirements/` + 项目目录 `requirements.json` | session 流程落盘 | ✅ |
| Plan | `session_plans.json` / pending plan | `agent_loop.PendingPlanStore` | ✅ |
| Approval | `session_approvals/` + workflow 审批 | approval store | ✅ |
| Provider / Model | `providers/` | `providers.store.ProviderStore` | ✅ |
| Agent / Team / Skill | `agents/` `teams/` `skills/` | AgentStore / registry | ✅ |
| Memory | `project_memory/{project_id}.json` + `session_topics/sess-*.json` | `project_memory.MemoryStore` / `topic_ledger.TopicLedger` | ✅ |
| Evidence | EvidenceStore (证据 bundle) | `session.evidence.EvidenceStore` | ✅ |
| Event | factory-core events store (`events/models.py: Event, EventType`) | `factory-core.events` EventLogger | ✅ |
| Audit | audit store (`audit/audit_store.py`) | `api.audit` | ✅ |
| Product Progress | `projects/{id}/product_progress.json` | `session.progress` | ✅ |
| Repair | `projects/{slug}/repair_task.json` | `session.quality.RepairManager` (唯一写者) | ✅ |
| Cost | `session/cost_ledger` | cost ledger | ✅ |

## 3. Identity Model

| Entity | ID 形态 | 生成者 | 唯一范围 | 持久 |
| --- | --- | --- | --- | --- |
| Project | `P-xxx` | org 注册 | 全局 | ✅ |
| Session | `sess-{hex}` | `console_sessions._new_id` | 全局 | ✅ |
| Message | `msg-{hex}` | `console_sessions._new_id` | 会话内/全局 | ✅ |
| Run | `R{timestamp}` | `agent_loop` (1319) | 项目内 | ✅ |
| Task | `T-*` / 自增 | `org.management.TaskSection` | 项目内 | ✅ |
| Evidence | bundle id | `EvidenceStore` | 全局 | ✅ |
| Approval | `APR-*` | 审批生成 | 全局 | ✅ |
| Repair | repair 记录 | `quality.RepairManager` | 项目内 | ✅ |
| 次级实体 (observation/conflict/experiment/rollback…) | `obs-*` `lc-*` `effexp-*` `rb-*` | `uuid.uuid4` | 全局 | ✅ |

**验证**: 无第二套 Project Identity 体系 (orchestrator 用同一 project_id; 目录 slug 是 id 的投影, 见 §16)。

## 4. SSOT Matrix

| Entity | SSOT | Owner / Writer | Readers | Projection |
| --- | --- | --- | --- | --- |
| Project | `org/projects.json` | ConsoleService (create/confirm/rename/archive/lifecycle) | CLI/API/session/orchestrator/frontend | 目录 project.json (镜像, §4.1) |
| Task | `management/backlog/task.json` | `service.create_task` / `agent_loop` / `org.management` | query_engine/project_scan/analysis/monitor/CLI | 任务统计 (动态计算) |
| Session | `console_sessions.json` | `SessionStore` | frontend/agent_loop/topic_ledger | 话题摘要 |
| Message | `console_sessions.json` (messages) | `SessionStore.append_message` | frontend/agent_loop(history) | meta.evidence (结构化视图) |
| Run | `workflow_runs/{id}/progress.json` | `Recorder._write_progress` | run-status API / run_liveness | report.json (终态投影) |
| Artifact | `org/artifacts.json` | ArtifactStore | 产物面板/审计 | 目录产物 |
| Memory | `project_memory/` + `session_topics/` | MemoryStore / TopicLedger | 新会话上下文注入 | — |
| Provider | `providers/` | ProviderStore | agent/CLI/API | — |

### 4.1 Lifecycle 双源判定 (S10-115 已统一)

| 源 | 词汇表 | 语义 | SSOT? |
| --- | --- | --- | --- |
| `org/projects.json` `lifecycle` | idea→discovery→product_defined→…→confirmed→development | **项目注册/业务生命周期** (会话/人驱动) | ✅ 唯一 |
| 目录 `project.json.status` | EXECUTION_READY→DEVELOPMENT→TESTING→VALIDATION_PASS→USER_ACCEPTANCE→DELIVERED | **执行/交付生命周期** (引擎驱动, 防回退守卫) | ✅ 唯一 (不同维度) |

**结论**: 二者表达**不同维度的领域事实** (注册阶段 vs 执行状态机), 不是同一事实的双份拷贝。
`set_project_lifecycle` (lifecycle_store.py) 是执行生命周期**统一写入口** (原子写 project.json + product.json + execution_state.json, 带防回退), org 层 `confirm` 写目录 `project.json(lifecycle=confirmed)` 是**注册生命周期的目录镜像** (S10-009 事务一部分)。
**非双事实源**; 命名易混 → 契约冻结词汇表 (§21)。

## 5. History

| 对象 | 历史存储 | 产生者 | 可变? | 重建? |
| --- | --- | --- | --- | --- |
| Task | `task.history: [{time, actor, action, result}]` (management.py 379, 每次状态转换追加) | `org.management` 状态转换 | 只追加 | 否 (SSOT 一部分) |
| 会话消息 | console_sessions messages (顺序=时间序) | SessionStore | 只追加 (truncate 可删尾部) | 否 |
| Run 进度 | progress.json stages/errors | Recorder | 每阶段覆盖 | 否 (运行事实) |
| Project | org 记录 updated_at (无独立 history 字段) | Service | 覆盖 | — |

**当前状态 vs 历史**: 严格区分 — `Task.status` 是 current state, `Task.history` 是审计链 (不可变追加)。
**GAP**: Project 无独立 history 链 (仅有 lifecycle 转换事件, 见 §6) — P2。

## 6. Events

- **Event 体系**: `factory-core.events` — `events/models.py: Event, EventType` (枚举已扩展 137→151); org 事件经 `org/events.py` (record_company_created / record_project_* 等) 落 EventLogger; 事件带 `seq` (last_seq 查询)。
- 事件是追加式 (event log), 与 History 区分: Event 描述"发生了什么", History 描述"对象状态变化"。

## 7. Audit

- **Audit 体系**: `audit/audit_store.py` (AuditStoreProtocol) + `api/audit.py` (audit_events / audit_trace / audit_decisions / audit_export) + `session_audit.py`。
- 能力: trace_id 追踪、decision 审计、导出。
- **GAP**: 统一 Actor 模型 (human/agent/system/tool/workflow/model) 未逐事件强制 `actor_id/actor_type`; 部分事件有 source (`org/events.py: source="org"/"cli"`) — P2, 治理扩展点 (§30)。

## 8. Execution Evidence (P0-001 延伸)

**血缘**: LLM claim ≠ Execution Fact ≠ Tool Result ≠ Artifact ≠ Evidence。

- `session/evidence.py`: `EvidenceBundle` / `EvidenceBuilder` (build/from_repo_result/from_execution_result) / `EvidenceStore` (save/load/list) / `emit_evidence_created`。
- 会话消息 `meta.tool_calls` + `meta.evidence` (结构化工具证据) — 前端 ToolCallList 展示。
- 消息 content 中的执行声称由 `execution_truth.py` 校验 (P0-001, 已在 2f29ea32)。
- **证据可追溯**: evidence bundle 引用 project_id/agent_id (from_repo_result 带 project_id/agent_id); tool_calls 在消息 meta 与 run 关联。

## 9. Cache

| Cache | 来源 | 更新 | 删除重建 | 证据 |
| --- | --- | --- | --- | --- |
| `workspace/projects.json` (id→slug 索引) | ensure_space 回填 | 注册/rename 时 | ✅ 目录扫描/ensure_space 可重建 | `org/space.py` 明说"纯缓存"; 测试"删除 → 列表不受影响" |
| 前端 localStorage (af.theme/af.locale/af.bg.*) | UI 偏好 | 用户操作 | 删除无影响 (纯 View 偏好) | theme.tsx/locale 测试 |
| 内存 model/provider 缓存 | provider 加载 | 进程内 | 重启即失 (正常) | — |

## 10. Projection

| Projection | 来源 | 消费者 | 可重建 |
| --- | --- | --- | --- |
| workflow `report.json` | progress.json 终态 | 报告 API | ✅ (run 完成后生成) |
| 任务统计 {total,done,pending} | task.json 动态计算 | WebUI/回答 | ✅ (每次读时算) |
| 话题摘要 (topic_ledger) | 会话消息 | context 注入 | ✅ (从消息可重建) |
| project_memory 摘要 | 话题摘要 | 新会话 | ✅ (派生, 不覆盖原消息) |
| 项目完成度 % | 任务统计聚合 | 侧栏/回答 | ✅ |

## 11. Runtime State

| 状态 | 存储 | 持久等价物 | 重启行为 |
| --- | --- | --- | --- |
| run_liveness `_CANCEL/_ALIVE` | 内存 dict | progress.json (status/updated_at) + run_liveness 僵尸检测 | 重启后取消标志丢失 (正常); 僵尸 Run 由 reconcile_stale 标记 STALE |
| SSE / 流连接 | 进程内 | — | 断连重连 |
| Session cancel 标志 (F-01) | 内存 | — | 重启丢失 (消息执行线程随之结束) |

**Runtime State ≠ Persistent State** — 已区分: 运行态可丢, 持久事实在 SSOT。

## 12. Logs

- `run/backend.log` `run/frontend.log` — 诊断信息, **不是业务 SSOT**。
- 禁止业务逻辑 parse log 当数据源 (当前无此行为)。

## 13. Memory

- `session_topics/sess-*.json` (话题账本) + `project_memory/{project_id}.json` (跨会话摘要)。
- 血缘: console_sessions → topic_ledger (摘要) → project_memory → 未来会话 context。
- **Memory 是 Derived Knowledge, 不是 Original Fact** — 摘要不修改原始消息; 原始事实在 console_sessions SSOT。

## 14. Snapshot

- `org/context_snapshots.json` — 上下文快照 (项目级, 分析产物投影)。
- Snapshot = 某时间点系统状态; 区别于 History (状态变化记录) 与 Backup (恢复副本)。

## 15. Backup / Recovery

| 备份 | 创建者 | 何时 | 恢复 |
| --- | --- | --- | --- |
| `org/projects.json.bak-s35` | 人工 (存量校正前) | 手动 | 直接恢复 |
| `cleanup-backup-*` | 清理任务 | 清理前 | 直接恢复 |
| confirm 事务快照 | `service.confirm_project` | 事务内 | 逐字节回滚 (失败时) |

**Backup 非 SSOT**, 是恢复副本。事务型回滚 (confirm/rename) 是手工快照补偿, 非数据库事务。

## 16. Index

- `workspace/projects.json` = id→slug **索引 (Cache 类)**, 非 SSOT; 删除后可重建 (ensure_space / 目录扫描)。
- 无独立 search index (grep 无); 查询走 store 读全量。

## 17. Data Lineage

```
User → WebUI (View, 无事实) → API (fastapi_adapter) → Service (ConsoleService)
     → Domain (org / session / orchestrator) → Store (SessionStore/ProjectStore/TaskSection/Recorder…)
     → SSOT JSON
     → Event (factory-core events) / History (task.history) / Audit (audit_store) / Evidence (EvidenceStore)
     → Projection (report/统计/摘要) → API → WebUI

执行链:
User Intent → Agent (run_agent_native) → Plan → Task → Run (R{ts})
     → NodeRun → Tool (dispatch) → Tool Result (calls 记录)
     → Artifact / State Change → Evidence (EvidenceBundle) → Audit → Projection → User
```

## 18. Write Authority

| Entity | 唯一写者 | 写入口 |
| --- | --- | --- |
| Project | ConsoleService + org ProjectStore | create_project/confirm/rename/archive/delete/lifecycle transition |
| Task | service.create_task / agent_loop / org.management | create_task/execute_plan/TaskSection.save |
| Session/Message | SessionStore | create_session/append_message/send_message |
| Run | Recorder (workflow_runner) | _write_progress |
| Evidence | EvidenceStore | save/emit_evidence_created |
| Repair | quality.RepairManager (唯一) | create_repair/save |
| Event | EventLogger (factory-core) | record_* |

**原则**: UI → API → Service → Store。**已发现直接读 GAP**: `agent_loop.py:908/930` 直接 `json.loads(org/projects.json)`; 多处直接拼路径读 `task.json` (service.py:3401/monitor/query_engine/project_scan/analysis_tools) — 均为**只读**, 无绕过写。分类 P1 (读路径未统一), 本轮不重写。

## 19. Read Authority

- 所有读者经 API→Service→Store 或直接 store 读; 投影读者 (统计/摘要) 知道自己读的是派生数据。
- 前端只经 `/api/*` (无直连 JSON); localStorage 仅 UI 偏好。

## 20. Concurrency (真实评估 — G2 修复后 2026-09-01)

| 维度 | 级别 | 说明 |
| --- | --- | --- |
| 单线程 | ✅ 安全 | 顺序执行 |
| 多线程 (进程内) | ✅ 安全 | SessionStore RLock 覆盖 read-modify-write; org store/management 原子写 |
| 多进程 | ✅ 基本安全 | **G2 修复**: org store / management / console_sessions 写操作均加 `file_lock` (fcntl.flock, per-file) 保护完整 read-modify-write; 原子写 (临时文件+os.replace) 防损坏; `update(record_id, mutator)` 事务接口防 get→save 丢更新; console_sessions 锁内 `_load()` 刷新防读陈旧 |
| 多 Agent | ✅ 基本安全 | 不同 Task/Project 并发写经 flock 串行化 (test_concurrency A/C 验证); 同一 Task 并发修改须用 `update_task` (B 验证); **业务层 get→save 模式未全量迁移至 update — 待逐步替换** |
| 跨文件原子性 | ❌ 无 ACID | confirm/rename 用手工快照回滚补偿; 无跨文件事务 (SQLite 阶段解决) |

**真实测试** (tests/org/test_concurrency.py, 多进程实测):
- A: 两进程 save 不同 Project → 无丢更新 ✅
- B: 两进程 update_task 同 Task 追加 history → 两条都在 ✅
- C: 4 进程不同 Task → 全保留 ✅
- D: 写中途 SIGKILL → JSON 仍有效 (原子写) ✅
- E: 两进程会话 append 消息 → 全保留 ✅

**诚实边界**: flock 是"串行化"不是"ACID"; 锁粒度 per-file (同一文件全部记录共享锁, 高频写有轻微串行); Windows 无 fcntl → 锁降级 (仅原子写)。

## 21. Schema Contract (核心 Schema)

- **Project** (org/projects.json): id/name/user_id/goal/starred/archived/lifecycle/repo_path/language/framework/build_command/test_command/project_type/analysis_ref/baseline_ref/snapshot_ref/slug/draft/company_id/department_ids/discovery/bindings/metadata/git_enabled/git_repo_url/git_provider/git_default_branch/git_current_branch/git_head_commit/git_working_tree/created_at/updated_at
- **Task**: id/title/description/priority(P0-P3)/status(todo|ready|in_progress|blocked|review|done)/assignee/dependency/history([{time,actor,action,result}])/exec_ref(EXR-*)/exec_result/created_at/updated_at
- **Session**: id/scope(company|project)/project_id/title/status/created_at/updated_at/summary/feature_id/task_id/run_ids
- **Message**: id/session_id/role(user|assistant)/content/created_at/meta{client_msg_id, tool_calls[{tool,ok,params,output,duration_ms}], evidence, thinking_steps, usage}
- **Run progress**: status/stages/totals/errors/updated_at (+ report.json 终态)
- **Provider**: 模型配置 (providers.json)

## 22. Relationship Contract

| 关系 | 键 | Owner | Cardinality | 删除行为 |
| --- | --- | --- | --- | --- |
| Project→Task | project_id 目录归属 | 项目目录 | 1:N | org 删除**不级联** (目录清理随 space) |
| Project→Session | session.project_id | SessionStore | 1:N | 不级联 (会话保留) |
| Session→Message | session_id | SessionStore | 1:N | 会话删除级联消息 (delete_session) |
| Task→Run | exec_ref (EXR-*) | agent_loop | 1:N | 不级联 |
| Run→NodeRun | execution_state.json | orchestrator | 1:N | 随 run 目录 |
| Project→Memory | project_memory/{id} | MemoryStore | 1:N | **不级联** (项目删除记忆保留) |
| Project→Audit/Event | project_id 引用 | events/audit | 1:N | **不级联 (审计保留)** |

## 23. Delete Semantics

- **delete_session**: 会话+消息级联 (console_sessions delete_session)。
- **delete_project** (service.delete_project): ①运行中保护(409) → ②org 删除 (org.project.deleted 事件落库) → ③运行数据清理 (workflow_runs/{id} + chat.json) + space 目录清理。
- **不级联**: Task/Epic/Feature (目录内, 随 space 清理)、Session (保留)、Memory (保留)、Audit/Event/Evidence (保留)。
- 无 soft-delete/tombstone (archive 是软归档)。

## 24. Retention

| 类别 | 长期保留? | 可删? |
| --- | --- | --- |
| org/projects.json | ✅ | archive (软) |
| task.json + history | ✅ (审计链) | 随项目 |
| console_sessions | ✅ | delete_session |
| Audit/Event | ✅ | 否 (审计) |
| Evidence | ✅ | 否 (证据) |
| Cache (workspace index / localStorage) | ❌ | ✅ 可删可重建 |
| Logs | ❌ | ✅ 轮转 |

## 25. Data Provenance

- 现有可追溯字段: actor/source (部分事件)、task.history actor、evidence project_id/agent_id、message meta (tool_calls 带执行记录)、run progress。
- **GAP**: 统一 provenance 字段 (run_id/trace_id/event_id 贯穿所有写入) 未全量实施 — P2, 治理扩展点。

## 26. Repository Boundary

```
UI → API → Service/Domain → Store (Repository) → JSON Persistence
```
未来: Store 层换 SQLite/Postgres, Service/Domain/API 不动。现有 Store 天然承担 Repository 职责 (ProjectStore/SessionStore/TaskSection/Recorder/EvidenceStore), 不新增抽象层。

## 27. Current JSON Persistence

根: `~/.factory` (factory_root)。全部 JSON, 无 DB。原子写模式: org store / management = 临时文件+os.replace; console_sessions = 直接 write_text (⚠️ 非原子, §20)。

## 28. Future SQLite Boundary

- 换 SQLite 时替换 Store 内部实现 (path→sqlite), 保持接口: save/get/list/delete/append_message。
- **本轮不动**。需先解决: SessionStore 原子写、跨文件一致性 (可借 SQLite 事务)。

## 29. Future External DB Boundary

- Store 接口不变; SQLite→Postgres 是连接层替换。
- 前提: 先消除业务代码直接 JSON 读 (agent_loop:908 / task.json 读散布, §18)。

## 30. Data Governance Extension Points

- Event (EventType 枚举可扩展)、Audit (AuditStoreProtocol)、Evidence (EvidenceBundle)、Identity (统一前缀)、History (task.history 模式可推广到 Project)。
- FUTURE: actor_id/actor_type 强制、trace_id 贯穿、retention 策略、数据目录 (catalog)。

## 31. Known Gaps

| ID | 类别 | 说明 | 级别 |
| --- | --- | --- | --- |
| G1 | Repository 边界 | **已修复 (2026-09-01)**: agent_loop.py:908/930 → org ProjectStore 门面; query_engine task.json → org ManagementStore 门面。残余: service/monitor/project_scan/analysis_tools 直接拼路径读 task.json (只读, 待逐步收敛); actions.py 用 read_projects 助手 (统一口径, 可接受) | P2 |
| G2 | 并发 | **部分修复 (2026-09-01)**: org store/management/console_sessions 写操作加 flock + 事务 update 接口 (test_concurrency 5 场景验证)。残余: 业务层 get→save 模式 (agent_loop 状态流转等) 未全量迁移至 update; 跨文件 ACID 仍无 (SQLite 阶段) | P2 |
| G3 | Project history | Project 无独立 history 链 (有 lifecycle 事件) | P2 |
| G4 | Provenance | actor_id/actor_type/trace_id 未全量贯穿 | P2 |
| G5 | Delete | 项目删除不级联会话/记忆 (保留=符合审计要求, 但删除语义需显式文档) | P2 (已文档化) |

## 32. UNKNOWN

- 完整 Event 清单 (events/models.py 151 枚举成员) 未逐项展开 — 需要时可另审。
- 多进程实际并发写入冲突的**实测频率**未统计 (无压测)。
- `tasks/` 旧目录 (旧 tasks/*.json) 与 backlog task.json 的双轨兼容细节 — cli_factory.py:2468 有定位兼容, 未深挖迁移状态。
- conversation_os 旧组件 (`/api/conversations/*`) 与 session 体系的关系 (独立, 未审计其存储边界)。

---

# MATRICES

## SSOT MATRIX
| Entity | SSOT | Owner | Writer | Readers |
| --- | --- | --- | --- | --- |
| Project | org/projects.json | org | ConsoleService | CLI/API/session/orchestrator/frontend |
| Task | backlog/task.json | org.management | service/agent_loop | query_engine/scan/monitor/CLI |
| Session/Message | console_sessions.json | SessionStore | SessionStore | frontend/agent_loop |
| Run | progress.json | Recorder | Recorder | run-status/liveness |
| Evidence | EvidenceStore | evidence.py | EvidenceStore | 审计/前端 |
| Event | events store | factory-core | EventLogger | 审计/查询 |

## HISTORY MATRIX
| Entity | History Source | Mutable? | Retention |
| --- | --- | --- | --- |
| Task | task.history (状态转换追加) | 不可变 | 项目生命周期内 |
| Message | messages 顺序 | 追加 | 会话生命周期 |
| Run | progress stages | 覆盖 | run 生命周期 |
| Project | (lifecycle 事件) GAP | — | — |

## EVENT MATRIX
| Event | Producer | Stored In | Consumers |
| --- | --- | --- | --- |
| org.project.* | org/events.py | EventLogger (events store) | 审计/查询 |
| org.project.deleted | ProjectLifecycle | EventLogger | 审计 |

## AUDIT MATRIX
| Action | Actor | Target | Evidence | Storage |
| --- | --- | --- | --- | --- |
| 项目/任务/会话操作 | human/agent (部分有 source) | 对象 id | audit_store | audit |

## CACHE MATRIX
| Cache | Source | Rebuild Method | Safe Delete |
| --- | --- | --- | --- |
| workspace/projects.json | ensure_space | 目录扫描回填 | ✅ (测试证明) |
| localStorage 主题/语言 | UI 偏好 | — | ✅ |

## PROJECTION MATRIX
| Projection | Source | Consumer | Rebuildable |
| --- | --- | --- | --- |
| report.json | progress | 报告 API | ✅ |
| 任务统计/完成度 | task.json | WebUI/回答 | ✅ |
| 话题摘要/项目记忆 | messages | context 注入 | ✅ |

## RUNTIME MATRIX
| Runtime State | Persistent Equivalent | Restart Behavior |
| --- | --- | --- |
| run_liveness cancel/alive | progress.json + STALE 检测 | 标志丢失, 僵尸标 STALE |
| SSE 连接 | — | 断连重连 |
| F-01 session cancel | — | 重启即失 (执行线程随进程) |

## EVIDENCE MATRIX
| Evidence | Produced By | References | Immutable? |
| --- | --- | --- | --- |
| EvidenceBundle | EvidenceBuilder (repo/execution) | project_id/agent_id | ✅ |
| message meta.tool_calls | agent_loop 工具执行 | 消息 | ✅ |

## IDENTITY MATRIX
| Entity | ID | Generator | Scope | Lifetime |
| --- | --- | --- | --- | --- |
| Project | P-xxx | org | 全局 | 项目 |
| Session | sess-* | console_sessions | 全局 | 会话 |
| Message | msg-* | console_sessions | 会话 | 会话 |
| Run | R{ts} | agent_loop | 项目 | run |
| Approval | APR-* | 审批 | 全局 | 审批 |
| Evidence | bundle | EvidenceStore | 全局 | 证据 |

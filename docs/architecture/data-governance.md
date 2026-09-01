# AI Factory Data Governance Contract

> 版本: v1 | 日期: 2026-09-01
> 前置: Data Foundation Contract (data-model.md) + JSON Storage v2 (b7802e61)
> 原则: **数据契约先于存储实现。** 真实代码为证, 无法证明 → UNKNOWN。

---

## 0. 冻结的原则 (本契约宪法)

1. **数据契约先于存储实现** — JSON 只是当前 Persistence Adapter, 不是 Domain Contract。
2. **业务逻辑不得依赖 JSON** — Domain/Service/API/Agent 不知道底层是 JSON/SQLite/PostgreSQL。
3. **WebUI 永远是 View, 不是真实数据源** — 前端不拥有事实, 只经 API 读投影。
4. **每个 Domain 只有一个 SSOT** — 允许 History/Event/Audit/Projection/Cache, 但不得冒充事实源。
5. **Cache/Projection 永远可重建** — 删除后从 SSOT 恢复, 不丢核心事实。
6. **History/Event/Audit/Evidence 不可被普通业务状态覆盖** — 追加式, 不可变。
7. **Storage Adapter 可替换, Domain Contract 不随数据库改变**。
8. **未来 SQLite/PostgreSQL 是存储实现变化, 不是业务模型变化**。

---

## 1. Identity

| Entity | ID 格式 | 生成器 | 全局唯一 | 持久 |
| --- | --- | --- | --- | --- |
| Project | `P-xxx` | org 注册 (ProjectStore) | ✅ | ✅ |
| Session | `sess-{hex}` | `console_sessions._new_id` | ✅ | ✅ |
| Message | `msg-{hex}` | `console_sessions._new_id` | ✅ | ✅ |
| Run | `R{ms-timestamp}` | `agent_loop` / `workflow_runner` (两处同规则) | ✅ (时间戳) | ✅ |
| Task (backlog) | 管理侧自增/模块生成 | `org.management.TaskSection` / `decomposer._new_id` | 项目内 | ✅ |
| Approval | `APR-*` | 审批生成 | ✅ | ✅ |
| Evidence | bundle id | `EvidenceStore` | ✅ | ✅ |
| 次级实体 (obs/lc/effexp/rb/trace…) | `obs-*` `lc-*` 等 | `uuid.uuid4` | ✅ | ✅ |

**发现**:
- ✅ 无第二套 **Project** Identity (orchestrator 用同一 project_id; 目录 slug 是投影)。
- ⚠️ ID **生成器分散 4 处** (`console_sessions._new_id` / `task_registry._new_id` / `decomposer._new_id` / `intelligence.models._new_id`), 前缀规则各自定义, 无统一入口 — **无冲突但无单点**, 契约冻结现有规则, 未来统一入口 (P2)。
- ✅ 业务层不拼**持久化** ID: `workflow_runner:886` 的 `T-{project_id}-{name}` 是 dev 执行请求临时 ID (SimpleNamespace, 不落盘 task store), 非 SSOT 任务 ID — 记 P3 观察 (格式易混)。
- ✅ 任务 ID 在 backlog 内唯一 (TaskSection upsert by id)。

**契约**: 禁止业务层自行生成/拼接持久化事实 ID; 新实体 ID 必须经 Store/Registry 生成。

## 2. Schema

| Entity | 必填 | 可选 | 枚举 | schema_version |
| --- | --- | --- | --- | --- |
| Project | id, name | 33 字段 (data-model §21) | lifecycle (idea→…→development) | ❌ 无 |
| Task | id, title | description/priority/status/assignee/dependency/history/exec_ref/exec_result | priority P0-P3; status todo/ready/in_progress/blocked/review/done | ❌ 无 |
| Session | id, scope, status | project_id/feature_id/task_id/title/run_ids | scope company/project; status active/archived | ❌ 无 |
| Message | id, session_id, role, content | meta (tool_calls/evidence/usage) | role user/assistant | ❌ 无 |
| Artifact manifest | — | — | — | ✅ `schema_version` (artifact_contract.py) |

**发现**: 仅 Artifact Manifest 有 `schema_version` (CONTRACT_SCHEMA_VERSION); 核心实体 (Project/Task/Session/Message) 无 version 字段。
**兼容策略**: pydantic model 全字段带默认值 + 宽容解析 (TaskPriority.parse/status.parse 大小写不敏感) — 旧数据加载零破坏 (test_project_entity "旧 projects.json → model_validate 零破坏" 验证)。
**契约**: schema 演进向后兼容 (新字段带默认); `schema_version` 扩展到核心实体 = FUTURE (SQLite 阶段前)。

## 3. Ownership (唯一事实写者)

| Domain | 唯一写者 | 绕过路径 |
| --- | --- | --- |
| Project | ConsoleService + org ProjectStore | 无 (WebUI 只经 API) |
| Task | service.create_task / agent_loop / org.management | 无 |
| Session/Message | SessionStore | 无 |
| Run | Recorder (workflow_runner) | 无 |
| Event | EventLogger (factory-core) | 无 |
| Audit | audit_store / audit_emitter | 无 |
| Evidence | EvidenceStore | 无 |
| Memory | MemoryStore / TopicLedger | 无 |
| Repair | quality.RepairManager | 无 |

**验证**: G1 已收敛核心读路径 (agent_loop/query_engine → Store 门面); 写路径全部经 Store (data-model §18); WebUI 纯 View (localStorage 仅主题/语言)。

## 4. History

| 对象 | 当前状态 | 历史 | 不可变 | 产生者 |
| --- | --- | --- | --- | --- |
| Task | task.status | task.history [{time,actor,action,result}] | ✅ 只追加 | ManagementStore 状态转换 |
| Session | session.status | messages 顺序 | ✅ 追加 (truncate 删尾) | SessionStore |
| Run | progress.json status | stages/errors | 覆盖式 | Recorder |
| Project | org lifecycle | **无独立 history 链** (G3) | — | 仅 lifecycle 事件 |

**GAP**: Project 状态变更 (lifecycle/name/archive) **无统一 history** — 有 org.project.* 事件 (EventLogger), 但无按项目聚合的 history 视图。
**契约**: 当前状态 ≠ 历史; Task.history 不可变; 状态变更应产生 Event (见 §5)。

## 5. Event

- **事件体系**: factory-core events (`Event`, `EventType` 151 枚举) + `org/events.py` (org.project.*) + `audit/audit_event.py` (TASK_CREATED/TASK_COMPLETED…)。
- **task 事件覆盖不全**: `audit_explain.py` 明示 "未找到任务 TASK_CREATED 审计事件 (任务可能未记录审计)" — 部分任务创建路径未发事件 (P2)。
- **契约**: 核心状态变更 (TaskCreated/TaskStarted/TaskCompleted/ProjectLifecycleChanged/ApprovalGranted/RunCancelled) 必须产 Event; 事件追加式不可变。

## 6. Audit

**现状 (完整)**:
- `audit/audit_event.py` — EventType (任务/项目/审批/决策)
- `audit/audit_store.py` — AuditStoreProtocol
- `audit/audit_emitter.py` — emit (project_id/task_id/agent_id/actor_type/actor_id)
- `audit/audit_explain.py` — 为什么创建/批准 (TASK_CREATED 事件+决策+计划)
- `api/audit.py` — audit_trace (trace_id 链路) / audit_decisions / audit_export
- `session/audit.py` / `session_audit.py` — 会话审计

**契约**: Audit 回答 WHO/WHAT/WHEN/WHY/RESULT; before/after 状态变更在 task.history + audit events 可关联; 完整追溯经 trace_id。
**GAP**: before/after 字段非统一强制 (部分事件有 from/to, 部分无) — P2 治理扩展点。

## 7. Provenance

| 字段 | 存在? | 写入点 |
| --- | --- | --- |
| actor_type / actor_id | ✅ (事件层) | learning_engine_v2 / effectiveness / rollback / intelligence / recovery (actor_type="system") |
| trace_id | ✅ (事件层) | control_tower / recovery (trace_id=run_id) / audit_trace |
| source | ✅ (部分) | org/events source="org"/"cli"/"console" |
| caused_by / parent_event_id | ❌ 无 | — |

**契约**: Human/Agent/System/Tool 来源区分 — 事件层已支持 (actor_type); 业务写 (session/task) 未统一携带 actor — P2 治理扩展点, 不强行补字段。

## 8. Retention / Delete

| 数据 | 允许删除? | 方式 | 审计保留? |
| --- | --- | --- | --- |
| Project | ✅ (org delete + 目录清理) | hard (无 tombstone) | ✅ 事件/审计保留 |
| Task | ✅ (随项目/delete_task) | hard | history 随删 |
| Session | ✅ delete_session | hard (本体+消息) | ❌ (删后无审计引用) |
| Run | ✅ (随项目清理) | hard | progress/report 随删 |
| Event/Audit/Evidence | ❌ (不可删) | 追加式 | — |
| Cache (workspace index/localStorage) | ✅ | 直接删, 可重建 | — |
| archived (项目/会话) | 软归档 | status=archived | ✅ |

**契约**: 删除 ≠ 物理删除 (archive 先行); Audit/Event/Evidence 不可删除 (保留为不可变事实); soft-delete/tombstone/purge 边界 = FUTURE (当前无机制, 记 GAP)。

## 9. Cache / Projection

| 项 | 类别 | 来源 | 可重建 | 反向覆盖 SSOT? |
| --- | --- | --- | --- | --- |
| workspace/projects.json | CACHE (index) | ensure_space | ✅ (目录扫描) | ❌ |
| workflow progress.json | PROJECTION | Recorder | ✅ (run 执行) | ❌ |
| report.json | PROJECTION (终态) | progress | ✅ | ❌ |
| 任务统计/完成度 | PROJECTION (计算) | task.json | ✅ (每读计算) | ❌ |
| topic_ledger 摘要 | PROJECTION (派生) | messages | ✅ | ❌ |
| project_memory | PROJECTION (派生) | topic 摘要 | ✅ | ❌ |
| localStorage (主题/语言) | CACHE (UI 偏好) | 用户 | ✅ | ❌ |

**验证**: 无 Cache/Projection 反向写 SSOT; 全部可重建。

## 10. Data Lineage

```
User → WebUI(View) → API → Service → Domain → Store → SSOT
   → Event → History/Audit/Evidence → Projection/Cache → API → WebUI

Action → Event (发生了什么) → Audit (谁/何时/为何) → History (状态变化) → Projection
```

(完整双链图见 data-model.md §17, 本契约冻结不变)

## 11. Concurrency Governance

**现状 (JSON Storage v2, b7802e61)**: thread-safe (RLock) + process-safe (flock per-file) + atomic replace + 事务 update (update_task) + 5 场景多进程测试。
**FUTURE (SQLite 阶段)**, 本轮不实现:
- revision / optimistic concurrency (stale write detection)
- cross-record transaction / cross-file transaction
- multi-agent 业务层 stale write (Agent A 读旧状态做决策后 update — 目前 flock 只保证文件级不覆盖, 不保证业务级不陈旧)

## 12. Data Governance Matrix

| Domain | SSOT | Identity | Owner | History | Event | Audit | Provenance | Retention | Cache/Projection |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Project | org/projects.json | P-xxx | ConsoleService/org | ⚠️ 缺独立链 (G3) | org.project.* | ✅ | source | archive+hard | workspace index (CACHE) |
| Task | backlog/task.json | 项目内唯一 | service/agent_loop/management | ✅ 不可变 history | ⚠️ 部分 (TASK_CREATED 缺) | ✅ | actor (history) | 随项目删 | 统计 (计算) |
| Session | console_sessions.json | sess-* | SessionStore | ✅ messages | — | ✅ | — | delete_session | — |
| Message | console_sessions messages | msg-* | SessionStore | ✅ | — | ✅ (evidence) | — | 随会话 | tool_calls 投影 |
| Run | progress.json | R{ts} | Recorder | stages | ✅ | ✅ | trace_id=run_id | 随项目 | report.json |
| Event | events store | seq | EventLogger | ✅ | ✅ | ✅ | actor_type/trace_id | 不可删 | — |
| Audit | audit store | — | audit_emitter | ✅ | ✅ | ✅ | actor_type | 不可删 | — |
| Evidence | EvidenceStore | bundle | EvidenceStore | ✅ | — | ✅ | project/agent | 不可删 | — |
| Memory | project_memory/ | — | MemoryStore | ✅ | — | — | — | 不删 | 派生摘要 |
| ProductProgress | product_progress.json | — | progress | — | — | — | — | 随项目 | — |

## 13. Storage Independence

**已达成 (核心路径)**: Domain/Service/API/Agent 经 Store Contract 访问数据; JSON 仅 Persistence Adapter。
**残余**: service.py:3401 / monitor / project_scan / analysis_tools 直接拼路径读 task.json (只读, P2 逐步收敛); actions.py 用 read_projects 统一助手 (可接受)。
**未来**: `Store Contract → {JsonStore, SQLiteStore, PostgresStore}` — Domain 语义不变。

---

## 14. P0 / P1 / P2 / P3

```
P0: 0
P1: 0
P2:  ID 生成器统一入口 (4 处分散, 无冲突)      [契约冻结, 未来统一]
     schema_version 扩展到核心实体             [FUTURE, SQLite 前]
     task 事件覆盖不全 (TASK_CREATED 缺路径)    [契约定义, 逐步补]
     Project 独立 history 链 (G3)             [契约定义]
     Provenance 贯穿业务写 (actor 统一)        [治理扩展点]
     before/after 统一强制                     [治理扩展点]
     残余读散布 (service/monitor/scan)         [逐步收敛]
P3:  workflow_runner T-{pid}-{name} 临时执行 ID 格式易混 (不落盘, 无风险)
UNKNOWN: 部分任务创建路径是否发 TASK_CREATED 的完整清单; soft-delete 机制
```

## 15. 最小修复建议 (本轮不实施 — 全部为 P2/P3, 无 P0/P1)

无 P0/P1 → **本轮零代码修改**。P2 项在后续 SQLite 阶段前按优先级实施。

## 16. SQLite 阶段可保持不动

- Domain 模型 (org.projects/management/session pydantic) — 不变
- Service 层 (ConsoleService 业务逻辑) — 不变
- API 层 (fastapi_adapter 端点契约) — 不变
- WebUI — 不变
- 事件/审计/证据模型 (factory-core events / audit / evidence) — 不变
- 变更点: Store 内部实现 (save/get/list/update/delete + file_lock → SQLite 事务)

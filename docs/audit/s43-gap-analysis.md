# S43 Gap Analysis — Unified Entity/Data Contract (Master Plan S42)

> 日期: 2026-08-29 | HEAD: 0cfa0d13 (v1.1.349)
> 注: 本 Sprint 执行 Master Plan 的 "S42 Unified Entity/Data Contract" (编号顺延为 S43 避免与已交付 Intelligence Strategy Kernel 冲突)

## GAP Audit
| 能力 | 现状 | 判定 |
|------|------|------|
| AuditEvent (correlation_id/trace_id) | audit/audit_event.py (S0.5 起) | REUSE |
| 统一 ID Contract | 各服务 uuid4().hex[:N] 无前缀 (run-/mem-/snap- 等分散) | MISSING |
| Universal Entity Contract | 各服务 dict 自建字段 | MISSING |
| Version Contract (optimistic concurrency) | 无 (VERSION_CONFLICT 未定义) | MISSING |
| 统一 Lifecycle 引擎 | 各服务自建状态机 (部分非法迁移拒绝) | PARTIAL (需统一) |
| Command Contract | CLI/API 各自 | MISSING |
| Event Contract (correlation/causation) | AuditEvent 有 correlation_id | PARTIAL |
| Error Contract | 各服务自抛 ValueError | MISSING |
| Pagination Contract | 无 | MISSING |
| Realtime Event Contract | 无 | MISSING |
| Conversation/Requirement/Analysis/Decision/Project/Sprint/Task/Node/Run/Artifact/Evidence/Approval 统一关系 | 分散 | MISSING |

## 设计
```
Unified Contract 层 (unified_contract.py):
- ID Contract: 统一前缀 (org_/dept_/workforce_/agent_/plugin_/conv_/msg_/req_/analysis_/
  decision_/project_/sprint_/task_/node_/run_/artifact_/evidence_/incident_/approval_)
- Universal Entity Contract: id/type/version/status/created_at/updated_at/created_by/
  owner/parent_id/project_id/lineage/policy/permissions/metadata
- Version Contract: entity_version + optimistic concurrency (VERSION_CONFLICT)
- Lifecycle Engine: Created→Validated→Active→Suspended/Blocked→Completed/Retired
  (domain lifecycle 扩展; Command→Policy→Validation→Transition→Event→Projection)
- Command Contract: request_id/entity_id/version/command/actor/timestamp/policy_context
  Response: success/data/entity_version/event_ids/warnings/errors
- Event Contract: actor/actor_type/action/entity/before/after/reason/policy/decision/
  timestamp/correlation_id/causation_id
- Error Contract: code/message/entity_id/request_id
- Pagination Contract: page/page_size/total/items
- Realtime Event Contract: event_id/type/entity/entity_id/version/timestamp/correlation_id
- 13 实体统一关系: Conversation→Requirement→Analysis→Decision→Project→Sprint→Task→Node→Run→Artifact→Evidence→Incident→Approval
```

## 复用
audit_event.py (correlation_id) + 现有服务

## 禁止
- 第二套 Event/Governance/Audit/Permission/Progress 模型
- UI 直接改 status / Agent 保存 OS 事实 / Projection 当真相

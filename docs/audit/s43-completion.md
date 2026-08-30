# S43 Unified Entity/Data Contract — Completion Report (Master Plan S42)

> 日期: 2026-08-29 | HEAD: (S43 commit) | v1.1.350
> 说明: 本 Sprint 执行 Master Plan 的 "S42 Unified Entity/Data Contract"(编号顺延 S43, 避免与已交付 S42 Intelligence Strategy Kernel 冲突)

## 1. ID Contract — REAL
统一前缀 (org_/dept_/workforce_/agent_/plugin_/conv_/msg_/req_/analysis_/decision_/project_/sprint_/task_/node_/run_/artifact_/evidence_/incident_/approval_/cmd_/evt_/corr_);未知类型拒绝;类型匹配校验。

## 2. Universal Entity Contract — REAL
14 基础字段 (id/type/version/status/created_at/updated_at/created_by/owner/parent_id/project_id/lineage/policy/permissions/metadata);缺字段/非法 id 拒绝。

## 3. Version Contract — REAL
乐观并发: 基于旧版本修改 → **VERSION_CONFLICT**(ConcurrencyError, 非静默覆盖);bump 产生 lineage。

## 4. Lifecycle Engine — REAL
Created→Validated→Active→Suspended/Blocked→Completed/Retired;非法迁移拒绝;history append-only;Command→Policy→Validation→Transition(禁 UI 直接改 status)。

## 5. Command/Response Contract — REAL
cmd_ request_id/entity_id/version/actor/timestamp/policy_context;Response: success/data/entity_version/event_ids/warnings/errors。

## 6. Event Contract — REAL
actor/actor_type/action/entity/before/after/reason/policy/decision/timestamp/**correlation_id/causation_id**(可回溯链)。

## 7. Error/Pagination/Realtime — REAL
统一 ERROR_CODES;Pagination(page/pages 修正);Realtime Event(REST/WebSocket/SSE 共用)。

## 8. 13 实体统一关系 — REAL
conv→req→analysis→decision→project→sprint→task→node→run→artifact→evidence→incident→approval;Lineage 追溯(node→conv 全链)。

## 9. CLI/API — REAL
factory entity 5 命令 + 4 API 端点(openapi 293)。

## 10. Tests — 12
id/entity/version/lifecycle/command-response/event/error/pagination/realtime/relations-lineage/CLI/API。

## 11. Regression
```
S43: 12/12 | 全量: 1044 passed + 6 skipped (零失败) | Zero-Stub: PASS | 前端 tsc: PASS
```

## 12. Commits
feat: S43 Unified Entity/Data Contract + chore(版本): bump v1.1.350 + tag

## 13. Final Verdict
**S43 = PASS** — 冻结统一数据与接口基础: ID/Entity/Version/Lifecycle/Command/Event/Audit/Lineage/Error/Pagination/Realtime 全 Contract REAL;13 实体统一关系 + 追溯;ONE Entity Contract/ONE Lifecycle/ONE Event/ONE Governance 原则落地。为 S44 Conversation OS 奠定基础。按 Master Plan 继续,等待下一步决策。

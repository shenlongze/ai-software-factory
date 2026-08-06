# ADR-0028 — Phase 9c: Human Decision Intelligence (通用人工决策系统)

> 日期: 2026-08-06 | 状态: Accepted | 前置: Phase 9b (35bb150, 3148 tests)

## 背景

9a/9b 已具备 Approval Gate (pending/approved/denied) 与"生成后自动申请审批"。
Phase 9c 把简单 approve/reject 升级为**通用人工决策系统**, 供 PRD/UI/Deploy/
Operation 等全部产品阶段复用: 四终态状态机 + Artifact 版本绑定 (禁覆盖历史) +
审批队列/历史 + Workflow 暂停/恢复 + CLI/Dashboard 完整接线。冻结约束:
**Core 零修改 / Extension only / Event 唯一事实源 / Artifact lineage /
Provider Intelligence 复用** (同 9a/9b)。

## 决策

### 1. 状态机语义升级三件套 (9a → 9c 兼容核心手法)

`awaiting_approval` → `paused`; `denied` → `rejected`。三件套缺一不可:

1. **遗留枚举成员保留只读**: `WorkflowStatus.AWAITING_APPROVAL` /
   `ApprovalStatus.DENIED` 仍存在 (读兼容旧数据), 注释标注 "9a 遗留";
   DENIED 不参与新流转, 新写入一律 rejected。
2. **输入别名映射**: `DECISION_ALIASES = {"denied": "rejected"}` — decide 输入
   denied 归一 rejected (兼容 9a CLI deny 动词与旧调用); `list_approvals(status=...)`
   同样归一。CLI argparse choices 保留 `deny` 为兼容别名 (移除会让既有错误路径
   测试在 argparse 层 SystemExit(2), 以另一种方式炸)。
3. **行为观察点测试最小化更新**: 断言旧值的测试数学上必然失败 (行为观察点非
   API), 最小化更新断言、实现零改动。本次 7 处 (6 兼容 + 1 连带, 见 §6)。

### 2. 兼容事件双发 + CLI 锚点用新语义事件

服务层终态路径**双发**兼容事件 (9a 下游仍可消费):
- approved → `approval.approved` + `approval.granted` (9a 兼容, Product Decision
  锚定 granted 事件 event_id, Lineage 闭环)
- rejected → `approval.rejected` + `approval.denied` (9a 兼容)

CLI decide 的 event_seq / 事件名锚点**只取 9c 事件**: `_DECISION_EVENT` 映射表
(终态值 → EventType.APPROVAL_*), 不用 granted/denied 取序 — 兼容事件不参与
CLI 取序 ("终态事件单一"教训的 CLI 侧升级: 锚点指向报告的状态转换)。
完整事件集: approval.created/pending/required(9a)/approved/granted(9a)/
rejected/denied(9a)/changes_requested/delegated/resumed/viewed +
product.approval_experience.recorded。

### 3. Workflow Pause/Resume (PAUSED → 终态 → resumed)

- `request_approval` 落 pending 后 `_pause_workflow_for`: 仅 **RUNNING** workflow
  进入 paused (未批准不自动推进; 无 workflow / 非 running 不动 — 9a
  awaiting_approval 细化)。
- approved → `_advance_workflow_for`: workflow 回 running + **推进下一 stage** +
  记录 product_decision + `approval.resumed (reason=approved)`。
- rejected / changes_requested / delegated → `_resume_workflow_for`: workflow 回
  running、**停留当前 stage** (进入修改流程) + `approval.resumed (reason=终态值)`。
- 手动 `workflow resume <idea_id>`: paused (含 9a 遗留 awaiting_approval) →
  running, reason=manual; 未暂停 → rc 1, 无 workflow → rc 7。
- **关键前提 (收尾实测)**: resume 事件只在 workflow 处于 paused 时发出 — 审批
  请求必须先于 workflow 存在且已暂停。测试构造 approve 链须按
  idea → workflow start → approval request → decide 顺序, 否则无
  approval.resumed (非实现 bug)。

### 4. Artifact Version 绑定 (revise 禁覆盖历史)

`revise_artifact` 产出**新 Artifact id** + `version + 1` + `supersedes` 指向旧
版本 — 旧版本永不覆盖 (lineage 可回溯); content 增量合并 + revision_note;
version_history 按 version 排序。审批链与版本绑定: v1 approved → revise v2 →
**重新审批** (v2 新请求); 同 version 重复批准由队列唯一性守卫拒绝。终态可逆:
rejected/changes_requested/delegated 可同 version 重新提交 (新请求);
approved 仅 version 递增后可再申请。模型校验 version ≥ 1、confidence ∈ [0,1]。

### 5. Approval Queue / History + Dashboard 增列 (非新视图)

- `approval_queue`: 每行 = request dict + artifact 只读联表
  (artifact_type/artifact_version/confidence; artifact 缺失 → None/0.0 失败安全)
  + `required_action` (pending → decide; approved → none; rejected/
  changes_requested → revise & re-request; delegated → await delegate)。
- `approval_history`: 请求 + 决定联表 (未决定 → None), 未找到 artifact → rc 7。
- Dashboard: **既有 Product View 增列 (非新视图)** — ProductSnapshot 加
  approval_rejected/changes_requested/delegated (默认 0) + approval_history
  (默认 []) + approvals 行富化 + 新 History 表 + summary 终态计数仅 >0 条件
  追加 — **默认关 + 空默认值双保险, VIEWS 精确集合断言零破坏** (同 9a/9b 先例)。

### 6. 测试观察点更新 (行为观察点非 API) + 收尾修 2 CLI 断言

兼容更新 7 处 (tests/product):

| 测试 | 旧断言 | 新断言 |
|---|---|---|
| test_product_service_workflow.py::test_request_approval_pauses_workflow | == AWAITING_APPROVAL.value | == PAUSED.value |
| test_product_service_approval.py::test_deny_transitions_request | status == "denied" | == "rejected" (denied 别名注释) |
| test_product_dashboard.py::test_workflow_awaiting_approval_status | {"awaiting_approval": 1} | {"paused": 1} |
| test_product_generator.py::test_prd_approval_workflow_pause_linkage | == "awaiting_approval" | == "paused" |
| test_product_cli.py::test_decide_deny | "DENIED" + "approval.denied seq=" | "REJECTED" + "approval.rejected seq=" |
| test_product_cli.py::test_workflow_pauses_and_resumes_via_cli | == "awaiting_approval" | == "paused" |
| test_product_cli.py::test_decide_approve (连带) | "approval.granted seq=" | "approval.approved seq=" |

收尾 2 CLI 断言 (tests/product/test_product_cli_decide_9c.py, 非实现 bug):
- `test_resume_paused_to_running`: `--json` 输出无文本锚点, 删
  `assert "approval.resumed seq=" in out` (JSON 输出为结构化 event_seq 字段,
  已由 `assert data["event_seq"]` 覆盖)。
- `test_decide_approve_events_9c_anchor`: 原链无 workflow (未 workflow start)
  → 无 approval.resumed。按 §3 顺序改为
  idea → workflow start → approval request (暂停) → decide approve。

新增 6 测试文件 106 测试 (tests/product/): test_product_state_machine_9c (24) /
artifact_version_9c (21) / approval_queue_9c (16) / cli_decide_9c (19) /
events_9c (15) / pause_resume_9c (11) — 达"新增 ≥100"。

### 7. Removal Isolation 源码级断言分级

dashboard/collector 的源码级断言比 cli/commands 严: collector 断言全文不含
"import product"/"from product" (任意位置), commands 只禁顶层 (函数内缩进延迟
导入允许)。collector 需要 `service._required_action` 时**内联纯函数副本**
(8 行状态映射 + 注释说明守铁律原因), 不跨包导入。

## 影响

- Core 零修改; providers/** 只读复用 (CostAwareSelector 等); 9a/9b 事件与
  Dashboard 输出逐位兼容 (增列/加事件纯增量)。
- product/: models/service/store/events 扩展状态机 + 版本 + 队列 + 暂停恢复;
  cli/ (main.py 4 触点 + commands.py 命令层动词映射) + dashboard/
  (models/collector/views 增列)。
- EventType 新增 (approval.rejected/changes_requested/delegated/resumed 等),
  纯增量枚举, 不改表不破坏既有测试。
- 测试: 3148 (9b) → 全量 ≥3263 passed (106 新增 + 7 兼容更新 + 2 收尾断言,
  零删除)。

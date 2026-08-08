# S9-001 — Approval Gate（Completion Report）

> 日期: 2026-08-09 | 状态: ✅ 完成 (待人工审核) | pytest 6357 (6274 基线 + 83 新增)
> 目标: 人工审批门 (Approval Gate) — approval_required stage COMPLETED → 门 PENDING → workflow PAUSED → approve 继续 / reject 停止

## 1. 实现概述

```
factory-core/events/models.py  EventType +3 (ADR-0001 扩展路径, Core 唯一允许改动点):
                              org.approval.created/approved/rejected — 门创建/放行/否决
factory-org/org/approval.py   新建: ApprovalStatus (PENDING→APPROVED/REJECTED 终态) +
                              APPROVAL_TRANSITIONS 受控转换表 (单向无环, 终态出边空) +
                              ApprovalGate 模型 + transition_approval + ApprovalGateStore
                              (approvals.json 原子写, 损坏失败安全 — 同 org 其他 store)
factory-org/org/projects.py   Stage + approval_required (默认 False — 旧 JSON 零破坏)
factory-org/org/workflow.py   WorkflowLifecycle + 审批门接线 (request/approve/reject +
                              守卫查询); WorkflowRunner/DevTestLoopRunner + 审批门守卫
                              (PENDING 挂起禁绕过 / REJECTED 响亮拒绝); 执行链钩子:
                              approval_required stage COMPLETED → 自动建门 → PAUSED 返回
factory-org/org/events.py     record_approval_created/approved/rejected (payload 唯一
                              事实源 + 顶层 project_id; source: 建门=org, 决定=cli)
factory-org/org/cli.py        approval list/show/approve/reject (人类 + --json; 错误
                              映射: 未找到 rc 7 / 非 PENDING 决定 rc 1)
约束: Core 冻结 (仅事件枚举) | WORKFLOW_TRANSITIONS/STAGE_TRANSITIONS 零修改
     | 零明文密钥 | 不实现 Console/Project Adoption (S9-002~006)
```

## 2. 新增/修改文件

```
新增:
  factory-org/org/approval.py            领域模型 + 状态机 + 持久化
  tests/s9/ (8 文件, 83 测试 = 79 用例函数 + 4 参数化展开)
    conftest.py / s9_helpers.py (唯一 basename, 防遮蔽)
    test_s9_approval_model.py 14 | test_s9_approval_store.py 12
    test_s9_approval_lifecycle.py 16 | test_s9_approval_events.py 9
    test_s9_approval_cli.py 12 | test_s9_workflow_approve.py 6
    test_s9_workflow_reject.py 5 | test_s9_smoke.py 5
修改 (只扩展不重写):
  factory-core/events/models.py          EventType +3 (允许例外)
  factory-org/org/{projects,workflow,events,cli}.py  审批门接线
  tests/intelligence/test_intelligence_events.py     事件计数 179 → 182
  factory-exec/benchmark_s8_demo/.gitignore           pattern 修正为相对路径
                                                     (防 app_project/ gitlink)
验证门: 全量 pytest / 四目录 diff / 密钥扫描 — 见 §9
```

## 3. Approval 模型 (ApprovalGate)

| # | 字段 | 类型 | 默认 | 说明 |
|---|------|------|------|------|
| 1 | id | str | — | 门 id (AG- + uuid, new_id) |
| 2 | stage_id | str | — | 被审批 stage (approval_required stage COMPLETED 后创建) |
| 3 | workflow_id | str | — | 所属 workflow (决定后恢复/停止目标 — 冗余 scoping) |
| 4 | status | ApprovalStatus | pending | PENDING/APPROVED/REJECTED (宽容解析, 大小写不敏感) |
| 5 | reviewer | str | "" | 决策人 (approve/reject 落库, 审计) |
| 6 | comment | str | "" | 决定理由 (reject 理由写入 workflow.failed_reason) |
| 7 | requested_at | datetime | utcnow | 门创建时间 |
| 8 | approved_at / rejected_at | datetime\|None | None | 决定时间 (终态落库) |

状态机 (受控转换表, 单向无环):

```
PENDING → APPROVED (放行, 终态) / REJECTED (否决, 终态)
approved/rejected 终态: 任何再流转 (含同状态重复决定) → ApprovalStateError
  — 决定不可撤销 (审计铁律: 一次决定, 永久记录; 改决定须新建门)
```

持久化: `<root>/org/approvals.json` (ApprovalGateStore, _SectionStore 模式 — 临时文件 + os.replace 原子写, 损坏响亮拒绝)。

## 4. Workflow 集成 (只扩展不改核心)

```
触发: approval_required stage COMPLETED → Runner 自动 request_approval
      → ApprovalGate (PENDING) + workflow ACTIVE→PAUSED (复用受控转换表)
approve → gate APPROVED → workflow PAUSED→ACTIVE (started from_status=paused)
      → Runner 继续下一 stage (下一门再挂起)
reject  → gate REJECTED → workflow FAILED 停止 (复用 PAUSED→ACTIVE→FAILED
      两跳合法路径 — WORKFLOW_TRANSITIONS 零修改; failed_reason 记录
      "approval rejected: <comment> (reviewer: <reviewer>)" 审计;
      代价: 审计多一条 started(from_status=paused) — 已说明)
Runner 守卫 (禁绕过审批门):
  run() 开头按序: COMPLETED 幂等返回 → REJECTED 门 → WorkflowStateError
  响亮拒绝 (含 failed→paused→active 重试路径 — 决定不可撤销) → FAILED 拒绝
  → PENDING 门 → 直接返回挂起 workflow (不自动恢复) → 才 activate
DevTestLoopRunner 独立 run() 循环加同守卫 (不能只加 base Runner)
每 stage 至多一门: request_approval 校验 stage 存在 + approval_required=True
  + 按 stage 查重 (DuplicateError) — 响亮防误挂
```

## 5. CLI (approval list/show/approve/reject)

```
factory-org approval list   [--workflow X] [--status pending|approved|rejected]
                            [--stage X]  — 清单 (人类 + --json: approvals/count)
factory-org approval show   <gate_id>    — 详情 (approval + stage + workflow)
factory-org approval approve <gate_id> [--reviewer R] [--comment C]
                            — 放行 →APPROVED + workflow 恢复 (org.approval.approved)
factory-org approval reject  <gate_id> [--reviewer R] [--comment C]
                            — 否决 →REJECTED + workflow FAILED (org.approval.rejected)
错误映射: 未找到 rc 7 / 非 PENDING 决定 rc 1 / 参数错 argparse rc 2
读命令 (list/show) 不独立发 viewed 事件 — S9-001 事件 +3 约束 (见 §8 限制)
```

## 6. 测试结果 (tests/s9 83 全绿)

```
tests/s9: 83 passed (68 基线 + 15 修复), 0 failed, 4.0s 级
修复的 15 失败按根因分类:
  实现 bug 4 个: transition_approval 终态门 (approved/rejected) 再决定静默幂等
    → 响亮拒绝 ApprovalStateError (决定不可撤销审计铁律) — 影响 lifecycle/
    CLI 4 个 non_pending 测试 (重复决定必须 rc 1, 不能静默成功)
  夹具路径 7 个: 测试直调 request_approval 但 workflow 未 ACTIVE (门语义 =
    ACTIVE→PAUSED; DRAFT 不暂停 → approve 不恢复 / reject 不停止) — 夹具/
    helper/种子补 activate: lifecycle fixture + 直调测试, events
    _complete_first_stage, CLI _seed_pending_gate
  测试期望 4 个: ① events 事件名 org.stage.completed → org.workflow.stage_completed
    (S7-003 实际事件名); ② approve 恢复断言 started 须取最后一个 (activate
    启动 + 恢复两个 started); ③ CLI list 人类输出断言 "approvals" → "审批门
    清单" (人类输出为中文); ④ 挂起守卫允许 blocked (Runner 就绪评估会把依赖
    未满足的后续 stage 标记 BLOCKED — 同为"未执行"语义)
全量 pytest: 6357 = 6274 基线 + 83 新增 (精确对账; 事件计数 179 → 182 确认)
```

## 7. S9-002 接入说明 (Console 可视层 / 下期)

```
前置依赖: S9-001 已交付 ApprovalGate 模型 + approvals.json 持久化 +
  workflow 接线 + CLI (list/show/approve/reject) + 事件 org.approval.*
接入方式 (S9-002 Console):
  1. 阶段链: Console 审批视图直接消费 ApprovalGateStore 数据
     (list_approvals 按 workflow/status 过滤) — 零 workflow 改动
  2. input_artifacts: 无新产物类型 — 门是 stage 级属性, 视图绑定
     stage_id → workflow_id 即可展示上下文
  3. 消费重点: PENDING 门清单轮询 + gate 详情 (reviewer/comment 审计字段)
  4. executor 模式: Console 决定 = 调用 approve_approval/reject_approval
     (复用 org.approval.* 事件, source 沿 CLI 先例传 "console")
  5. 事件: org.approval.created/approved/rejected 已就绪; viewed 类读审计
     事件留给 S9-002 按 ADR-0002 补齐 (当前限制见下)
  6. 诚实边界: 本任务不实现 Console UI / Project Adoption; 只保证数据面
     与命令面就绪 (CLI 即最小可操作界面)
```

## 8. 当前限制 (诚实标注)

```
1. 读命令 (list/show) 未发 viewed 事件 — S9-001 任务约束事件 +3 (仅
   created/approved/rejected); viewed 类审计锚点由决定事件承载, S9-002
   Console 可视层补齐 (ADR-0002 张力已记录)
2. reject 停止复用 PAUSED→ACTIVE→FAILED 两跳 → 审计多一条 started
   (from_status=paused) — WORKFLOW_TRANSITIONS 零修改的已知代价
3. approve/reject 经 CLI/生命周期 API; Console UI / Project Adoption 未实现
   (S9-002~006, 本次禁止范围)
4. 门创建时机由 Runner 保证 (stage COMPLETED); 直调 request_approval 不校验
   stage 完成态 (API 契约: 调用方保证, 与设计文档一致)
```

## 9. 验证门

```
pytest 全量: 6357 passed, 0 failed (6274 基线 + 83 s9 新增; 事件计数 182)
tests 目录: tests/s9 8 文件 83 测试全绿
四目录 diff: factory-core (events/models.py +3 允许例外) / factory-console /
  factory-runtime / desktop = 0 改动
scripts_diag_empty.py 未触碰
密钥扫描: git diff 无 key/secret/token 明文
gitignore: factory-exec/benchmark_s8_demo/.gitignore pattern 修正为相对路径
  (app_project/ 生效, git check-ignore 命中, gitlink 风险解除)
commit: "S9-001: Approval Gate" → push → git status -sb (ahead 0)
```

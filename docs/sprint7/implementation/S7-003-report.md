# S7-003 — Workflow Engine（Completion Report）

> 日期: 2026-08-08 | 状态: 完成 | pytest 全绿 (5919)
> Sprint 7A: Execution Foundation (S7-003 Workflow Engine — 组织级编排壳 + Artifact 流转)

## 实现概述

S7-003 把 S7-001/002 的静态关联链升级为**可运行的 Workflow Engine**:
组织级编排壳 (org 侧) 编排 `User→Project→Workflow→Stage→Artifact` 全链 —
Workflow 生命周期状态机 (DRAFT/ACTIVE/PAUSED/COMPLETED/FAILED) + Stage 状态机
(PENDING/READY/RUNNING/BLOCKED/COMPLETED/FAILED) + DAG 依赖 + Runner 执行循环
(就绪判定 → Role Executor → 输出 Artifact 自动注册 → 推进)。

设计依据: sprint7-architecture.md §1/§3 (任务级 → 组织级; 阶段产物自动流转;
人工闸门保持; 事件审计)。**Core 任务级 WorkflowEngine (factory-core/workflows,
4 技术模板 CREATED/RUNNING/COMPLETED/FAILED + Step 顺序执行) 冻结零修改** —
本模块是组织级编排壳, 复用 Core 状态机/事件模式但不 import Core 业务模块
(Removal Isolation, 同 S7-001/002: 仅依赖 events 层)。

## 新增文件

```
factory-org/org/workflow.py              (Workflow Engine 核心: WorkflowStatus/
                                         WORKFLOW_TRANSITIONS 状态机 + Workflow/
                                         WorkflowSection 模型 + WorkflowLifecycle
                                         编排 + WorkflowRunner 执行循环 + DAG 校验
                                         + Artifact 集成 + workflow_files)
tests/s7/test_s7_workflow_model.py       (Workflow 模型全字段/宽容解析/终态)
tests/s7/test_s7_workflow_crud.py        (Workflow/Stage CRUD + 引用完整 + order)
tests/s7/test_s7_workflow_state.py       (Workflow 状态机合法链/非法跳转/幂等/事件)
tests/s7/test_s7_workflow_stage.py       (Stage 状态机 + 转换事件契约)
tests/s7/test_s7_workflow_dag.py         (DAG 拓扑序/循环拒绝/跨 workflow 拒绝)
tests/s7/test_s7_workflow_runner.py      (Runner 就绪判定/执行循环/失败路径/重试)
tests/s7/test_s7_workflow_artifact.py    (Artifact 集成: 输入门禁/项目隔离/输出注册)
tests/s7/test_s7_workflow_events.py      (org.workflow.* 8 事件 payload 契约 + 链序)
tests/s7/test_s7_workflow_cli.py         (workflow 子命令 create/list/show/run/status)
tests/s7/test_s7_workflow_integration.py (Project→Workflow→Stage→Artifact→Runner 全链)
```

## 修改文件

```
factory-org/org/projects.py        (StageStatus +READY/BLOCKED 枚举 + STAGE_TRANSITIONS
                                   受控转换表 — 纯增量成员, 既有值零改动)
factory-org/org/events.py          (+8 record_workflow_* 生命周期/流转/读审计函数;
                                   stage.created payload 增补 name/depends_on/
                                   input/output_artifacts — 向后兼容)
factory-org/org/cli.py             (workflow 子命令 create/list/show/run/status +
                                   --json 输出 + rc 语义 + _build_workflow_runner
                                   executor 注入点)
factory-core/events/models.py      (EventType +8 org.workflow.* 枚举成员) — 允许例外
tests/intelligence/test_intelligence_events.py (枚举计数 171→179 + 8 成员断言)
```

约束遵守: Core/Runtime/Desktop diff = 0 (events/models.py 枚举 +8 允许例外);
未触碰 scripts_diag_empty.py; 零 LLM/零执行副作用 (编排壳诚实边界 — executor=None
响亮拒绝, 不假装执行); 不重写执行链/Artifact (复用 ArtifactRegistry 契约);
不删既有能力; 无 rm / 无明文密钥。

## 架构说明

```text
User → Project → Workflow (run) → Stage (role_id=exec 注册表角色)
                                      └─ input_artifacts[] / output_artifacts[]
                                          → Artifact (VALIDATED 门禁 / 自动注册)

与 Core WorkflowEngine 解耦 (双引擎, 各司其职):
  Core:   单任务内步骤执行 (4 技术模板, 冻结, 零修改)
  org:    组织级工作流运行 (角色编排壳: PM→Architect→Developer→Tester→
          Release→Analytics 全链; 本层只建壳/流转/编排, 不调 LLM)
```

执行循环 (WorkflowRunner.run): 读 workflow → DRAFT/PAUSED 自动转 ACTIVE →
validate_dag (循环响亮拒绝) → 评估各 stage 就绪 (READY/BLOCKED) → 按 order 取
首个 READY → RUNNING → Role Executor (注入 callable: executor(stage, context)
→ dict; 不重写 EmployeeExecutor — S7-005 接真实执行适配器) → 输出 Artifact
自动注册 (create→generated→validated, 契约失败 → stage FAILED) → COMPLETED →
推进; 全部完成 → workflow COMPLETED; 无可推进 (BLOCKED) → 保持 ACTIVE (等待
外部输入/修复 — 不假装完成); 失败 → FAILED; 步数保护 (上限 = stage 数 + 1)。

## Workflow 数据模型

```text
Workflow (org/workflow.py):
  id / project_id (引用完整: 项目须存在) / name
  status (draft→active→paused→completed/failed, WORKFLOW_TRANSITIONS 受控表)
  stage_ids (编排层索引; 权威读取 = ProjectStore.list_stages_by_workflow)
  started_at / completed_at / failed_reason (运行审计)
  转换: →active 发 started (含 paused→active 重试恢复, from_status 区分);
        →completed 发 completed; →failed 发 failed (stage_id+reason);
        paused 无独立事件 (同 S7-001 stage 先例)

Stage (org/projects.py, S7-003 扩展全默认值 — 加载零破坏):
  id / workflow_id / role_id (exec 注册表单一事实源) / name / order
  depends_on[] (本 workflow 内前置; 跨 workflow/未定义 → WorkflowDependencyError;
               循环 → WorkflowCycleError, Kahn 拓扑检测)
  input_artifacts[] (全须 VALIDATED 且同项目/空项目 → 放行; 否则 BLOCKED)
  output_artifacts[] (Runner 完成回写 + stage_completed 事件带出)

存储: <root>/org/workflows.json (WorkflowSection, 独立文件); Stage/Artifact
复用 ProjectStore (零新数据空间)。
```

## Runner 流程（含 2 个真实 bug 修复）

```text
run(workflow_id):
  1. COMPLETED → 幂等返回; FAILED → WorkflowStateError (须 pause 人工介入)
  2. DRAFT/PAUSED → activate (org.workflow.started)
  3. validate_dag → 循环依赖响亮拒绝 (WorkflowCycleError)
  4. 循环 (步数上限 = stage 数 + 1):
     a. 就绪判定: 依赖全 COMPLETED 且输入全 VALIDATED → READY; 否则 BLOCKED
        (幂等转换, 每转换审计事件)
     b. 无 READY → break (保持 ACTIVE, 不假装完成)
     c. _execute_stage: RUNNING → executor(stage, context) → 输出注册 →
        COMPLETED / 异常 → FAILED
  5. 全部 COMPLETED → workflow COMPLETED (终态)

修复 1 — Runner 回写竞态 (实测 bug):
  症状: 执行期用旧 stage 对象回写 output_artifacts, 会把已流转的
  RUNNING 状态覆盖回 PENDING, 破坏 COMPLETED 转换 (转换表拒绝)。
  修复: 回写前重新 get_stage 取最新对象 (fresh), 再 model_copy 追加
  output_artifacts — 状态字段不受回写影响 (workflow.py _execute_stage)。

修复 2 — executor=None 吞掉 (诚实边界):
  症状: 编排壳无 executor 时若流转 RUNNING 再抛错, 阶段卡死在 RUNNING
  (不可恢复)。
  修复: executor=None 且需执行时, 在流转 RUNNING **前**响亮拒绝
  (WorkflowExecutionError) — 状态保持 READY, 注入 executor 后可直接重跑
  (不假装执行, S7-005 接真实 Role Executor)。
```

## Artifact 集成

```text
输入门禁 (Runner._is_ready):
  stage.input_artifacts 全部 VALIDATED 且 project_id ∈ ("", workflow.project_id)
  → READY; 未验证 / 缺失 / 跨项目 → BLOCKED (项目隔离铁律, S7-001 空 project_id 兼容)
输出自动注册 (Runner._register_outputs):
  executor 结果 (单产物 artifact_type/ref/metadata 或多产物 artifacts[]) →
  ArtifactRegistry: create (producer_role=stage.role_id, project_id 继承
  workflow, stage_id 归属) → mark_generated → validate (契约失败 → INVALID
  → WorkflowExecutionError → stage FAILED → workflow FAILED)
角色默认输出类型 (ROLE_OUTPUT_TYPES, exec 注册表 role_id 单一事实源):
  product-manager→prd / architect→design / ui-designer→design /
  developer→code / tester→test / devops→release
查询: stage_artifacts / workflow_artifacts (复用 ArtifactRegistry.query)
```

## 事件 (org.workflow.* +8, 枚举 171 → 179)

```text
org.workflow.created         workflow_id/project_id/name/status/stage_count
org.workflow.started         from_status/to_status (启动 + paused→active 恢复)
org.workflow.stage_ready     workflow_id/project_id/stage_id/role_id/name/status
org.workflow.stage_started   同上 (→running)
org.workflow.stage_completed 同上 + output_artifact_ids (产物引用审计)
org.workflow.completed       status/stage_count/completed_stage_count
org.workflow.failed          status/stage_id/reason (result=FAIL, 失败定位)
org.workflow.viewed          count/filters (读命令审计, source="cli", ADR-0002)
logger=None 全静默 (同既有 org 模式); payload 唯一事实源 (可重建编排关键字段)
事件链序: created→started→stage_ready→stage_started→stage_completed→completed;
失败链: ...→stage_started→failed; 阻塞挂起无 completed/failed (诚实审计)
```

## CLI

```text
factory-org workflow create|list|show|run|status
  create  --project P-1 --name "Ship v1" [--id WF-1]   (org.workflow.created)
  list    [--project P-1]                              (org.workflow.viewed)
  show    WF-1   (workflow + 阶段明细 + 产物引用; viewed)
  run     WF-1 [--max-steps N]  (Runner 执行; executor 经 _build_workflow_runner
          注入点 — S7-005 接真实执行; 未注入且需执行 → rc 1 响亮拒绝)
  status  WF-1   (阶段状态计数 status_counts; viewed)
  rc 语义: 0 成功 / 1 业务错误 (非法转换/未注入 executor/重复) / 7 未找到
  每个 CLI 行为产生事件 (ADR-0002); --json 输出 (ok/.../event_seq)
```

## 测试结果

```text
tests/s7: 398 passed (S7-001/002 既有 249 + S7-003 workflow 新增 149:
  model/crud/state/stage/dag/runner 103 + artifact/events/cli/integration 46)
pytest 全量: 5919 passed, 0 failed (5745 → 5919, 全绿)
tests/intelligence 枚举计数 171→179 同步更新 (S7-001 既定伴生模式)
Core/Runtime/Desktop diff = 0 (events/models.py 枚举 +8 允许例外;
scripts_diag_empty.py 未触碰)
测试修复: 2 个测试期望错 (查询用例 PM 阶段误用 code executor / CLI run
不审计 viewed — 实现未改, 断言对齐真实契约)
```

## S7-004 Tester Agent 接入方案

S7-004 (backlog P0, dep S7-001) = Tester Agent executable + Developer↔Tester
Loop, 接入本 S7-003 Workflow Engine 的 **executor 注入点**, 具体方案:

```text
1. Tester executor 契约 (直接复用 Runner 契约, 零新编排代码):
     executor(stage, context) → {"artifact_type": "test",
                                  "metadata": {"results": {...}, "bugs": [...]}}
   ROLE_OUTPUT_TYPES 已映射 tester→test; 产物自动注册/校验/审计全走 S7-003
2. bug_report 产物类型 (S7-004 新增, 单点扩展):
     ArtifactType +BUG_REPORT ("bug_report") + CONTRACTS 表 + 条目
     (position/reproduce/expected/actual — 架构 §4 结构化缺陷报告)
   S7-002 已预留: "新增产物类型 = 枚举加成员 + 表加条目单点扩展"
3. Dev↔Tester Loop 表达为 Stage DAG + 重试路径:
     dev stage → tester stage (depends_on); tester 失败 → bug_report 产物
     → 人工/编排介入 (reset failed stage + paused→active, S7-003 已支持)
     → dev 修 → tester 再测; Loop ≤2 轮 = 重试上限计数 (架构 §4, 防无限)
4. 复用: 验证循环 L1-L4 + AgentRuntime (exec validation) + FailureReason bug
   分类 + 沙箱; 真实执行经 _build_workflow_runner 注入点 (CLI run /
   S7-005 编排壳统一接入, 不重写执行链)
5. 验收映射: 输入 Developer Artifact (code, VALIDATED) → Tester 执行 →
   测试通过 (test 产物 bugs=[]) → 全链 COMPLETED; 失败 → bug_report 回传
   → 修复 → 再测 ≤2 轮
```

## 下一步

```text
S7-004 Tester Agent executable (Dev↔Tester Loop, 经 executor 注入点接入本引擎)
S7-005 Workflow Engine 接真实 Role Executor (EmployeeExecutor 适配器, 编排壳
     升级为真实执行; 本 S7-003 已提供完整契约/注入点/事件审计底座)
```

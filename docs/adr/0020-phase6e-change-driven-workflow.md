# ADR-0020 — Phase 6E: Change Driven Workflow (变更驱动工作流层)

> 日期: 2026-08-06 | 状态: Accepted

## 背景

Phase 6E 给 Factory 加 **Change Driven Workflow 层**: `factory-core/changeflow/`
六件套 (models/rules/triggers/events/engine/`__init__`) + CLI `change triggers/
evaluate/workflows` + Dashboard Change Flow View (第 16 视图) + change.trigger.* /
change.workflow.* 审计事件。设计文档 phase6e-status.md 明令 **复用不复制**:
只组装既有 WorkflowEngine / WorkflowStore / OrchestrationPipeline, 不修改
workflows/execution/orchestration 核心, 且 **失败恢复不级联** (evaluate 永不抛)。

接续 Phase 6D Change Intelligence 层 (ADR-0019): 规则输入 = ChangeService
(L4 判定 / 关联提交 / 变更文件), 触发器命中 → 4 规则评估 → PASS 则启动
target_workflow 运行实例并 (可选) 执行 — 形成 "提交即发布" 的链式交付。

本 ADR 界定 changeflow 层边界、evaluate 执行契约与失败安全语义, 并记录
Phase 6E 收尾 10 个失败测试的契约裁定 (2155 → 2159 全绿)。

## 决策

### 1. 触发器声明式注册 (只落盘, 不校验目标)

- `ChangeTrigger` (id / event_type / project_id / task_type /
  required_validation / target_workflow): event_type 受控词汇
  (`workflow.completed` 等, 非法值回落缺省), project_id / task_type 为
  可选限定 (None = 任意), required_validation 默认 PASS。
- `ChangeTriggerRegistry` 持久化 `<root>/changeflow/triggers.json` (JSON
  列表, 原子写 tmp+os.replace); 冲突 id → `ChangeTriggerExistsError`
  (CLI 退出码 1); 文件缺失/损坏 → 空列表 (失败安全)。
- **目标工作流存在性在 evaluate 触发时校验**, 注册只落盘 (KISS):
  声明式驱动规则与既有 `workflow add` 解耦, 先注册触发器后补工作流合法。

### 2. 复用不复制: 触发 = WorkflowEngine 状态机 + OrchestrationPipeline 执行

- run 创建 = `WorkflowRun.from_workflow` + `WorkflowStore.save_run` +
  `WorkflowStore.next_run_id`; 状态推进 CREATED→RUNNING、第一步
  PENDING→RUNNING 的合法性经 `WorkflowEngine.is_valid_run_transition` /
  `is_valid_step_transition` (**公开 API**, 不触碰 workflows/ 内部)。
- 执行 = **executor 注入**: CLI 装配 `orchestration.pipeline.execute_workflow`
  部分应用; run 已 RUNNING → OrchestrationEngine._ensure_run 走续跑分支
  (不读 task.workflow), 天然支持 **target != task.workflow** 的链式交付。
- 规则输入 = ChangeService.validate / analyze / parse_commits (Phase 6D),
  不复制 L4 判定逻辑; runtime 规则④输入 = RuntimeRegistry AVAILABLE 集合。

### 3. evaluate 执行契约 (execute 三态, 收尾裁定)

`ChangeWorkflowEngine.evaluate(task_id, trigger=None, *, execute=None)`:

- `execute=None` (缺省): **装配了 executor 才触发** (CLI `change evaluate`
  装配 → 默认执行; 库内零装配引擎 → 只评估不触发, 纯评估语义)。
- `execute=True`: **强制触发** (无 executor 时启动 run 但不执行 — 触发与
  执行解耦; 测试注入 no-op 场景契约)。
- `execute=False`: **纯评估**, 不触发不启动 run。
- CLI 参数: `change evaluate` 缺省执行 (`--no-execute` 关闭, 见决策 7)。
- 触发成功 → `evaluation.triggered_workflow` / `run_id` 填充 + 事件
  `change.workflow.started`; 装配 executor 时执行终态 → 事件
  `change.workflow.completed` (result=COMPLETED/FAILED, 执行失败只审计,
  评估仍 PASS — 判定与执行解耦)。

### 4. 4 规则评估: 失败安全, SKIP 不误报

- 规则恒定 `RULES = ("validation.l4", "commit.linked", "required.files",
  "runtime.pref")` (顺序即评估顺序, Dashboard/CLI 依赖); 每条为纯函数。
- 输入装配 (build_context) 全部失败安全: ChangeService 异常 → 规则① SKIP /
  证据为空; RuntimeRegistry 异常 → 空集; 缺省字段 = "无证据/未配置" →
  对应规则 SKIP (绝不误报 FAIL)。
- 总判定: 任一 ERROR → ERROR > 任一 FAIL → FAIL > 任一 PASS → PASS >
  全 SKIP → SKIP (同 validation 聚合语义; **全 SKIP = 无匹配证据 → 评估
  SKIP 不触发**, 旧 Task 兼容, 不误报)。
- PASS 且 (execute 生效) → `_launch`: 目标工作流未注册 / 任务已有 run
  (一个 task 至多一个 run, 同 WorkflowEngine 语义) → `ChangeFlowError`。

### 5. 失败恢复不级联: evaluate 永不抛

- 引擎缺 task store / 任务不存在 → ERROR 评估 (含 error 摘要), 事件照发。
- 触发失败 (目标未注册 / 已有 run) → evaluate 捕获 → **ERROR 评估** +
  `triggered_workflow=None`, 不向上传播, 不影响调用方 (CLI 退出码按评估
  状态: PASS/SKIP → 0, FAIL → 3, ERROR → 1)。
- 无匹配触发器 (项目/任务类型维度) → SKIP 评估 (trigger_id=None)。

### 6. workflow_chain 只读查询 (change workflows 数据源)

- 链 = 任务工作流行 (task.workflow → 定义名/运行实例/状态, 无 run →
  NOT_STARTED) + 触发工作流行 (`change.workflow.started` 事件:
  target workflow/run_id/trigger_id/STARTED)。无记录 → []。
- 失败安全: 任务不存在 → 空链; CLI `change workflows` 零执行副作用
  (engine 装配 execute=False, 不装 executor)。

### 7. Dashboard Change Flow View (第 16 视图) + CLI --no-execute (收尾修复)

- `ChangeFlowSnapshot` (trigger_total/triggers/evaluation_total/evaluations/
  workflow_links_total/workflow_links/by_status) + `FactorySnapshot.changeflow`
  默认空; collector `include_changeflow` 缺省关 (同 include_git/change 模式,
  零回归); 数据源 = ChangeTriggerRegistry 快照 + `change.trigger.evaluated` /
  `change.workflow.started|completed` 事件聚合。
- **CLI 实现 bug (收尾修复)**: `change evaluate --execute` 原为
  `action="store_true", default=True` — argparse 下该参数恒 True,
  commands.py 的 `execute = None if args.execute else False` 纯评估分支
  永远不可达。修复 = `--no-execute` (`action="store_false", dest="execute",
  default=True`), 默认执行、显式关闭, 与 README/ADR 契约一致。
- **CLI 实现遗漏 (收尾修复)**: `cmd_dashboard` 只装配了 Phase 6D 的
  change_store/include_change, 未装配 Phase 6E 的 change_trigger_registry /
  include_changeflow — `dashboard --view changeflow` 渲染视图壳但
  Triggers/Evaluations/Links 三表恒空。修复 = 同 change view 模式按
  `view == "changeflow"` 装配 `ChangeTriggerRegistry(<root>/changeflow)` +
  `include_changeflow=True`; dashboard.viewed payload 补 changeflow_triggers /
  changeflow_evaluations / changeflow_links 摘要 (同 6C/6D 先例)。
- VIEWS 精确集合断言随视图扩展数学上必然失败 (15→16), 最小化更新 + 本
  ADR 记录 (第五犯先例, 同 ADR-0014/0017/0018/0019)。

### 8. Phase 6E 收尾修复: 10 个失败测试的契约裁定 (2155 → 2159)

1. **evaluate 缺省执行语义 (测试期望错, 修测试, 9 个)**: 契约 = 缺省
   execute = 装配 executor 才触发 (决策 3)。`TestEvaluateTrigger` 2 个
   (无 executor 期望触发) / `TestLaunchFailures` 3 个 (期望触发失败转
   ERROR) / `TestLaunchRun` 2 个 (期望 run 落盘) / `TestWorkflowChain` 2 个
   (期望 started 事件行) 原以零 executor 引擎调 `evaluate` 期望触发 —
   与新契约矛盾。修复 = 显式 `evaluate(..., execute=True)` (触发与执行
   解耦, 无 executor 时仍启动 run), docstring 同步 "显式 execute=True
   (无 executor) → 触发 run (CREATED→RUNNING) 但不执行"。
2. **RuntimeStore API (测试期望错, 修测试)**: `test_runtime_pref_and_available`
   用 `runtime_store.save(...)` — RuntimeStore 写 API 是 `save_runtime`/
   `save_execution`/`save_result`, 无 `save`。修复 = `save_runtime`; 且
   `RuntimeInfo` 的 `name` 字段必填 (模型校验), 测试数据补
   `name="Echo Runtime"`。

## 验证

- pytest **2159 全绿** (2155 既有 + 10 收尾修复 - 0 删除, 测试只增不减),
  含 tests/changeflow/ 全量 144 (模型/rules/events/engine)、tests/dashboard/
  (Change Flow View)、tests/cli/ (change 命令 + 退出码契约)。
- 冒烟: `factory workflow add release` → `change triggers register`
  (validation PASS→release) → `task create MP-BUG-001` → `change validate`
  PASS → `change evaluate` (PASS, 触发 release run) → `change workflows`
  (链含任务行 + 触发行) → `dashboard --view changeflow` (三表渲染) 正常;
  `change evaluate --no-execute` 只评估不触发。

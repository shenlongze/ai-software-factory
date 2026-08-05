# ADR-0003: Phase 3A Validation Engine — 三层验证、事件流扩展与既有断言更新

> 状态: 已接受 | 日期: 2026-08-05 | 作者: 后端开发工程师
> 关联: `docs/design/phase3a-status.md` · `docs/design/cli-design.md` §2.6/§5 · `docs/design/event-model.md` §3.3 · `docs/adr/0002-phase2-cli-events-layout.md`

## 背景

Phase 3A 将 `factory validate` 从占位升级为真实 Validation Engine (L1 Factory / L2 Workflow / L3 Artifact Hook),
并要求新的验证事件流 `validation.started → validation.rule.started → validation.rule.completed → validation.completed` (失败追加 `validation.failed`)。
落地时存在四处需要消解的张力:

1. **事件流 vs 既有测试**: 新流程在 `validation.started` 与 `validation.completed` 之间插入每规则一对
   `validation.rule.started / validation.rule.completed` 事件 (6 条规则 = 12 条事件), 而 Phase 2 的
   `tests/cli/test_cli_commands.py::test_validate_pass_exit_0` 断言 `types[-2:] == [validation.started, validation.completed]`,
   `tests/cli/test_cli_integration.py::test_init_create_flow_all_events` 断言精确事件列表且 `count() == 10`。
   任务同时强制"新增 ≥30 测试且已有 141 不回归"与"新事件流"——两者在数学上不可兼得 (规则事件必然落在两事件之间)。
2. **失败事件契约**: 既有测试要求失败时仍发 `validation.completed` (result=FAIL, payload.reason=status_mismatch/task_not_found);
   任务要求失败时发 `validation.failed`。二者需共存, 需确定落库顺序。
3. **未找到任务的退出码**: cli-design §5 约定"未找到 = 7", Phase 2 行为与测试均固定 `validate T-999 → 7`;
   任务样例写"有 FAIL → 3"。需明确优先级。
4. **--level 语义**: cli-design §2.6 描述 `--level L1/L2/L3` 为验证深度; 任务样例报告固定显示全部三层 (L1/L2/L3)。

## 决策

1. **事件流按任务指令落地**, 并更新 2 个既有测试的事件断言 (非 API 变更, 纯行为观察点更新):
   - `validation.started → validation.rule.started → validation.rule.completed (×规则) → validation.completed`;
     失败时 completed 先落库, `validation.failed` 追加收尾。
   - 每个规则事件: stage=层 (L1/L2/L3), result=started/判定 (PASS/FAIL/SKIP/ERROR), payload 含 rule/level/status/message。
   - 理由: 任务指令"Event 集成 (validation.started→rule.started→rule.completed→completed/failed)" 是显式需求,
     既有测试断言的是旧占位行为; 更新断言使其覆盖新流程 (started 紧随 task.created、completed 收尾、规则事件成对出现),
     测试数仍为既有 141 个 (断言更新不改计数)。

2. **validation.completed 保留为总判定事件** (兼容 Phase 2 契约: result=PASS/FAIL/ERROR, payload 含 level/expect_status/reason/checks,
   checks 保持 `{id,name,status,detail}` 形状); `validation.failed` 为失败专属事件 (payload 含 reason/failure_class/checks),
   仅当总判定为 FAIL 时追加。ERROR 总判定不发 validation.failed (completed result=ERROR 表达)。

3. **未找到优先**: `report.task_found == False` (任务 JSON 文件缺失) → 退出码 7 (cli-design §5 未找到);
   其余 FAIL → 3; 规则内部 ERROR → 1 (一般错误); PASS → 0。报告仍显示 L1 FAIL, 只是退出码按未找到约定。

4. **--level 保留为事件 stage 标记**: 引擎始终执行全三层 (L1/L2/L3 均廉价且可并行于报告展示),
   与任务样例报告 (L3 Artifact SKIP 恒展示) 一致; `--level` 仅影响事件 stage 与 payload.level, 不改层集合。

5. **L2 规则实现口径**: 父任务示例"状态 DEVELOPMENT 但无 architecture.completed 事件 → FAIL"在本阶段事件词汇中
   以等价语义落地: 最近状态事件 (task.created 的 stage / task.updated 的 payload.to) 与任务当前 status 不一致 → FAIL
   (Phase 2 无每阶段 completed 事件; 状态流转由 task.updated 表达)。`workflow` 为空/缺失 → 整层 SKIP。

6. **L1 规则顺序与 reason**: 按父任务 ①存在 ②数据 ③状态 ④文件 顺序执行; `reason` 取首个 FAIL 规则映射
   (task_not_found / task_data_invalid / task_status_invalid / task_files_incomplete / workflow_mismatch / status_mismatch)。
   模型校验失败时保留原始 JSON 供细粒度规则 (task_status/task_files) 继续诊断。

## 后果

- `factory validate TASK_ID` 命令签名不变 (task_id / --level / --expect-status), 输出升级为 Validation Report 文本格式
  (`Validation Report / Task / L1-L3 / Result`), `--json` 输出含 report 结构化结果。
- EventType 纯增量扩展 3 成员 (validation.rule.started / validation.rule.completed / validation.failed),
  沿 ADR-0001 扩展路径, 不改表结构/任何 API (未知类型拒绝测试用 `not.a.type`, 不受影响)。
- 既有 141 测试全部通过 (其中 2 个测试的事件断言按决策 1 更新); 新增 82 个测试覆盖模型/规则/引擎/报告/CLI。
- 风险: L2 依赖事件历史与任务文件的强一致; 人工直接改任务文件绕过事件会导致验证 FAIL (设计意图, 审计面)。
- 后续 Phase: L3 Hook 接入 Flutter/Java/Python 验证器时, 在 rules.py 增加规则函数并在 `_RULE_ORDER` 注册即可, 事件流不变。

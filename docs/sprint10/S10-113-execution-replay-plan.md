# S10-113 — M5-1 执行重放引擎：实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-25 | 前置: v1.1.81 · M3 7/7 · P0-10/11 ✅
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 架构设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-113 提示词（M5-1, §5.6.3 L3/L4）

---

## 0. 现状审计（CTO 独立复核）

| 项 | 现状 |
|---|---|
| execution_records.json | workspace/exec/execution_records.json; 字段: intent/action/agent/task/result/result_id/timestamp/error — **缺 input_snapshot (params 未录)** → 旧记录无法 re-exec |
| audit 事件 | TASK_STARTED/COMPLETED/FAILED 等 (EVENT_TYPES 63) — 时间线可重建 |
| 沙箱 | factory-exec/exec/sandbox.py: create/diff/change_summary/export_patch/apply_patch + _git() — L4 快照回滚可复用 (export_patch 快照 + 反向 apply 回滚) |
| 入口 | commands.py BoardCommand (子命令: graph/chain/timeline/project) — 加 replay 子命令; 自然语言意图规则 (intent.py) |
| 待办清单 | M5-1 行存在 (L51) |
| 版本 | 1.1.81 → 目标 1.1.82 |

## 1. 架构决策

### 1.1 新模块 `factory-console/session/execution_replay.py`

```python
class ReplayEngine:
    def __init__(self, workspace: Path, records_file: Optional[Path] = None): ...

    # 1. dry-run: 读 records + audit 事件 → 按时间线重建单次执行
    def dry_run(self, exec_id: str) -> ReplayTimeline
        # 无效 id → ReplayError("执行记录不存在: {id}") 明确错误
        # 时间线: 合并 records (intent/action/agent/task/result/耗时) + audit 事件
        #   (TASK_STARTED/COMPLETED/FAILED 细化步骤) — 按 timestamp 排序
        # 耗时: 相邻时间戳差 (真实计算, 非占位)

    # 2. re-exec: 从记录取 input_snapshot → 同输入重跑 → 新 exec_id 记录
    def re_exec(self, exec_id: str, runner: Callable) -> str
        # input_snapshot 缺失 (旧记录) → ReplayError("旧记录无输入快照, 无法重跑 — 请确认记录版本")
        #   如实报告, 不瞎跑
        # 成功 → 新 exec_id + 记录 (含 input_snapshot, 可对比)

    # 3. 对比: 两次执行 diff → markdown 报告
    def compare(self, exec_id1: str, exec_id2: str, save_to: Optional[Path] = None) -> str
        # diff: 步骤差异 / 结果差异 (success vs failed) / 耗时 / 产物差异 — 真实 diff, 非"看起来一样"
        # save_to → 写 markdown (docs/sprint10/replay-compare-<id1>-<id2>.md)

    # 4. L4 快照回滚 (可选, 简单则做)
    def snapshot_before(self, exec_id: str) -> str  # sandbox.export_patch → 存记录 pre_snapshot
    def rollback(self, exec_id: str) -> None         # 反向 apply_patch → 回滚到执行前
```

### 1.2 记录完善（重放数据源保证）

- `execute_task` (actions.py): record 增加 `input_snapshot` = {intent, action, params (objective 等全部可序列化参数), context 摘要}
- 新执行记录含 input_snapshot → 未来可重放 (验收 4)
- 旧记录无 input_snapshot → re-exec 明确错误 (诚实纪律)

### 1.3 入口

- `/board replay <exec_id>` — 默认 dry-run; flags: `--re-exec` / `--compare <exec2_id>` (缺省对比最近一次) / `--save` (对比报告落盘 docs/sprint10/)
- 自然语言 "重跑 <exec_id>" → intent.py 规则 (replay_exec) → router → replay action
- 命令层最小: 只加 replay 子命令 + 入口, 不动 board 渲染

### 1.4 L4 快照回滚（可选）

- 若实现简单: 执行前 `sandbox.export_patch` 快照入记录 → 失败后 rollback 反向 apply
- 不做则如实标注 "L4 未做, 待后续" (验收 6 部分完成标注)

## 2. 契约测试（tests/console/test_s10_113_execution_replay.py, ≥6）

1. **dry-run 真实重建**: 造 3 条记录 (含 audit 事件) → ReplayEngine.dry_run 输出含步骤/agent/结果/耗时; 无效 id → 明确错误
2. **re-exec 同输入重跑**: 有 input_snapshot → 重跑 → 新 exec_id + 新记录 (可对比)
3. **re-exec 缺快照**: 旧记录无 input_snapshot → 明确错误不瞎跑
4. **对比报告**: 两次执行 diff (结果/耗时/步骤数差异); --save 落盘文件存在且含真实 diff
5. **记录完善**: 新 execute_task 记录含 input_snapshot (可还原输入)
6. **入口**: /board replay (dry-run/--re-exec/--compare) + 自然语言 "重跑 <id>" → 意图路由
7. L4 (若做): snapshot → rollback 恢复执行前状态

## 3. 版本与发布

- pyproject `1.1.81` → `1.1.82`; CHANGELOG v1.1.82; 版本断言同步; docs/FEATURES.md (头版本 + M5-1 行);
  docs/sprint10/待办清单-已发现未落地.md L51 M5-1 标 ✅ (L4 未做 → 如实标注部分完成)

## 4. Codex 实施范围

**Allowed/Files**:
- NEW `factory-console/session/execution_replay.py`
- MOD `factory-console/session/actions.py` (execute_task 记录 + input_snapshot; 只加字段, 不改执行链)
- MOD `factory-console/session/commands.py` (BoardCommand replay 子命令)
- MOD `factory-console/session/intent.py` + `router.py` (replay_exec 意图 — 纯新增)
- MOD `factory-exec/exec/sandbox.py` (若做 L4: snapshot/rollback 方法)
- NEW `tests/console/test_s10_113_execution_replay.py`
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / docs/FEATURES.md / docs/sprint10/待办清单-已发现未落地.md

**Forbidden（硬边界）**:
- 不改调度器/M3a-d、执行引擎核心逻辑 (execute_task 内部逐字节 — 只在记录处加字段)、board 渲染、产品管线、ChangeControl
- 不做并行线程化 / RAG / 消息平台
- 禁 git add -A; 禁新增第三方依赖
- 禁 stub/fake: dry-run/re-exec 必须真实重建/重跑; 对比必须真实 diff; 缺快照如实报错

**Validation**:
- `pytest tests/console/test_s10_113_execution_replay.py -q` 全绿
- env -u 聚焦 (actions/commands/intent/router + 既有执行测试) 全绿
- env -u 全量 console+api 0 新增失败
- 实测: 真实 exec_id dry-run 时间线; re-exec 新记录; compare diff + --save; 缺快照明确错误
- commit: `feat(S10-113): M5-1 执行重放引擎 — dry-run/re-exec/对比报告 + input_snapshot 记录完善, v1.1.82`

## 5. 边界（不做）

- 执行引擎核心逻辑不改; L4 快照回滚可选 (做/不做如实报告)
- 旧记录 re-exec 不可用 (无 input_snapshot) — 如实报告, 新记录起可重放

## 6. 验收标准（Hermes 独立验证）

- [ ] dry-run: 真实 exec_id 重建时间线 (步骤/agent/结果/耗时可读); 无效 id → 明确错误
- [ ] re-exec: 同输入重跑 → 新记录; 输入缺失 → 明确错误不瞎跑
- [ ] 对比报告: 两次执行 diff (结果/耗时/步骤数); --save 落盘
- [ ] 记录完善: 新执行记录含 input_snapshot
- [ ] 全量回归 0 新增失败 · v1.1.82
- [ ] 待办清单 M5-1 ✅ (L4 未做 → 如实标注部分完成)

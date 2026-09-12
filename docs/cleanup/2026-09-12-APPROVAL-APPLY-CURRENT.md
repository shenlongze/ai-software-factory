# APPROVAL-APPLY 真相（步骤 2.1，只读）

> 日期: 2026-09-12 | 性质: **只读**（未改任何文件）
> 目的: 切 apply 前的真相摸底

## ① apply 具体做什么

**入口**：`factory-exec/exec/approval.py:166 ApprovalGate.apply(approval_id, target_dir)`

**流程**：
1. `store.get_approval(id)` → 不存在 → `ApprovalError`
2. 校验 `decision == approved`（否则硬拒绝："patch apply requires approved"）
3. 校验 `not applied`（否则 "patch already applied"）
4. `store.get_result_by_request(request_id)` → 取 ExecutionResult
5. `_patch_artifact_path(result)` → 取 PATCH artifact 的 `path`
6. `target.is_dir()` 校验
7. **`self._git_apply(target, patch_path)`** ← 见下
8. `model_copy(applied=True, applied_at=utcnow())` → `store.save_approval`
9. `exec_events.record_execution_applied(...)`（审计）
10. 返回 `(updated_record, patch_text)`

**改哪些文件/目录**：**真实 target 项目目录**（`--project` 或 request.input.project_dir）
**跑哪些 git 命令**（`_git_apply:218`）：
```
git -C <target> rev-parse --git-dir     # 检查是 git 仓库（非 git → 硬拒绝）
git -C <target> apply <patch_path>      # 直接应用补丁到真实仓库
```
**删除操作**：无（不 delete；但 patch 本身可含删除 hunk）
**仓库状态变化**：target 的 **working tree 被修改**（未 commit、未 add、未 push）；approval 记录 `applied=True`

## ② 上一轮"6 failed"的确切根因

**失败测试**（6 个）：
- `tests/exec/test_approval_decide.py::TestApprovalDecideCLI::{test_decide_approve_reuses_gate, test_decide_reject}`
- `tests/console/test_approval_apply.py::TestApprovalApplyCLI::{test_apply_success_applies_patch, test_apply_without_project_uses_request_dir, test_duplicate_apply_rejected}`（+1）

**确切根因（状态污染 + 逻辑不一致，非断言错误）**：
1. 当时 `_approval_via_runtime` **含 apply 分支**，调用新实现 `gate.apply()`
2. 新实现 `gate.apply()` **不做真 git apply**，只**标记 `applied=True` 并写入 `approvals.json`**
3. 返回格式为 `{"ok":True, "approval_id":..., "applied_at":...}` —— **缺 `approval` 字段**
4. CLI `_print_approval_result` 访问 `result["approval"]` → **KeyError** → 异常
5. 异常触发 **fallback 旧实现** → 旧实现读到第 2 步写下的 `applied=True` → **报 `patch already applied: APR-xxx (applied_at=...)`** → `rc=1`
6. 测试断言 `rc == 0` → **AssertionError**

**证据（失败栈）**：
```
error: patch already applied: APR-e77a1a8c (applied_at=2026-09-12T04:22:36.000746+00:00)
tests/console/test_approval_apply.py:132: assert rc == 0  →  assert 1 == 0
```
**性质**：**状态污染**（新实现半成品污染了 `applied` 标志）+ **逻辑不一致**（返回结构不符）→ 不是断言本身错。

## ③ apply 有没有事务性

**无事务、无回滚**：
- `git apply` 失败 → 抛 `ApprovalError`（失败响亮），但**已应用的 hunk 不回滚**
- `applied=True` 在 git apply **成功之后**才写（顺序正确，但 git apply 部分失败时状态不一致）

**沙箱机制存在，但 apply 不用它**：
- `factory-exec/exec/sandbox.py:75 class Sandbox`（"项目副本沙箱：创建 → 修改 → diff → patch 导出"）
- **apply 完全绕过 Sandbox，直接对真实 target 执行 `git apply`**

## ④ 数据存储写哪些文件

| 文件 | 内容 |
|------|------|
| `<data_dir>/exec/approvals.json` | `applied=True` / `applied_at` |
| `<data_dir>/factory.db`（EventStore） | 审计事件 `org.execution.applied`（经 `record_execution_applied`） |
| **target 项目目录** | **真实文件修改**（patch 落地） |

## ⑤ 谁调用 apply

- **CLI**：`cli_factory.approval()` → `exec_cli.cmd_exec_approval_apply`（`exec/cli.py:387`）
- 其他：`release_truth.py` / `session/workloads/backlog_sweeper.py` **读** approval 数据（不调 apply）
- 测试：`tests/console/test_approval_apply.py` · `tests/exec/*`

---

# ⛔ HARD STOP 触发

**触发条款**："若旧实现的 apply 直接改真实仓库（无沙箱概念）→ 停，汇报"

**确认结果**：**旧实现确实直接改真实仓库**（`git -C <target> apply`），**完全无沙箱、无事务**。

**含义（需你裁决）**：
- apply 的**功能语义就是"把批准的 patch 应用到用户真实项目"**——用沙箱副本就**无法真正应用**（沙箱内改动不落用户仓库）
- 因此"新实现用沙箱"与"apply 的用途"**直接冲突**：沙箱版 apply **不具备等价能力**
- 你的 2.2 铁律要求"git 写入必须在沙箱副本上"——这与旧实现语义**不可调和**

**三个选项（请你裁决）：**
- **A. 保留真实写入，不套沙箱**（新实现照旧 `git apply` 到 target，但**加事务性**：apply 前 `git stash`/记录，失败回滚）
- **B. apply 不绞杀**（承认 apply 是"写入用户环境"的特权操作，保持旧实现；绞杀范围止于 list+decide）
- **C. 其他**（如 apply 改为"导出 patch 供人工应用"，但那改变了产品语义）

**当前停下，未写任何 apply 新代码**（按你的 §6："2.1 文档未出就写代码 → 停"，现文档已出，但 ② / HARD STOP 已触发）。

# APPROVAL 现状（S1.1 只读摸底）

> 日期: 2026-09-12 | 性质: **只读**（未改任何文件）
> 目的: 绞杀者模式第一刀 — 摸清 `factory approval` 全链

## 1. CLI 入口

| 层 | 文件:行 | 函数 |
|----|---------|------|
| 分发 | `factory-console/cli_factory.py:994` | `if args.command == "approval": self.approval(args)` |
| 实现 | `factory-console/cli_factory.py:1981` | `FactoryCLI.approval()` — list/decide/apply |
| 委托 | `factory-console/cli_factory.py:1989` | `exec_cli = self._proxy_exec_cli()` → factory-exec |
| 实际执行 | `factory-exec/exec/cli.py:377/382/387/431` | `cmd_exec_approval_approve/deny/apply/list` |

## 2. 调用链（factory-core 侧涉及几个模块）

```
cli_factory.approval()
  → exec.cli.cmd_exec_approval_*        [factory-exec]
    → exec.approval.ApprovalGate        [factory-exec/exec/approval.py:65]
      → exec.store.ExecStore            [factory-exec/exec/store.py]
        → events.logger.EventLogger     [factory-core] ← ①
        → events.models.EventType       [factory-core] ← ②
        → events.store.EventStore       [factory-core] ← ③
```

**factory-core 侧涉及 = 3 个模块**（events.logger / events.models / events.store）
→ **未超 HARD STOP 阈值 5** ✅

> 注：`factory approval` 消费方列表里另有 governance_service / fastapi / api/approvals 等，但**不属于本 CLI 链**（见 §4）。

## 3. 数据存储

| 存储 | 位置 | 写入方 | 说明 |
|------|------|--------|------|
| **ExecStore（本链）** | `<data_dir>/exec/` | `exec.store.ExecStore.save_approval` | **ApprovalGate 用这个** |
| governance | `<root>/governance/approvals.json` | `governance_service.py:82` | 另一体系（release 审批） |
| session | `<data_dir>/session_approvals/<sid>.json` | `session/approval_store.py:29` | bash 写操作门（第三套） |
| ops 投影 | `<root>/ops/governance/approvals.json` | `control_tower.py:91` | 只读投影 |

**本链存储 = `ExecStore`（`exec/` 目录）**，记录结构由 `ApprovalRecord` 定义。

## 4. 消费方（谁读这个数据）

| 消费方 | 文件 | 备注 |
|--------|------|------|
| CLI | `cli_factory.py` | 本链（入口） |
| Web | `web/backend/fastapi_adapter.py:7501+` | 经 `session.approval_store`（**不同体系**） |
| API | `api/approvals.py` | 经 org approval（**不同体系**） |
| 发布 | `release_truth.py` | 读 approval 做门 |
| 清单 | `session/workloads/backlog_sweeper.py` | 读待办 |
| 存储 | `exec/store.py` / `exec/__init__.py` | 定义方 |

> ⚠️ 多套并存：**本刀只绞 `ExecStore` 这一条 CLI 链**，不碰 governance/session 两套。

## 5. 测试覆盖

- **直接覆盖本链**：`tests/exec/test_exec_approval.py` · `tests/exec/test_approval_decide.py` · `tests/exec/test_exec_cli.py` · `tests/exec/test_exec_store.py`
- 相关：`tests/s9/test_s9_approval_{cli,lifecycle,store,model,events}.py` · `tests/product/test_product_approval_queue_9c.py` · `tests/product/test_product_service_approval.py`
- 全仓提及 "approval" 的 test 文件 **99 个**（多数为词匹配，非本链）

## 6. 决策方式

**硬编码规则**（无 LLM/Prompt）：
```python
# factory-exec/exec/approval.py:44
def classify_risk(patch_text, *, changed_files=1) -> tuple[str, list[str]]:
    if changed_files >= 3:        → "high"
    if changed_files >= 2 or "config" in text[:2000].lower():  → "medium"
    else:                          → "low"
```
+ 敏感文件 pattern（`requirements.txt|pyproject.toml|package.json`）

## 7. 绞杀可行性结论

| 判据 | 结果 |
|------|------|
| factory-core 涉及模块 | 3（< 5）✅ |
| 是否需改存储格式 | 否（沿用 `ExecStore` 的 approval 部分）✅ |
| 链路清晰度 | 高（ApprovalGate 单一类，方法：list/apply/decide + risk 分类） |
| 风险 | 中低（消费方多，但本刀只切 CLI 一条线） |

**结论：approval 适合作为绞杀第一刀** ✅

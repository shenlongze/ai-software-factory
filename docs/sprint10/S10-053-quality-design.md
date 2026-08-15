# S10-053 — Quality & Repair Loop 设计

> 日期:2026-08-15 | Sprint: S10-053 | Phase 0 分析 + Phase 1-8 设计

---

## 1. Phase 0 — 内部分析

### 复用点(S10-052)
```
orchestrator.py   ExecutionOrchestrator (execute_project → _run_queue → _set_lifecycle)
pipeline.py       Lifecycle (DEVELOPMENT/TESTING/DELIVERED + next_status)
actions.py        execute_project / project_progress / execute_task
audit.py          record_execution
```

### 当前缺口
```
G1: 无 ValidationResult / Validator (任务完成 → 直接下一任务, 无质量门)
G2: Lifecycle 无 VALIDATION_PASS (TESTING → DELIVERED 无校验)
G3: 无 RepairManager / repair_task.json (失败无修复循环)
G4: 无 repair_task Action (手动触发修复)
G5: 无 Reviewer 接口 (未来 Reviewer Agent 预留)
G6: project_progress 无 validation/repair 信息
```

### S10-053 最小范围
```
P0: ValidationResult + Validator (mock/command 接口, 不绑语言)
P1: Lifecycle VALIDATION_PASS 门 (无 success 禁止 DELIVERED)
P2: RepairManager + repair_task.json + Retry Policy (max_retry=1)
P3: repair_task Action (确认门)
P4: Orchestrator 集成 (execute → validate → repair)
P5: Reviewer 基础接口 (ReviewResult)
P6: project_progress 增强 (validation/repair)
```

---

## 2. Quality Loop 架构

```
Task → Agent Execution (execute_task, S10-049)
    ↓
Validation (Validator)
    ├─ PASS → 下一任务 → 全部完成 → TESTING → VALIDATION_PASS → DELIVERED
    └─ FAIL → RepairManager
                ├─ repair_task.json (original_task/failure_reason/retry_count/status)
                ├─ 手动/自动 → Agent Retry (repair_task Action, 确认门)
                └─ Validation 重跑
                     ├─ PASS → completed
                     └─ FAIL → failed (max_retry=1, 不无限循环)
```

## 3. Validation System

### ValidationResult
```python
@dataclass
class ValidationResult:
    success: bool
    tests_total: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    errors: list[str] = field(default_factory=list)
    timestamp: str = ""
    def to_dict() -> dict  # 落盘 validation_result.json
```

### Validator(不绑语言, 第一版最小)
```python
class Validator:
    """输入 Task Result → 执行 validation → ValidationResult。"""
    def validate(self, task: dict, task_result: dict, *, command: str | None = None) -> ValidationResult:
        # 1. mock validator (默认): 检查 task_result.success + artifact 存在 → PASS
        # 2. command validator (可选): 执行 command (pytest/flutter test/npm test 未来)
        #    - 未来: command 在沙箱内执行, 解析退出码/输出
        # 第一版: mock 为主, command 接口定义
```

## 4. Lifecycle Gate

```
DEVELOPMENT → TESTING (全部任务完成)
→ VALIDATION_PASS (全部 ValidationResult.success)   ← 新增
→ DELIVERED (仅 VALIDATION_PASS 可进入)

规则: 无 ValidationResult.success → 禁止 DELIVERED (停留在 TESTING/DEVELOPMENT)
```

## 5. Repair Flow

### RepairManager
```python
class RepairManager:
    def create_repair(self, project_dir, original_task, failure_reason, retry_count=0) -> dict:
        # repair_task.json: {original_task, failure_reason, retry_count, status: pending}
    def repair(self, project_dir, *, execute_fn=None, validator=None) -> RepairResult:
        # pending repair → Agent Retry (execute_fn) → Validation 重跑
        # PASS → status completed + 更新 execution_state
        # FAIL → retry_count+1, max_retry=1 → failed (不无限循环)
```

### Retry Policy
```
任务状态: failed → repair_pending → retrying → completed/failed
max_retry=1: 首次失败 → 1 次修复重试; 仍失败 → failed (终止)
禁止无限循环
```

## 6. Action 注册

```
repair_task (sensitive=True, category="execution")
  — "修复失败任务/修复任务" → 确认门 → RepairManager
```

## 7. Reviewer 基础接口

```python
@dataclass
class ReviewResult:
    approved: bool
    comments: list[str] = field(default_factory=list)

class Reviewer(ABC):
    def review(self, task: dict, result: dict, validation: ValidationResult) -> ReviewResult: ...
    # 未来: Reviewer Agent (LLM) 实现; 第一版仅接口
```

## 8. Orchestrator 集成

```
_run_queue 每任务:
  outcome = execute_fn(task)          # Agent Execution
  validation = validator.validate(...)  # Validation (新增)
  if validation.success:
      task → completed
  else:
      RepairManager.create_repair(...)  # Repair Task
      (repair 由 repair_task Action 手动触发, 或 resume 自动)
全部完成 → _set_lifecycle(TESTING) → 全部 validation success → VALIDATION_PASS → DELIVERED
```

## 9. Progress Enhancement

```
project_progress 增加:
  validation: passed/failed/not_run
  repair: repair_pending/repair_done/repair_failed
```

## 10. 架构符合性

| 原则 | 符合 |
|---|---|
| 复用 Agent Runtime | ✅ execute_task/execute_fn 薄调 |
| 最小正确方案 | ✅ mock validator + command 接口 |
| 质量结果资产化 | ✅ validation_result.json + repair_task.json 落盘 |
| 不无限循环 | ✅ max_retry=1 |
| 长期方向 | ✅ Plan→Build→Test→Review→Repair→Deliver |

---

## 11. 文件计划

```
factory-console/session/
  quality.py        (新增: ValidationResult/Validator/ReviewResult/Reviewer/RepairManager)
  orchestrator.py   (修改: 集成 validate + repair + VALIDATION_PASS)
  pipeline.py       (修改: Lifecycle + VALIDATION_PASS)
  actions.py        (修改: +repair_task, project_progress 增强)
  intent.py         (修改: +repair_task 关键词)
  router.py         (修改: 映射)
tests/console/
  test_session_quality.py (新增, >=80 测试)
docs/sprint10/S10-053-quality-repair-loop.md (Phase 11)
```

> Phase 1-8 设计完毕 | Validator + Gate + Repair + Retry + Reviewer 接口 | 复用 execute_fn | max_retry=1

# S12 Autonomous Repair E2E — 真实失败→自动修复→PASS 证据

> 日期: 2026-08-29 | 执行: run_professional_workflow(max_repair=2) + CONTROLLED failure injection
> 真实外部依赖: DeepSeek LLM (PM/Arch/QA) + Codex 0.147 (Developer/Repair) + 真实 pytest

## Environment
| 项 | 值 |
|----|-----|
| version | v1.1.318 |
| provider | deepseek (deepseek-v4-pro) |
| Codex | codex-cli 0.147.0 |
| Python | 3.12.13 |
| pytest | 项目 venv (sys.executable) |

## Initial Production
- production_run_id: 每 Agent 独立 (4 个 ProductionRun)
- agent_run_ids: pm/arch/dev/qa 各 1
- artifact_ids: 4 阶段各 1
- handoff_ids: 3

## Failure (CONTROLLED)
```
failure_type = CONTROLLED (Developer 注入: add 用减号, divide 不处理除零)
pytest #1 (attempt 1): exit_code=1, 真实 subprocess FAIL
```

## Repair (AUTOMATIC)
```
repair_trigger = 自动 (NodeRun verification FAIL → repair_fn, 无人工介入)
repair_input = failed Artifact (payload.content) + pytest failure evidence (stdout/stderr)
repair_engine = 真实 Codex
repair_output = 新 Artifact (attempt 2)
```

## Re-test
```
pytest #2 (attempt 2, repair 后): exit_code=0, 真实 PASS
```

## NodeRun Attempts (developer)
```
attempt 1: VERIFIED FAIL  (bad code)
attempt 2: VERIFIED PASS  (repaired code)
```

## Final Artifact (developer)
```python
def add(a, b):
    return a + b
def subtract(a, b):
    return a - b
def multiply(a, b):
    return a * b
def divide(a, b):
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b
```
Final pytest: PASS (exit=0) — 除零保护由 Repair 自动加入。

## 判定
**S12 REAL E2E: PASS** — 真实 pytest FAIL → 自动 repair(消费 failure evidence)→ 新 Artifact → 真实 pytest PASS → 全链 COMPLETED。

# S12 Gap Analysis — Autonomous Failure Recovery & Repair Loop

> 日期: 2026-08-29 | HEAD: 3e24c45f (v1.1.317)

## Existing (REAL)
| 机制 | 位置 | 状态 |
|------|------|------|
| Repair Loop (max_attempts + repair_fn) | node_runtime.execute_node_run (S5) | REAL |
| Artifact 不可变 + lineage | artifact_lifecycle (S1) | REAL |
| Verification (pytest subprocess) | verification.py (S5) | REAL |
| Failure propagation | production_run (S3) | REAL |
| Recovery/Resume | recovery.py (S7) | REAL |

## GAP (S12 修复)
| GAP | 影响 |
|-----|------|
| **repair_fn/max_attempts 未透传到 agent_kernel.run_agent** | 真实链 pytest FAIL 只 FAILED, 不自动修复 |
| **execute_production_run 未透传 repair 配置** | 同上 |
| Developer 无内置 pytest 验证 | 代码错误要等 QA 才暴露, 无法在 Developer 内自愈 |

## Minimum Changes
1. agent_kernel.run_agent + production_run.execute_production_run 透传 max_attempts/repair_fn
2. professional_workflow: Developer executor 内置真实 pytest 验证 (最小测试集) + repair_fn (真实 codex 修复)
3. run_professional_workflow 接受 repair 配置

## Failure Origin 策略
- NATURAL: codex 自然产出 buggy 代码 (不可控)
- CONTROLLED: 明确标记的 fixture 注入 (可控, 报告区分)
最终 failure 必须经过真实 pytest subprocess。

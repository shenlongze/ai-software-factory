# S11 Gap Analysis — Workforce E2E Production Run

> 日期: 2026-08-29 | HEAD: 6bf6b93d (v1.1.316)

## 现有能力 (REAL)
| 能力 | 接口 | 备注 |
|------|------|------|
| LLM Gateway | llm_gateway.complete(messages, tools, provider, model, api_key) | provider=deepseek, model=deepseek-v4-pro, key 已配 |
| LLM key/provider | workflow_runner.load_llm_key + get_config().get_llm() | REAL |
| Codex executor | external_executor.executor.run(adapter, prompt, project_dir) | codex 0.147 可用 |
| verify_pytest | verification.verify_pytest(workspace) | subprocess pytest, 记录 exit_code/stdout/stderr |
| Professional Workflow | professional_workflow.run_professional_workflow | 4 Agent 链 + Handoff (S10) |
| Repair | node_runtime max_attempts + repair_fn (S5) | 新 Artifact 保证 |

## GAP (S11 修复)
| GAP | 修复 |
|-----|------|
| QA 只 AST 验证, 未接 verify_pytest | QA executor: code+test 写临时目录 → verify_pytest 真实跑 |
| Developer 无真实 codex 路径 | codex executor 生成代码 → payload 保存 content |
| 真实 LLM 全链未跑 | 真实 E2E: PM/Arch LLM + Dev codex + QA pytest |

## 最小修改 (不重构 Production Kernel)
1. professional_workflow: QA executor 支持真实 pytest (临时目录 + verify_pytest)
2. 真实 E2E 入口: run_real_workforce_e2e (LLM/codex/pytest 全真实)
3. 证据文档: s11-real-workforce-e2e.md

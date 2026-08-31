# S30-002 — Execution Model Audit

> 日期: 2026-08-31 | 纯审计

## 一、执行链真实拓扑

```
Entry Points:
  POST /projects/{id}/start       → workflow_runner.start_project_workflow
  trigger_work (conversation)     → create_task → create_production_run
  CLI project/run                 → cli_factory → workforce
  API /api/runtime/execute        → 直接执行

Orchestrator:
  workforce.py (唯一) — 角色定义/权限/create_task

Workflow:
  workflow_runner — 阶段编排 (pm→uxui→architect→developer→tester→release)

Executor:
  professional_workflow — LLM executor factory (每角色 system_prompt + 工具)
  exec/ — 执行器库 (provider/registry)

Node/Run:
  production_run.create_production_run (被 7 处调用)
  node_runtime (NodeRun 实体)

Artifact:
  artifact_lifecycle.create_artifact

Verification:
  verification.py
```

## 二、Run 创建入口分散 (真问题)

| 调用方 | 用途 |
|--------|------|
| conversation_os.trigger_work | 会话触发 |
| adaptive_workforce | 自适应编排 |
| agent_kernel | Agent 内核 |
| effectiveness_service | 效果评估 |
| self_healing | 自愈 |
| production_service | 生产服务 |
| workflow_runner | 项目工作流 |

**7 处直接调 create_production_run — 入口分散, 但都走同一函数 (production_run), 非重复实现。**

## 三、职责判定

| 模块 | 职责 | 判定 |
|------|------|------|
| workflow_runner | 工作流编排 (阶段依赖) | KEEP |
| professional_workflow | 执行器 (LLM/codex) | KEEP |
| workforce.py | 角色/编排 | KEEP 唯一 Orchestrator |
| production_run | Run 实体/生命周期 | KEEP 统一门面 |
| exec/ | Provider/Registry | KEEP |

**无双引擎** — workflow_runner (编排) 与 professional_workflow (执行) 互补。

## 四、结论

- 唯一 Orchestrator: workforce.py ✅
- 唯一 Execution Semantics: 成立 (workflow_runner 编排 + professional_workflow 执行)
- 改进点: Run 创建入口收敛 (非紧急)
- P0-3 缺口: session ↔ run 关联

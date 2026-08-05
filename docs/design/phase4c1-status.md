# AI Software Factory — Phase 4C-1: Hermes Runtime Adapter

> 日期: 2026-08-05
> 前置: Phase 1-4B-3 (824 tests)
> 目标: 真实 RuntimeAdapter — Hermes CLI 子进程调用

## 范围

- factory-core/runtime/adapters/hermes.py — HermesRuntimeAdapter
- execute(request): 构造 Hermes 调用参数 → subprocess → stdout/stderr → ExecutionResult
- 注册 hermes-runtime (type=agent, AVAILABLE)
- 输入输出协议: input (task/step/instruction/agent_id) → output/error/status
- Event 由 Runner 负责 (Adapter 不写 Event)
- 失败处理: 命令不存在/timeout/exit≠0/stdout 空 → FAILED (不抛未处理异常)
- CLI: factory runtime test hermes-runtime (smoke)
- 测试: 新增 ≥50, 824 不回归

## 边界

Factory=Task/Workflow/Assignment/Execution/Validation; Hermes=Agent 执行/Skill/工具
禁止: 修改 Hermes 核心 / Factory 逻辑入 Hermes / LLM API / 多 Agent / 自动生成代码流程

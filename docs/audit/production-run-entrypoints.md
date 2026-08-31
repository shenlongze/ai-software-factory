# Production Run Entrypoints Audit (S30-003)

> 日期: 2026-08-31 | 纯审计

## 7 个 create_production_run 调用方

| Caller | 用途 | 路径 | 类型 |
|--------|------|------|------|
| conversation_os.trigger_work | 会话触发执行 | 对话→任务→run | Production |
| adaptive_workforce | 自适应编排 | 自动排程 | Production |
| agent_kernel | Agent 内核 | 内部执行 | Production |
| effectiveness_service | 效果评估 | 评估 run | Production |
| self_healing | 自愈 | 恢复 run | Production |
| production_service | 生产服务 | API 触发 | Production |
| workflow_runner | 项目工作流 | POST /start | Production |

**结论**: 全部共享同一 `create_production_run` 门面 (production_run.py) — **非重复实现**。
后续 P1 建议: 收敛为单一入口 (facade 已有, 只需统一调用约定)。

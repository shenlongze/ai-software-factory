# Decisions — 决策记录

> ⭐ 实时决策日志 | 新决策追加, 旧决策标注状态 (ACTIVE/SUPERSEDED/DEFERRED)
> 完整 ADR: docs/adr/ (35 份技术决策)

## 待决 (OPEN)

| ID | 决策 | 选项 | 依据 | 决定时间 |
|:-:|:-----|:-----|:-----|:-----|
| D-001 | Ollama qwen3:8b 是否作为生产模型 | DeepSeek (reasoning 瓶颈) vs 本地 | 6.2 Benchmark 数据 | Sprint 6.5 |
| D-002 | Workspace/Organization 泛化时机 | Sprint 7 (连接前) vs Sprint 9 (UI 前) | 依赖顺序 | Sprint 6 后 |
| D-003 | 11 个空目录处置 | 清理 vs 实现 (knowledge/mcp/skills) | 领域规划 | Sprint 10 |

## 已决 (ACTIVE)

| ID | 决策 | 结论 | 日期 |
|:-:|:-----|:-----|:-----|
| D-010 | 审计基线 | Reality Audit v1.0 为状态基准 (docs/audit/) | 2026-08-08 |
| D-011 | 文档体系 | factory-tree/state.json/sprint-board/decisions 实时更新 | 2026-08-08 |
| D-012 | 开发路线 | 先生产 (模型) → 再连接 (组织) → 后领域 (多行业) | 2026-08-08 |
| D-013 | 真实数据原则 | Benchmark 禁 mock 当证明; 失败如实 (已执行 3 轮) | 2026-08-07 |
| D-014 | 模型瓶颈定位 | deepseek-v4-flash reasoning 耗尽 (25/27 空响应) | 2026-08-08 |
| D-015 | Multi Run 保留 | runs=2-3 抗随机性 (Greenfield 2/3 有据) | 2026-08-08 |

## 历史关键决策 (摘要)

```
ADR-0001..0035: 技术决策 (Core 冻结/事件模型/Provider/沙箱/审批/执行...)
架构裁决: Core Command Model / Desktop=入口层 / Runtime=Managed Services
Phase 冻结: Phase A 边界 (1 Agent/1 Provider/1 Sandbox/1 Approval)
```

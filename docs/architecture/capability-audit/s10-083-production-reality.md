> **Documentation Status:** HISTORICAL
>
> This document records the system state/design at the time it was created.
> It is NOT the current system truth.
>
> Current truth: `docs/00-index/CURRENT_SYSTEM_TRUTH.md`
> Frozen contracts: `docs/audit/product-system-baseline/STEP10_DOMAIN_FREEZE.md`

# Production Reality Report — 真实生产闭环审计

> 日期: 2026-08-19 | 首席架构审查 | 仅代码路径 + CLI 实测, 不看设计文档

---

## A. 当前真实能力 ✅

| 能力 | 证据 |
|---|---|
| 想法 → Discovery | 真实 (conversation 多轮字段收集) |
| Product → Project | 真实 (create_product 桥接 create_project, product.json/project.json 落盘) |
| Engineering Plan | 真实 (engineering.json 模块 + tasks.json epics/features/tasks) |
| Agent 分配 | 真实 (execution_plan.json: backend-1, reason="skill match 33% (python), 成功率 78%") |
| LLM 调用 | 真实 (report.md: 1411 tokens, cost 0.000456 USD) |
| patch 生成 | 声称真实 (report.md: "diff lines: 269 (generated from 1 structured operations)") |
| 审计/记忆 | 真实 (事件落盘, 决策链) |
| "继续开发" 路由 | 真实 (resume_project → execute_project → orchestrator → 11 任务"完成") |

## B. 假能力 / 占位能力 ❌ (P0)

| 假能力 | 证据 |
|---|---|
| **任务"完成"但 0 行代码落盘** | 项目目录代码文件数 = 0; execution_state 11 任务 completed + artifact, files=[] |
| **patch 从未应用回项目** | approval.apply(target_dir) 存在但 orchestrator 从不调用; 沙箱副本执行后丢弃 |
| **validation 假 PASS** | "语法检查通过 (0 个 .py 文件)" — 空目录验证无意义 |
| **patch artifact 内容失真** | 部分 patch 是 execution_state.json 自我修改 (状态机自写) |
| **Agent 不产出可交付物** | backend-1 执行 → patch → 副本丢弃 → 无代码 |

## C. 缺失生产链

```
Execute Task → Sandbox(副本) → LLM 生成 patch → 副本内验证
                                                    ↓
                               ★ 断裂: 无 approval.apply 接线
                               patch 存 artifact 后丢弃
                                                    ↓
                               ✗ 真实项目目录永远 0 代码
                               ✗ 无真实测试运行 (仅 syntax check)
                               ✗ 无真实交付物
```

具体缺口:
1. **patch 自动应用缺失**: orchestrator 任务循环从不调用 approval.apply / git apply
2. **沙箱回写缺失**: Sandbox(副本)执行后无 copy-back
3. **验证不真实**: 0 文件项目 "PASS" 是假验证
4. **approval gate 无人触发**: 人工审批流存在但 execute_project 路径不经过

## D. P0 修复建议

1. **执行链落地**: execute_project 任务成功后 → 自动 approval.apply(patch → 项目目录) 或沙箱 copy-back;人工审批可选(高风险才批)
2. **真实验证**: validation 需在**合并后项目**上跑真实 pytest(有文件才有意义);0 文件 → 任务 FAILED 而非 PASS
3. **patch 内容治理**: 排除 execution_state.json 等状态文件进 patch(白名单代码文件)
4. **静默失败消除**: 任务完成条件 = patch 应用成功 + 验证真实通过

## E. 下一 Sprint 建议

**S10-083 = Execution Delivery Closure**(生产链最后一环):
- Sandbox → Project 回写 (自动 apply 或 copy-back)
- 真实代码产物验证 (文件存在 + 真实 pytest)
- 状态机修正 (execution_state 不入 patch)
- 真实 E2E: "继续开发" → 项目目录出现真实 .py 文件 + 测试通过
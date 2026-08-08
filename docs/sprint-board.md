# Sprint Board — 任务计划清单

> ⭐ 实时任务板 | 与 factory-state.json / factory-tree.md 同步
> 规则: 每任务完成 → 更新本板 + state.json + tree → commit

## 当前 Sprint: 6 — DeepSeek 模型档位调优 + 生产闭环

```
目标: 在"仅 DeepSeek"约束下, 用 v4-pro + 现有工程打破"生产 0%"瓶颈
背景: flash 是 reasoning 模型 (25/27 空响应); pro 实测稳定产出 patch (无空内容)
      + 延迟快 2.7×; 当时 diff 失败已被 Operation API/行号/MultiRun 修复
状态: NOT_STARTED | 前置: 审计 ✅ / 文档校准 ✅ / 模型约束确认 (仅 DeepSeek) ✅
```

| # | 任务 | 状态 | 验收 | 依赖 |
|:-:|:-----|:----:|:-----|:-----|
| 6.1 | v4-pro 单样本冒烟 (非空 patch?) | ✅ | 966 chars 非空, 17.3s, $0.0076 |
| 6.2 | v4-pro 真实闭环验证 (6 步) | ✅ | SUCCESS: patch+report+test_result, $0.0046, 经验落库 |
| 6.3 | Employee-Execution 连接 + 多角色 (6 角色) | ✅ | employee_executor + roles.py, 28 测试 |
| 6.4 | flash vs pro 对比 + 验收拆解 | ✅ | production-validation-report.md |
| 6.5 | 9 样本 Benchmark (v4-pro) → 门禁 (Bug Fix ≥60%) | ⬜ | 下一执行 |

## Sprint 7: 组织-执行连接

```
目标: Employee 真正干活 (统一 Agent 模型 + 分配 + 多角色)
```

| # | 任务 | 状态 | 验收 |
|:-:|:-----|:----:|:-----|
| 7.1 | Core Agent 并入 org Employee (统一模型 + model/memory/kpi 字段) | ⬜ | 双模型消除 |
| 7.2 | Employee→Task 分配器 (Registry 推荐→Approval→分配) | ⬜ | 分配闭环 |
| 7.3 | 多角色员工 (product/architect/test/ops 复用 exec 引擎) | ⬜ | ≥3 角色可执行 |

## Sprint 8: 多角色员工 + 业务 Workflow

| # | 任务 | 状态 | 验收 |
|:-:|:-----|:----:|:-----|
| 8.1 | 组织级 Workflow 编排 (目标→部门接力→交付) | ⬜ | 全链演示 |
| 8.2 | 业务流程模板 (内容生产 1 个) | ⬜ | 非软件可跑 |

## Sprint 9: 工作台 UI

| # | 任务 | 状态 | 验收 |
|:-:|:-----|:----:|:-----|
| 9.1 | Workspace Dashboard | ⬜ | 项目/组织/员工/任务 |
| 9.2 | Organization/Employee View | ⬜ | 组织结构可视化 |
| 9.3 | Workflow View + Monitoring | ⬜ | 节点/负责人/ETA/实时 |
| 9.4 | Configuration Center | ⬜ | LLM/Skill/MCP/Knowledge |

## Sprint 10-12: 领域与规模

```
10: Skill/MCP 整合 + Domain Intelligence (造专家工厂)
11: Self Improvement (观察→分析→建议→批准→改进)
12: 多行业工厂 (电商/媒体/数据/办公 6+ 模板)
```

## 历史 (已完成)

```
Sprint 5 ✅ T5.1-T5.5 (Execution Reliability: MultiRun/Evaluator/Capability — 5493)
Sprint 4 ✅ T4.1-T4.5 (Context Intelligence: Ranking/Progressive/Budget/Experience)
Sprint 3 ✅ Context Engine v1 (33.3% 基准, 教训: 上下文不是越多越好)
Phase A+++++++ ✅ Developer 可靠性 (File Operation API/Repo Index/验证循环)
Phase A ✅ Developer Agent MVP (Sandbox/Approval/Experience)
```

## 待决事项 (decisions.md)

```
D-001: Ollama qwen3:8b 是否作为生产模型 (6.2 数据后定)
D-002: Workspace/Organization 泛化时机 (7 前或 9 前)
D-003: 11 个空目录清理或实现
```

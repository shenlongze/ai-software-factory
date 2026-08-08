# Sprint 6 — Production Validation Report（真实生产闭环验证）

> 日期: 2026-08-08 | 状态: 完成 | 首个真实生产闭环 ✅
> 模型: deepseek-v4-pro (仅 DeepSeek 约束) | 项目: /Users/Shared/work/ai-software-factory

## 1. 六步闭环结果（真实执行, 非 mock）

| # | 步骤 | 结果 | 证据 |
|:-:|:-----|:----:|:-----|
| 1 | Task 创建 | ✅ | temp git 项目 + calc.py bug (sum_list 漏 nums[0]) + test_calc.py |
| 2 | Agent 调用 | ✅ | EmployeeExecutor.execute (employee_id=E-1, agent_id=developer-1) |
| 3 | v4-pro 执行 | ✅ | 真实 HTTP 调用: 938 prompt + 230 completion (147 reasoning) tokens |
| 4 | 代码修改生成 | ✅ | 3 artifacts: **patch + test_result + report** |
| 5 | 测试执行 | ✅ | 沙箱内验证循环 (语法+测试); 源项目零修改 (apply 需审批 = 铁律) |
| 6 | Evidence 记录 | ✅ | 事件链 + 10A-4 experience (subject_id=E-1) + 上下文经验落库 |

```
成本: $0.0046 (单任务) | 延迟: ~17s 级 (v4-pro) | 成功率: SUCCESS
对比 flash: 25/27 空响应 (reasoning 耗尽) vs v4-pro 非空稳定输出
```

## 2. v4-pro vs flash（模型档位对比）

| 指标 | v4-flash (瓶颈) | v4-pro (生产候选) |
|:-----|:----:|:----:|
| 空响应率 | 25/27 (reasoning 耗尽) | 0/N (稳定产出) |
| 延迟 | 30-600s | ~17s |
| reasoning | 耗尽输出空间 | 147 tokens 高效 (不耗尽) |
| 单任务成本 | $0.05-0.18 (烧钱不出活) | $0.0046 |
| 代码产出 | 空 | patch + report + test_result |

**结论: v4-pro = 生产模型 (D-001 候选, 6.5 判定)**

## 3. Employee-Execution 连接（实现）

```
Employee (org) → EmployeeExecutor (exec) → AgentRuntime → DeveloperAgent
  → Context/Operation/Sandbox → v4-pro → Patch+Report → Validation
  → Evidence (事件) + Experience (10A-4 + 上下文经验)

employee_executor.py:
  execute(employee, task_id, objective, project_dir, requirement, role_id)
  → ExecutionResult (status/artifacts/usage/employee_id)
  角色匹配 (_role_for_stage) + 能力合并 + 经验装配 (失败安全)

修复: _role_for_stage list_roles 遍历 (原 __import__ 写法 TypeError)
     _build_extractor 路径→store 包装 (原 PosixPath AttributeError)
```

## 4. 多角色模型（统一 Employee 抽象, 不复制 Agent）

```
roles.py: 6 角色注册表 (RoleDefinition = capabilities + prompt 模板 + workflow_stages + execution_kind)
  ProductManager (planning) / UIDesigner (planning) / Architect (planning)
  Developer (executable ✅) / Tester (planning) / DevOps (planning)

诚实标注: 当前仅 Developer 可执行 (executable); 其余 5 角色=planning
  (已定义能力/提示词/阶段映射, 执行能力复用同引擎后续解锁)
Employee 可绑定多角色 (role_ids) + 执行时按角色选 prompt/能力
```

## 5. 验收演示: "开发一个UI功能" 自动拆解

```
Product → Design → Architecture → Development → Testing
  阶段映射 (workflow_stages):
    product → product-manager | design → ui-designer | architecture → architect
    development → developer (可执行) | testing → tester (planning)
  拆解流程: ✅ 可跑 (execute_for_workflow 按阶段匹配角色)
  真实 LLM 执行: 限 development 阶段 (Developer 已验证); 其余阶段 = 规划 (诚实)
```

## 6. 限制（诚实）

```
1. 真实闭环验证了 1 个简单任务 (sum_list); 复杂任务 (markpad 9 样本) 待 Benchmark
2. 其余 5 角色 planning (未执行) — 需后续 Sprint 解锁
3. apply 未演示 (设计: 需 Approval — 沙箱外零修改铁律)
4. 成本估算基于 DeepSeek 端点费率 (v4-pro 定价)
```

## 7. 结论

```
✅ 生产瓶颈打破: v4-pro + 现有工程 = 真实代码产出 (patch/report/test_result)
✅ Employee 真正"干活": 接收任务→调用能力→执行→返回结果→保存经验 全链通
✅ 多角色抽象就绪: 6 角色统一 Employee, 不复制 Agent
下一步: 9 样本 Benchmark (v4-pro) → Bug Fix ≥60% 门禁 → D-001 定案
```

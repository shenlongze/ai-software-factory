# factory-core 目录地图

> 只描述现状（职责 / 引用次数 / 消费者）。钢律：不评价、不预测、只列包。
> 引用次数 = 全仓 `import` 该包的 Python 文件数（排除包内自身）。

| 包 | 职责（一句话） | 引用 | 主要消费者 |
|----|--------------|------|-----------|
| `events/` | 事件日志与血缘，全系统事实流的记录处 | 169 | factory-console 全域、audit、approval |
| `tasks/` | 任务数据模型（任务的状态与字段定义） | 73 | factory-console/web、change、changeflow |
| `runtime/` | 执行运行时（把任务真正跑起来的引擎） | 72 | assignment、changeflow、cli |
| `agents/` | Agent 元数据与注册（谁有哪些技能/表现） | 64 | factory-console/web、assignment、cli |
| `workflows/` | 工作流定义（流程的步骤与编排结构） | 64 | assignment、changeflow、cli |
| `product/` | 产品域（产品生命周期与生成） | 36 | factory-console、web、cli |
| `providers/` | LLM Provider 注册与用量记录 | 34 | factory-console/web、cli、dashboard |
| `cli/` | factory-core 自带的命令行入口 | 28 | demo、tests/agents、tests/assignment |
| `intelligence/` | 决策 / 推荐 / 经验归集 | 24 | factory-console、web、cli |
| `assignment/` | 任务分配与匹配（决定谁来做） | 23 | cli、orchestration、recovery |
| `git/` | git 操作封装（仓库读写的基础能力） | 20 | change、cli、dashboard |
| `dashboard/` | 仪表盘数据聚合（可视化数据源） | 18 | cli、tests/change、tests/dashboard |
| `recovery/` | 崩溃恢复与状态重建 | 16 | cli、dashboard、tests/change |
| `change/` | 变更分析与关联（改动追踪） | 13 | changeflow、cli、validation |
| `execution/` | 执行派发（把单元交给运行时） | 12 | cli、orchestration、tests/execution |
| `runtimes/` | 运行时变体（多种执行场景） | 11 | cli、dashboard、runtime |
| `metrics/` | 指标计算（数值统计） | 10 | cli、dashboard、tests/metrics |
| `workspace/` | 工作区管理（项目目录空间） | 10 | factory-console/web、cli、tests/console |
| `changeflow/` | 变更流引擎（触发器 / 规则） | 7 | cli、tests/changeflow |
| `orchestration/` | 编排（多步骤调度） | 6 | cli、tests/orchestration |
| `project/` | 项目加载（示例与目录） | 6 | factory-console、cli、workspace |
| `understanding/` | 需求理解（把输入转成结构化） | 6 | cli、dashboard、tests/understanding |
| `validation/` | 校验（输入/结果检查） | 6 | cli、tests/validation |
| `demo/` | 演示脚本（示例流程） | 2 | cli、tests/demo |

**合计 24 包 · 零引用包：无 · 待判包：无**

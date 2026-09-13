"""services.work — 项目 / 工作 / 工作流 / 任务 / 任务节点。

拥有契约：contracts/work.py
调度器经 core.scheduler.ports.WorkPort 读取节点、依赖、时限、优先级。
不负责：调度决策（core/scheduler）、执行（services/execution）。
"""

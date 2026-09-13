"""services.execution — 执行实例 / 结果。

拥有契约：contracts/execution.py
调度器经 core.scheduler.ports.ExecutionPort 查活跃执行、创建实例。
关键语义：执行成功 ≠ 业务完成；完成由 Outcome.accepted 定义。
不负责：真正干活（plugins）、验收判定标准（能力声明的 verify）。
"""

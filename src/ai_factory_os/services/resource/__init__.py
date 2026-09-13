"""services.resource — 能力声明 / 实现绑定 / 解析。

拥有契约：contracts/resource.py
调度器经 core.scheduler.ports.ResourcePort 读取解析结果与能力声明。
不负责：成员与容量（services/organization）、执行（services/execution）。
"""

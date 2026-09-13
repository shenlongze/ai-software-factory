"""services.organization — 公司 / 部门 / 角色 / 成员。

拥有契约：contracts/organization.py、contracts/identity.py
调度器经 core.scheduler.ports.ResourcePort / LoadPort 读取成员与容量。
不负责：调度决策（core/scheduler）、能力声明（services/resource）。
"""

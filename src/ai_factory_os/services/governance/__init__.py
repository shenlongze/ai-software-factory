"""services.governance — 门 / 预算 / 策略。

拥有契约：contracts/governance.py
调度器经 core.scheduler.ports.GatePort / LoadPort 询问是否已批、预算是否够。
门不是流程常量：由能力声明的 approval 推导，数量与位置不固定。
不负责：能力声明本身（services/resource）。
"""

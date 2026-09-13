"""plugins — 一切实现绑定（只依赖 contracts）。

平台不认识任何具体能力；能力由插件声明与实现。
插件种类：
    factories    行业工厂（模板 + 能力声明 + 角色 + 验收，纯数据）
    agents       Agent 实现      skills   技能实现     tools    工具实现
    mcp          MCP 集成        models   LLM / Embedding Provider
    connectors   外部系统        controllers  浏览器 / 电脑控制
    healers      修复执行端      notifiers    通知渠道
    triggers     触发器         storages     存储后端

铁律 R4：plugins/* 只 import contracts。
"""

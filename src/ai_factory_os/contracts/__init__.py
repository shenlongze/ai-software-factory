"""contracts — AI Factory OS 契约层（零依赖）。

本层只放数据结构、枚举与协议。禁止：if / for / IO / import 其他顶层包。

契约清单（11 域）：
    identity      主体（人 / Agent / 服务）
    organization  公司 / 部门 / 角色 / 成员
    work          项目 / 工作 / 工作流 / 任务 / 任务节点
    resource      能力 / 实现绑定 / 解析
    execution     执行 / 结果
    governance    门 / 预算 / 策略
    learning      经验
    conversation  会话
    scheduling    调度决策 / 排序键 / 就绪条件
    events        事件（链式事实）
    errors        统一错误码

ID 前缀：
    CAP- 能力 · W- 工作 · WS- 工作流 · T- 任务 · TN- 任务节点
    RS- 解析 · EX- 执行 · OC- 结果 · GT- 门 · XP- 经验
"""

"""services — 平台的七个业务域（只依赖 contracts）。

    organization   公司 / 部门 / 角色 / 成员
    work           项目 / 工作 / 工作流 / 任务 / 任务节点
    resource       能力声明 / 实现绑定 / 解析
    execution      执行实例 / 结果
    governance     门 / 预算 / 策略
    learning       经验
    conversation   会话（唯一人类入口）

域内统一结构（由铁律 R11 强制，只允许五件套 + __init__）：
    service.py     用例与编排 —— 该域唯一对外入口
    store.py       持久化 —— 只被本域 service 使用
    rules.py       纯规则与判定 —— 无 IO，可单测
    events.py      本域发出的事件定义
    contracts.py   域内部契约（对外契约一律在 contracts/）

域间只走契约与事件，禁止 import 另一域的实现（铁律 R3）。
"""

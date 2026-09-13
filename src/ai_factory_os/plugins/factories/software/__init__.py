"""plugins.factories.software — 第一个工厂：软件交付。

本包全部是**数据**：内核里没有 "PRD" / "计划" / "验证" / "交付" 任何一个词。
    capabilities.py   本工厂用到的能力声明
    bindings.py       每个能力落在哪种实现上
    roles.py          角色与授权
    acceptance.py     交付验收标准
    template.py       流程模板（步骤图）+ 纯函数 instantiate()

审批不是流程常量：两个门由"由人满足的能力"表达（CONFIRM-PRD / CONFIRM-PLAN），
后继节点依赖它们的 accepted Outcome → 没人确认，后继自动 blocked。
"""

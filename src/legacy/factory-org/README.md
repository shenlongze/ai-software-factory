# factory-org — AI Software Factory 组织扩展 (Phase 16A, ADR-0036)

独立 Extension 包: Company/Department/Role/Employee/Authority/Knowledge
组织模型 + 独立数据空间 `<root>/org/` + `org.*` 审计事件。

- `org/models.py`    组织领域模型 (Pydantic v2)
- `org/store.py`     OrgStore 独立数据空间 (原子写, 损坏失败安全)
- `org/events.py`    org.* 事件辅助 (经 factory-core EventLogger)
- `org/templates.py` company 模板 (software_company / solo) + Role 冲突规则
- `org/registry.py`  EmployeeRegistry (find_by_capability / find_by_role, 只推荐不分配)
- `org/lifecycle.py` OrgLifecycle 编排 (公司/部门/角色/员工/权限/知识生命周期)
- `org/cli.py`       `factory-org` 独立 console script CLI

约束 (phase16-organization-model-review.md):
- factory-org 是 Extension: Core/Runtime/Desktop 零修改
- 事件驱动: 全部组织变化可审计 (org.* 经 EventLogger)
- Default Deny: Authority 绑定 Role, 未声明即拒绝; 显式 deny 优先
- Employee != Role, Capability != Role
- 禁: 真实 LLM / Agent 执行 / 自动任务分配 (Phase 17/18)

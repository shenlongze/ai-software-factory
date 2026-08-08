# S7-001 — Organization Model（Completion Report）

> 日期: 2026-08-08 | 状态: 完成 | pytest 5604 (5521 + 83)
> Sprint 7A: Execution Foundation (S7-001 组织模型)

## 修改文件

```
factory-exec/exec/roles.py            (增强: resolve_role 3 链解析 + ORG_TEMPLATE_ROLE_MAP + org_role_coverage)
factory-org/org/templates.py          (RoleSpec.role_ref 字段 + software_company/solo 模板 4 AI 角色引用)
factory-org/org/models.py             (Role.role_ref 字段, 默认 "" 向后兼容)
factory-org/org/lifecycle.py          (create_role(role_ref) + resolve_role_ref 统一解析)
factory-org/org/cli.py                (_resolve_role_id 委托统一解析)
factory-org/org/projects.py           (新建: Project/Sprint/Stage/Artifact/ProjectTaskLink/ProjectStore/ProjectLifecycle)
factory-core/events/models.py         (EventType +7: org.project.*/org.sprint.*/org.stage.*/org.artifact.*) — 允许例外
factory-org/org/events.py             (7 个 record_* 函数)
tests/s7/                             (新目录: 83 测试 — role_resolution 24 + projects 45 + integration 14)
```

## 架构影响

```
1. 角色双体系统一: org 模板 (CEO/PM/Architect/Developer/QA) ↔ exec roles.py (6 角色)
   通过 role_ref 单一注册表连接; resolve_role 3 链 (id 精确 → 显示名大小写不敏感 → 别名)
2. 统一生命周期模型: User→Project→Sprint→Workflow→Stage→Task→Artifact
   Project (idea→active→maintained→archived 单向状态机) + Sprint + Stage (role 校验) 
   + Artifact (prd|design|code|test|release) + ProjectTaskLink (Task 冻结, 扩展侧映射)
3. 事件: 165 (+7 org 生命周期事件)
4. 向后兼容: 既有 roles.json (无 role_ref) 加载零破坏; require_role 精确语义不变
```

## 测试结果

```
pytest 全量: 5604 passed, 0 failed
tests/s7 83 新测试: resolve_role 3 链/大小写/别名/映射完整性/Project 状态机/Sprint/Stage/Artifact/事件契约/向后兼容
Core/Runtime/Desktop diff = 0 (events 枚举 +7 允许例外)
```

## Migration 说明

```
既有数据 (roles.json 无 role_ref): 默认 "" → 加载零破坏, 无需迁移
新数据: 模板创建自动带 role_ref; hire 大小写不敏感 (Developer == developer)
```

## 下一步

```
S7-002 Artifact System (Artifact 流转完整化: 阶段产物→下一阶段输入)
```

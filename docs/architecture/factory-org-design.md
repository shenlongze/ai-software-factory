# factory-org 设计 — AI Organization Foundation (Phase 16A, ADR-0036)

> 日期: 2026-08-07 | 状态: Accepted
> 前置: phase16-organization-foundation-review.md / organization-model.md / agent-employee-model.md / ai-company-operating-model.md / knowledge-learning-model.md

## 1. 定位

`factory-org/` 是独立 Extension 包: Factory 从"管理软件生产"升级为"管理 AI 组织"的
**组织基础层** — Company/Department/Role/Employee/Authority/Knowledge 六实体全生命周期 +
审计事件流。**本阶段只做组织状态与审计, 零执行副作用** (禁真实 LLM / Agent 执行 /
自动任务分配 — 属 Phase 17/18)。

## 2. 六实体模型 (`org/models.py`, Pydantic v2)

| 实体 | 关键字段 | 语义 |
|---|---|---|
| Company | id / name / template / knowledge_space / departments[] | 公司根; knowledge_space = 公司知识空间 Layer 2 根 (公司隔离) |
| Department | id / company_id / name | 部门; id 全库唯一 + 名称公司内唯一 |
| Role | id / company_id / department_id / name / responsibility / authority_policy / human | 职位; department_id="" = company-level (Solo 扁平); authority_policy 只接受 allow/deny |
| Employee | id / company_id / name / role_ids[] / capabilities[] / status / left_at | 员工; **Employee ≠ Role, Capability ≠ Role** |
| Authority | id / role_id / permission / effect | 权限绑定 Role, 不绑员工/技能 |
| KnowledgeItem | id / company_id / domain / content / version | 企业知识, 公司隔离 |

EmployeeStatus: ACTIVE / LEFT (离职保留记录审计, 权限即刻失效, 不进候选)。

## 3. 数据空间 (`org/store.py`)

- 独立目录 `<root>/org/`, 六个 `_SectionStore` 子库 (companies/departments/roles/
  employees/authorities/knowledge) 各一个 JSON 文件, 原子写 (tmp + os.replace)。
- 损坏文件 → `CorruptOrgStoreError` 响亮报错 (store 层契约: 损坏一律响亮, 绝不静默
  返回空; save 先读后写, 损坏文件上 save 同样响亮)。
- `OrgStore` 门面: 六实体 CRUD + 公司/部门/角色/员工/知识查询 (list_*_by_company
  公司隔离) + `count_companies()` 计数。
- 与 tasks/agents/product/intelligence 等数据空间并列, 互不干扰。

## 4. 模板 (`org/templates.py`)

- `CompanyTemplate` 声明式模板: departments + roles (RoleSpec 含 authority_policy)。
- 内置: `software_company` (MarkPad AI Software Company: Product/Engineering/Quality
  三部门, CEO(Human)/PM/Architect/Developer/QA) + `solo` (扁平无部门, 同一角色集)。
- 模板实例化 (create_company) 物化: 公司 → 部门 → 角色 → 权限矩阵落库, 事件链序固定。
- **Role 冲突规则** (`FORBIDDEN_ROLE_COMBINATIONS`, 执行权 != 审核权, 组合顺序无关):
  `developer+reviewer` / `developer+qa` / `任何角色+CEO` (最终批准权唯一, Human CEO)。

## 5. 事件链 (`org/events.py` + factory-core EventType 枚举)

14 个 `org.*` 事件 (EventType 137 → 151, 纯增量枚举):

```
create_company:  company.created → department.created ×N → role.created ×N
                 → authority.granted/denied ×M          (链序固定, 测试断言)
hire_employee:   employee.joined → employee.role_assigned → employee.capability_added ×K
assign/transfer: employee.role_assigned (冲突组合硬拒绝前置)
leave:           employee.left (权限即刻失效, 幂等)
grant/deny:      authority.granted / authority.denied (同 (role, permission) last-write-wins)
check:           authority.checked (越权尝试也审计 — Default Deny 可追溯)
只读审计:        company.viewed / employee.viewed / knowledge.viewed (ADR-0002)
```

## 6. 员工注册表 (`org/registry.py`) — 只推荐不分配

- `register_employee`: 入职落库 (upsert)。
- `find_by_capability(cap, company_id?)`: 能力精确匹配 (大小写敏感), 只返回 ACTIVE。
- `find_by_role(role_id, company_id?)`: 角色成员匹配 (Role ≠ Capability)。
- `find(company_id?, role_id?, capability?)`: 组合检索 AND; 空字符串/None 过滤 = 无过滤。
- `candidates_for(requirement)`: duck-typed `required_capabilities`。
- 检索零副作用: 不发事件 / 不改任何库; **不产生任何 assignment/execution** — Phase 18
  才自动派发。

## 7. 生命周期编排 (`org/lifecycle.py`)

- `create_company` / `create_department` (id 唯一 + 名称公司内唯一) / `create_role`
  (authority_policy 物化为 Authority 记录)。
- `hire_employee` (单一角色, 跨公司角色硬拒) / `assign_role` (冲突硬拒) /
  `transfer_role` (剩余角色集冲突校验) / `leave` (幂等)。
- 权限模型 **Default Deny**: `check_authority` 无记录即拒绝, 显式 deny 优先于 allow;
  高危 `release.approve` 仅 CEO 声明 → Developer 硬拒绝。
- `add_knowledge`: 公司隔离 + 版本化。

## 8. CLI 双形态 (`org/cli.py`)

| 形态 | 入口 | 实现 |
|---|---|---|
| 独立 CLI | `factory-org` console script (pyproject) | `org/cli.py` 全量 (parser/dispatch/print) |
| 主 CLI | `factory org <sub>` | 复用同一 `cmd_*` 函数 (单一实现零复制), 主 CLI `_print_org` 文本渲染与独立 CLI 逐字一致 |

命令面: `company create/show` / `employee hire/list` / `authority check` /
`knowledge add/list`; `--role` 接受角色 id 或名称 (大小写不敏感)。错误映射:
NotFoundError → rc 7, 其余业务错误 → rc 1。所有 CLI 行为发审计事件。

## 9. Removal Isolation

- factory-org 只依赖 factory-core events 层 (Extension → Core 单向); factory-core
  零顶层 imports 本包 (CLI 经 `_open_org_cli` 延迟 import + sys.path 挂载)。
- 删 factory-org → `factory org` 命令 rc 7 (装配点响亮), 其余命令零影响。

## 10. 与既有架构文档的关系

- organization-model.md: 统一组织模型 (Solo ↔ Enterprise) — 本设计是其落地。
- agent-employee-model.md: Agent = 组织中的专业员工 (角色化) — Employee 模型即其承载。
- ai-company-operating-model.md: AI Company Operating (权限/PM/集团扩展) — 权限模型落地。
- knowledge-learning-model.md: Knowledge 三层隔离 — 本阶段实现 Layer 2 公司知识空间
  (add/list 公司隔离)。
- 运行时/执行边界见 organization-runtime-boundary.md。

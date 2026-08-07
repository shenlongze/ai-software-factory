# ADR-0036 — Phase 16A: Organization Foundation (factory-org)

> 日期: 2026-08-07 | 状态: Accepted

## 背景

Phase 16 目标: 把 Factory 从"管理软件生产"升级为"管理 AI 组织" — 一个人拥有一个
AI 公司 (MVP)。Phase 16A 交付组织基础层: Company/Department/Role/Employee/
Authority/Knowledge 六实体全生命周期 + `org.*` 审计事件 + CLI 双形态。
约束: Core/Runtime/Desktop 零修改 (仅 events 枚举), 禁真实 LLM / Agent 执行 /
自动任务分配。

## 决策

### 1. factory-org/ 独立 Extension 包
不污染 factory-core。独立数据空间 `<root>/org/` (六子库 JSON 原子写, 损坏响亮)。
唯一导入路径: 把 factory-org/ 挂 sys.path 后 `import org` (包名无连字符, 正常导入)。

### 2. 统一组织模型 (Solo ↔ Enterprise 同一模型)
同一套六实体模型承载 Solo (扁平, 无部门) 与 software_company (三部门) —
不允许两套系统。模板实例化 (create_company) 物化部门/角色/权限矩阵, 事件链序固定
可审计。

### 3. Employee ≠ Role, Capability ≠ Role
Employee.role_ids 多岗位 (冲突组合硬拒绝: developer+reviewer / developer+qa /
任何+CEO — 执行权 != 审核权, 顺序无关); capabilities 为声明技能集 (大小写敏感
精确匹配)。权限 (Authority) 绑定 Role, 不绑员工/技能; 能力培训不自动提权。

### 4. Default Deny 权限模型
Authority 未声明 = 拒绝; 显式 deny 优先于 allow; 离职权限即刻失效 (即使 Role
仍允许); 越权尝试也审计 (authority.checked)。高危 `release.approve` 仅 CEO 声明。
check_authority 本阶段为**咨询性校验**, 不接入执行流程 (边界见
organization-runtime-boundary.md)。

### 5. 只推荐不分配 (Registry 零副作用)
EmployeeRegistry find_by_capability/find_by_role/find/candidates_for 只返回 ACTIVE
候选, 不发事件、不改任何库 — 自动任务分配属 Phase 18。

### 6. CLI 双形态复用单一实现
`factory-org` console script 与主 CLI `factory org` 复用同一 `cmd_*` 函数
(org/cli.py), 文本渲染逐字一致 (主 CLI `_print_org`); `--role` 接受 id 或名称;
NotFoundError → rc 7。Removal Isolation: 删包 → `factory org` rc 7, 其余零影响。

### 7. 收尾裁定 (5 失败修复仲裁)
- 实现 bug 2: `find()` 空字符串 capability 过滤 = 无过滤 (改 `if capability:`;
  docstring 语义"空字符串 = 无过滤"); `create_department` 补**名称公司内唯一**
  检查 (模板已物化部门名不可重复建, id 唯一已有)。
- 测试 bug 3: `test_hire_emits_event_chain` 链尾断言 `seq[-3:]` 与 2 能力
  (`capability_added ×2`) 数学矛盾 → 改 `seq[-4:]`; `test_transfer_conflict_raises`
  前提 (Developer+QA 并存) 与冲突矩阵 (顺序无关硬拒) 自相矛盾 → 重写为一致场景
  (Developer+Architect 并存 → 转岗 Architect→QA 剩余 [Developer]+QA 冲突);
  `test_company_scoped` 种子 E-B1 缺 role_ids → 补 `role_ids=["R-1"]`。
- 仲裁原则: 冲突矩阵/检索语义 docstring 即规范 → 实现与测试分别按规范修正。

### 8. 编号冲突消解
任务文本指定 `0035-phase16a-organization-foundation.md`, 但 0035 已被 Phase 11B
(Human Console Web) 占用 (`docs/adr/0035-human-console-web.md`)。核对 `ls
docs/adr/` 后顺延到**下一个空闲号 0036**, 本 ADR 内记录冲突消解; 允许修改范围内
代码引用已同步 0036 (cli 接线注释/README), 被禁改文件 (events/models.py) 内注释
保留旧号不碰。

## 验证

- pytest 全量全绿 (≥4433; tests/org 192)
- CLI 冒烟链: company create (software_company) → employee hire → authority check
  (Developer release.approve = DENY) → knowledge add/list → employee list
  --capability (find_by_capability 可见), 非 JSON 输出逐条可见
- EventType 137 → 151 (+14 org.*), 纯增量枚举 (ADR-0001 路径)
- Core 零修改 (仅 events 枚举 + cli 接线), Runtime/Desktop 零修改

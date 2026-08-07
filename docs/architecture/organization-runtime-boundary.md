# Organization ↔ Runtime 边界 (Phase 16A, ADR-0036)

> 日期: 2026-08-07 | 状态: Accepted
> 配套: factory-org-design.md / phase16-organization-foundation-review.md

## 1. 为什么需要边界文档

Organization 层 (factory-org) 描述"**谁**在组织里、**能做什么**" (状态 + 审计);
Runtime 层 (factory-core runtime/execution, ADR-0009 等) 执行"**实际做了什么**"。
Phase 16A 只交付前者, 本文档固定两层的边界与未来接线点, 防止实现越界。

## 2. 本阶段硬边界 (零执行副作用)

| 领域 | 组织层 (Phase 16A) | 运行时层 (禁) |
|---|---|---|
| 员工 | hire/assign/transfer/leave — 组织状态 | ❌ 不创建/不修改 Agent/Execution |
| 能力 | employee.capabilities 声明 + 检索 | ❌ 不触发 Agent 执行 |
| 权限 | check_authority 咨询性校验 (返回 bool) | ❌ 不拦截/不强制执行门禁 |
| 知识 | knowledge add/list (公司隔离, 版本化) | ❌ 不注入任何执行上下文 |
| 任务 | 无 Task 引用 | ❌ 不自动任务分配 (Phase 18) |
| LLM | 无 | ❌ 禁真实 LLM / Agent 执行 |

铁律: `OrgLifecycle` / `EmployeeRegistry` 的写路径只落 Org 数据空间 + 发 `org.*`
审计事件; 检索路径零副作用 (不发事件、不改任何库 — 测试断言)。

## 3. 咨询性权限 vs 执行门禁

`check_authority` 是**咨询性 (advisory)** 校验: 返回 ALLOW/DENY + 审计事件,
但本阶段**不接入**任何执行流程 (execution/agent/workflow 零修改)。设计意图:

- 权限语义先落地并被测试锁定 (Default Deny / deny 优先 / 离职即刻失效);
- Phase 17/18 把 check_authority 作为执行前的授权门禁接入时, 语义零变更,
  只需在装配点消费 bool 结果。

## 4. AI 员工 ↔ 可执行 Agent 的未来接线 (Phase 17/18, 非本阶段)

```
Phase 16A 产物:  Employee (org 数据空间) — 组织身份/岗位/能力/权限/知识
Phase 17+ 接线:  Employee → Agent 执行身份映射 (同步/物化), 经既有 Runtime 执行
Phase 18 接线:   HR 流程 (Search → Training/Recruit) 后自动任务分配
```

边界规则:
- 组织模型 (六实体) 与执行模型 (Agent/Execution) 保持**独立数据空间**, 不并库;
- 未来接线只做"映射/物化", 不做"替代" — 组织状态是唯一事实源 (审计链完整);
- 自动分配必须显式开启 (本阶段 registry 只推荐, 永不自动派发)。

## 5. 数据空间隔离

```
<root>/org/        ← factory-org (六子库 JSON, 原子写)
<root>/factory.db  ← 审计事件库 (org.* 与全部事件同流, EventLogger)
<root>/tasks|agents|runtimes|providers|product|intelligence|...  ← 其余扩展
```

Org 数据损坏 → CorruptOrgStoreError 响亮失败; 事件库独立, 组织变化不污染其他域。

## 6. Removal Isolation 边界

- 删 factory-org → 主 CLI `factory org` rc 7 (装配点响亮暴露), 其余命令/其余域零影响;
- factory-org 只依赖 factory-core events (单向), factory-core 零顶层 imports 本包;
- 未来删除组织层不影响 Runtime/Agent/Workflow 既有链路。

## 7. 验收锚点

- pytest tests/org 全绿 (192), 全量 ≥4433;
- 检索零副作用测试 (test_find_emits_no_events / test_find_does_not_modify_store);
- CLI 冒烟链: company create → employee hire → authority check (deny) →
  knowledge add/list → employee list --capability (find_by_capability 可见)。

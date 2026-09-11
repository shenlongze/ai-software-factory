# OS Core SSOT & Production Takeover Contract (冻结)

> 冻结日期: 2026-09-10 | 性质: **架构契约冻结（文档）** | 基线: HEAD=3c1ff6a5
> 依据: `docs/audits` 外部审计 — 2026-09-10-os-core-closure-audit.md / 2026-09-10-os-core-production-takeover-plan.md
> 状态: **FROZEN** — 后续所有 MU 必须引用本契约；冲突以本文件为准。

---

## §0 目的

把"AI Factory OS Core 是唯一 Control/Domain SSOT"从理念固化为**可引用、可验收、可回滚**的契约，
约束后续 Production Takeover 的每一刀。

---

## §1 边界冻结（四平面）

| 平面 | 拥有 | 禁止 |
|------|------|------|
| **OS Core** | Domain Truth + 生命周期 + ID + Governance | 业务实现 |
| **Factory** | 领域逻辑(PRD/理解/架构/Repo/Code/Build/Test/打包) | 重定义 Project/Task/TaskNode/Execution/Resolution/Scheduler/Verification/Evidence/Outcome |
| **Runtime** | Execution Engine + NodeRun + Provider 调用 | 拥有 Task/Execution Truth |
| **Extension** | Plugin/Provider/Tool/Skill/Agent/Model/Connector | 绕过 OS Resolution/Governance |
| **UI(Web/CLI)** | 呈现 + 触发 | 拥有任何 Truth / 自生成 ID |

## §2 实体不变量（永久）

- `TaskNode ≠ Execution`；`Execution ≠ NodeRun`；`TaskNode ≠ NodeRun`
- `NodeRun` = Runtime 执行实例；**永远不得**被当作 OS TaskNode
- `Employee ≠ Identity`；`Role Definition ≠ Role Assignment`；`Professional Role ≠ Capability`
- `Execution success ≠ Verification PASS`；`exit_code==0` 只证明"执行完成"
- `Verification UNKNOWN` 是诚实缺省；禁止由执行结果隐式推导 PASS

## §3 事实链冻结

```
Execution → Verification → Evidence → Outcome → Promotion/Release
```
- Verification ∈ {UNKNOWN, PASS, FAIL, INCONCLUSIVE, BLOCKED}
- 仅显式 PASS（且 ≥1 Evidence）可过 Release Gate；UNKNOWN/INCONCLUSIVE → REJECTED
- 目标控制面：`Requirement → Capability → Resolution → Scheduler → Execution → Plugin → Provider`

## §4 Project ID 契约

- Project ID 唯一来源 = OS Core（`org/projects.json` / `os_core_project`）
- `conversation_id` / `slug` **只能作 reference/display**，**永不**作 project identity
- Factory/Web/Runtime 禁止自行生成 Project ID
- 无关联时用显式 `UNASSIGNED`，禁止用 conv_id 冒充

## §5 迁移硬规则（Rule 1-10）

1. 任何 MU 不得创建新 Truth Store
2. 不得让 Old Store 与 OS Core Store 同时成为 writer（禁双写）
3. Adapter 允许存在，但必须有明确 retirement condition
4. Projection 只读 Canonical Truth，不得反向写 Truth
5. Web 不得直接写 Domain Store
6. Factory 不得绕 OS Core 创建 OS-level Entity
7. Execution success 不得自动生成 Verification PASS
8. TaskNode 与 NodeRun 永久不同实体
9. 任何迁移完成必须有 Runtime Evidence
10. Legacy 退役必须证明 production caller = 0

## §6 验收模型（不得跳阶）

```
REAL CODE → CONNECTED → EXECUTED → VERIFIED → EVIDENCE
  → OLD PATH DISABLED → OLD WRITERS=0 → PRODUCTION CALLERS=0 → ROLLBACK AVAILABLE
```
`CODE ≠ CONNECTED` · `CONNECTED ≠ PRODUCTION` · `TEST ≠ PRODUCTION` · `PRODUCTION ≠ VERIFIED`

## §7 本轮已批准范围（MU-00 + MU-08）

- **MU-00**（本文件）：SSOT / Takeover Contract Freeze — 纯文档
- **MU-08**：切断 canonical execution chain 中 `Execution success → Verification PASS` 自动推导
  - 范围：`production_run.py` / `node_runtime.py` 的 executor-结果→验证结果 自动 PASS 路径
  - **明确不含**：verification_domain / evidence_domain 迁移、golden_path.py、cut5-9、
    os_core_verification/evidence、Task/Execution 迁移、Release 架构重构、任何 store 新增
- **MU-08 只能声称**："Execution success → Verification PASS 自动推导路径已被切断"
- **MU-08 不得声称**："旧 Verification Truth 已退役"（需后续 Verification Migration 满足
  OLD WRITERS=0 + CALLERS=0 才可）

## §8 未决（后续 MU，需单独批准）

Project 接管(MU-02，受 cut5-9 阻塞) · Work/Stream(MU-03) · Task(MU-04) · TaskNode(MU-05) ·
Execution(MU-06) · Resolution/Scheduler(MU-07) · Verification(MU-08b) · Evidence(MU-09) ·
Outcome(MU-10) · Identity/Role/Workforce(MU-11) · Capability/Plugin(MU-12) ·
Governance(MU-13) · Web(MU-14) · Legacy(MU-15) · factory-core(MU-16)

# S10-115 — J-1 生命周期状态单一来源：全写点枚举清单（改前/改后对照）

> 日期: 2026-08-25 | 版本: v1.1.83 | 验收 1: 全写点枚举
> 对应设计: docs/sprint10/S10-115-lifecycle-single-source-plan.md §0.3（写点全量枚举表）
> 唯一事实源: **project.json.status = canonical (Lifecycle 词汇)**；
> product.json.status + execution_state.json.lifecycle = 派生镜像，
> 只许由 `session/lifecycle_store.py::set_project_lifecycle` 更新。

---

## 0. 三处状态落点

| 文件 | 字段 | 词汇 | 角色 |
|---|---|---|---|
| project.json | status | Lifecycle (idea → … → delivered) | **canonical** |
| product.json | status | Lifecycle (旧词汇 product_defined/engineering_ready 兼容) | 派生镜像 |
| execution_state.json | lifecycle | Lifecycle | 派生镜像（存在时） |
| project.json | lifecycle | org ProjectState (idea/confirmed/…) | org 镜像字段（保留，非本 Sprint 范围） |

---

## 1. 写点全量枚举（改前 → 改后）

### 1.1 统一入口 `set_project_lifecycle`（NEW `factory-console/session/lifecycle_store.py`）

词汇校验（∈ Lifecycle.STATUSES，非法 → ValueError）· 防回退守卫（新 idx < 现有
project.json.status idx → LifecycleRegressionError；force=True 仅显式例外）· 三处同步
写（project.json.status + product.json.status + execution_state.json.lifecycle 存在时）·
失败安全（project.json 损坏 → LifecycleStoreError 不覆盖；镜像损坏 → 跳过 + errors 记录，
绝不臆造）。

### 1.2 改造写点（改走统一入口）

| # | 位置 | 改前 | 改后 |
|---|---|---|---|
| 1 | actions.generate_prd | product.status="prd_ready" 无条件（回退 bug：development 项目重生成 PRD 被降级） | canonical 存在 → **不写** product.status（防回退，镜像由统一入口在其它写点同步）；无 canonical → product.status=engineering_ready（旧 prd_ready 的 Lifecycle 等价，仅落 product.json，不造 canonical） |
| 2 | actions.create_product | product.status="project_created" | product.status=product_defined（Lifecycle 词汇；仅 product.json，canonical 由 org/统一入口管理） |
| 3 | service.confirm_project | 写 project.json lifecycle=confirmed（org 镜像），无 canonical | org 镜像字段 lifecycle=confirmed **保留**；project.json.status 缺省 → `set_project_lifecycle(PRODUCT_DEFINED)` 补 canonical（三处同步；失败安全不影响事务） |
| 4 | orchestrator._set_lifecycle | 手工双写 project.json + product.json | 委托 `set_project_lifecycle`（加 execution_state 同步 + 防回退守卫；签名兼容 project_dir/slug/status） |
| 5 | actions.approve_project_plan（approved） | 手工双写 project.json + product.json | 审批决策元数据先落（status 仍为 gate 值）→ `set_project_lifecycle(EXECUTION_READY)` 三处同步 |
| 6 | orchestrator 执行状态 L1206/1214/2034-2044/2647-2657 | state.lifecycle 内存 + _save_state + _set_lifecycle（双写） | 同上经 _set_lifecycle → set_project_lifecycle（state.lifecycle 同步；execution_state.json.lifecycle 双保险落盘） |
| 7 | orchestrator.accept_project | state.lifecycle=DELIVERED + _save_state + _set_lifecycle（双写） | 同上经 _set_lifecycle → set_project_lifecycle（canonical=delivered 三处同步） |
| 8 | board 读（L1013/1074） | 只读 product.json.status | 先 project.json.status，缺失回退 product.json.status（board.project_state_consistency 实现；board 读 canonical 优先） |

### 1.3 白名单直接写（设计指定例外，非漂移 — 契约测试 a 断言）

| # | 位置 | 值 | 理由 |
|---|---|---|---|
| W1 | actions.create_product | product.json.status=product_defined | 产品域落盘（product.json），canonical 由 org/统一入口管理（设计 §0.3 #2） |
| W2 | actions.generate_prd | product.json.status=engineering_ready（无 canonical 时） | 无 canonical → 派生值（设计 §0.3 #1）；canonical 存在 → 不写 |
| W3 | actions.prepare_project | project.json.status=pending_arch_review + product.json 同步 | S10-111 M3-7 架构审批门 gate 值（**非 Lifecycle 词汇**，独立于线性链；设计写点表未列，属既有行为保留，范围外） |
| W4 | actions.approve_project_plan（rejected） | project.json.status=pending_arch_review（值不变）+ arch_review.feedback | 拒绝分支非生命周期推进（状态值不变，仅审批元数据更新） |
| W5 | orchestrator 执行引擎 | state.status/state.lifecycle 内存 + _save_state | ExecutionState 全量持久化（tasks/status/governance…），非独立生命周期写；三处落盘已由 _set_lifecycle → set_project_lifecycle 负责 |
| W6 | service.confirm_project | project.json.lifecycle=confirmed（org 镜像） | org 状态机镜像字段（design §0.3 #3 保留） |

### 1.4 范围外（不涉及三轨，不改）

| 位置 | 说明 |
|---|---|
| orchestrator.resume_project L2145 | state.lifecycle=DEVELOPMENT + _save_state（恢复语义；只写 execution_state，不落 project/product — 既有行为保留） |
| change_control.py | change_control.json proposal status（自有文件，非 project/product/execution_state 三轨） |
| execution_replay.py L4 | 项目目录 git 快照回滚（M5-1，明确范围外） |
| org 状态机 | org/projects.json + project.json.lifecycle（org ProjectState 词汇，独立状态机） |

---

## 2. 存量对账（reconcile）

- 入口: `factory project reconcile [--dry-run]`（workspace = 数据目录；/board 侧只读
  一致性展示已由 board.project_state_consistency 提供）
- canonical 判定优先级: ① project.json.status 有效 ② product.json.status 映射
  （LEGACY_STATUS_MAP: project_created→product_defined / prd_ready→engineering_ready /
  draft→idea / confirmed→product_defined）③ execution_state.lifecycle ④ 全无/非法/损坏
  → 跳过 + 如实报告（不臆造）
- 修复前每项目快照 `projects/<slug>/.status_snapshot_<YYYYmmdd-HHMMSS>.json`（三处原值），
  快照落盘后再改；dry-run 只读预览

---

## 3. 防回退语义（验收 c）

- generate_prd: canonical 存在 → 不写 product.status（PRD 动作不覆盖 canonical）
- set_project_lifecycle: 单调前进（Lifecycle.STATUSES 索引比较；旧词汇先映射再比较；
  未知 gate 值如 pending_arch_review 无 index → 不阻断）— force=True 仅显式例外
  （ChangeControl 重规划等显式场景；PRD 重生成不得 force）

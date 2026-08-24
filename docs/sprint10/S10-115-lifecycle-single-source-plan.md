# S10-115 — J-1 生命周期状态单一来源：设计文档 + 实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-25 | 前置: v1.1.82 · M3 7/7 · P0-10/11 ✅ · M5-1 ✅
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-115 提示词（J-1, 消除三轨漂移）

---

## 0. 现状审计（CTO 独立复核 — 写点全量枚举 + 真实数据实测）

### 0.1 三处状态落点

| 文件 | 字段 | 词汇 | 角色 |
|---|---|---|---|
| project.json | status | Lifecycle (idea/product_defined/engineering_ready/execution_ready/development/testing/validation_pass/user_acceptance/delivered) | **canonical** (确认后存在; orchestrator._set_lifecycle 已事实写入) |
| product.json | status | **旧词汇混用**: project_created/prd_ready (product 域) + Lifecycle 值 (development/execution_ready) | 派生镜像 (待改) |
| execution_state.json | lifecycle | Lifecycle | 派生镜像 (存在时) |

### 0.2 真实数据实测（~/.factory/projects, 只读, 2026-08-25）

| 项目 | project.json | product.json | execution_state | 判定 |
|---|---|---|---|---|
| P-f848f51d (日记) | development | **prd_ready** | development | 🔴 漂移 (product 回退) |
| P-e023a04c (墨笺) | **缺失** | prd_ready | 缺失 | 🔴 缺 canonical |
| P-2f622bdf (旅行记账) | **缺失** | project_created | 缺失 | 🔴 缺 canonical |
| P-94ec0742 (命令行记账) | **缺失** | project_created | 缺失 | 🔴 缺 canonical |
| ai-factory-self | **缺失** | development | 缺失 | 🔴 缺 canonical |
| P-5be3a04a | development | development | development | 🟢 一致 |
| P-8b06b00d / P-c8bf4d4a | execution_ready | execution_ready | 缺失 | 🟢 一致 (es 无) |

### 0.3 写点全量枚举（改动面）

| # | 位置 | 现状 | 改法 |
|---|---|---|---|
| 1 | actions.generate_prd L465 | product.status="prd_ready" 无条件 (回退 bug) | project.json 存在 → 不写 status (防回退); 无 canonical → 写 engineering_ready |
| 2 | actions.create_product L300 | product.status="project_created" | → product_defined (Lifecycle 词汇) |
| 3 | service.confirm_project L1528 | 写 project.json lifecycle=confirmed (org 镜像) | 保留 org 镜像字段; 若 status 缺省 → 由统一入口补 canonical=product_defined |
| 4 | orchestrator._set_lifecycle L986 | project.json + product.json (正确口径) | → 委托 set_project_lifecycle (加 execution_state + 防回退守卫) |
| 5 | actions.approve_project_plan L790 | 手工双写 project.json + product.json | → set_project_lifecycle |
| 6 | orchestrator 执行状态 L1206/1214/2034/2038 | state.lifecycle + _set_lifecycle | → set_project_lifecycle (state.lifecycle 同步) |
| 7 | orchestrator.accept_project L2311 | (经 orchestrator 写 DELIVERED) | → set_project_lifecycle |
| 8 | board.py L1013/1074 (读) | 只读 product.json.status | → 先 project.json.status 回退 product.json |

## 1. 架构决策

### 1.1 唯一事实源

- **canonical = project.json.status** (Lifecycle 词汇; 确认后即存在)
- product.json.status / execution_state.json.lifecycle = **派生镜像**, 只许由 set_project_lifecycle 更新

### 1.2 统一写入口（新模块 `factory-console/session/lifecycle_store.py`）

```python
def set_project_lifecycle(project_dir: Path, status: str, *, force: bool = False,
                          product_file: Optional[Path] = None,
                          state_file: Optional[Path] = None) -> dict:
    """原子写三处: project.json.status + product.json.status + (execution_state.json 存在时) lifecycle。

    - 词汇校验: status ∈ Lifecycle.STATUSES (非法 → 明确错误)
    - 防回退守卫: 新 idx < 现有 project.json.status idx → 拒绝 (force=True 例外 —
      仅 ChangeControl 重规划等显式场景; PRD 重生成不得 force)
    - 失败安全: 单文件损坏 → 不崩, 记录 error; 绝不臆造
    """
```

### 1.3 词汇映射（对账/遗留兼容）

```python
LEGACY_STATUS_MAP = {
    "project_created": "product_defined",   # 产品已创建
    "prd_ready": "engineering_ready",        # PRD 就绪
    "draft": "idea", "confirmed": "product_defined",
}
# Lifecycle 值原样通过; 未知值 → 无法判定 (跳过, 不臆造)
```

### 1.4 防回退守卫（验收 c）

- generate_prd: project.json 存在 → **不写** product.status (canonical 不被 PRD 动作覆盖);
  product.json 镜像由 set_project_lifecycle 在其它生命周期写点同步
- set_project_lifecycle 内部: 单调前进 (Lifecycle.STATUSES 索引比较)

### 1.5 存量对账（一次性确定性修复）

- 入口: `factory project reconcile`（或 /board reconcile 别名, Codex 选简单者）
- 规则 (优先级): ① project.json.status 有效 → canonical ② 缺失 → product.json.status 映射 ③ 再缺失 → execution_state.lifecycle ④ 全无/非法 → 跳过 + 如实报告
- 修复前: 每项目快照写 `projects/<slug>/.status_snapshot_<YYYYmmdd-HHMMSS>.json`（三处原值）
- 修复: 写 canonical + 镜像; 快照落盘后再改
- demo 无 product.json → 无法判定 → 跳过不臆造 (诚实纪律)

### 1.6 board 读取（验收 5）

- board.py L1013/1074: 先 project.json.status, 缺失回退 product.json.status

## 2. 契约测试（tests/console/test_s10_115_lifecycle_single_source.py, ≥8, 仿 test_s10_112 风格）

a. **写点枚举**: 静态 grep actions/orchestrator/service 中直接写 status/lifecycle 的 `_write_json*` 调用 —
   全部经 set_project_lifecycle 或显式标注例外 (白名单断言)
b. **一致性校验器**: 构造漂移 fixture (三处不一致) → 校验器检出; 一致项目 → 通过
c. **防回退**: development 项目重生成 PRD → project.json.status 不变 (仍 development),
   product.json.status 不被降级 (跟随 canonical)
d. **对账修复**: 已知漂移 fixture (缺 project.json / product.json 回退) → 修复后三处一致 + 快照落盘
e. **词汇映射**: project_created→product_defined / prd_ready→engineering_ready / 未知→跳过
f. **统一入口单测**: 合法写/非法词汇错误/防回退拒绝/force 例外
g. **board 读取**: canonical 优先 (project.json 存在 → 用之; 缺失 → 回退 product.json)
h. **回归**: 全量 0 新增失败

## 3. 版本与发布

- pyproject `1.1.82` → `1.1.83` (若并发消耗则顺延, 不回退); CHANGELOG v1.1.83;
  版本断言同步; docs/FEATURES.md (头版本 + J-1 行); docs/sprint10/待办清单-已发现未落地.md L224 J-1 ✅

## 4. Codex 实施范围

**Allowed/Files**:
- NEW `factory-console/session/lifecycle_store.py` (set_project_lifecycle + LEGACY_STATUS_MAP + reconcile)
- MOD `factory-console/session/actions.py` (generate_prd/create_product/approve_project_plan 改走统一入口)
- MOD `factory-console/session/orchestrator.py` (_set_lifecycle 委托 + 执行状态写点)
- MOD `factory-console/session/service.py` (confirm_project 补 canonical 缺省)
- MOD `factory-console/session/board.py` (读取 canonical 优先)
- MOD `factory-console/session/commands.py` 或 cli (reconcile 入口)
- NEW `tests/console/test_s10_115_lifecycle_single_source.py`
- NEW `docs/sprint10/S10-115-write-points.md` (验收 1: 全写点枚举清单)
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / docs/FEATURES.md / docs/sprint10/待办清单-已发现未落地.md

**Forbidden（硬边界）**:
- 改 discovery/PRD 生成内容语义、org 状态机流转规则、主线 M4/P0 其他项
- 改 ChangeControl / M5-1 / 调度器 / M3a-d
- 调 LLM (纯规则); 禁 git add -A (工作区 untracked demo/、unused/ 不纳入)
- 禁臆造: 无法判定的存量项目如实跳过标注

**Validation**:
- `pytest tests/console/test_s10_115_lifecycle_single_source.py -q` 全绿
- env -u 聚焦 (actions/orchestrator/service/board + 既有生命周期测试) 全绿
- env -u 全量 console+api 0 新增失败
- 实测: 对账修复真实 ~/.factory 数据 (快照先行) — 修复后三处一致; 无法判定项目如实跳过
- commit: `feat(S10-115): J-1 生命周期状态单一来源 — set_project_lifecycle 统一入口 + 防回退 + 存量对账, v1.1.83`

## 5. 验收标准（Hermes 独立验证 — 与 Codex 自报告分开）

- [ ] 1. S10-115-write-points.md 落盘 (全写点枚举)
- [ ] 2. 8 个项目实测: 对账修复后三处一致; 修复前有快照
- [ ] 3. 契约测试 ≥8 覆盖 a-e 全绿
- [ ] 4. 全量回归 0 新增失败
- [ ] 5. pyproject + CHANGELOG + FEATURES + 待办清单 J-1 ✅ 同步
- [ ] 诚实: 无法判定项目如实标注; 波及面超预期 → 列出征询不擅自扩大

# 质量报告 (quality-report)

> 版本: v1.0 | 日期: 2026-08-06 | 状态: v1.0 Release 配套
> 关联文档: [system-architecture-review.md](./system-architecture-review.md) · [real-world-validation.md](./real-world-validation.md) · [project-structure.md](./project-structure.md)

本文档回答: **凭什么说 v1.0 可以发布** — 架构 / 测试 / 真实项目验证 / 安全四个维度。

---

## 1. Architecture — Core 冻结 + Extension 隔离

### 1.1 Core 冻结 (2026-08-06 冻结报告)

- **Core = 8 项通用原语** (core-boundary.md v1.0): 状态管理 · 生命周期 · 调度 · 执行抽象 · 事件审计 · 恢复 · 观测基础 · 组织。冻结后**不修改 Core 行为**, 新能力一律走 Extension 声明式注册。
- **证据**: [architecture-freeze-2026-08.md](./architecture-freeze-2026-08.md) 冻结审查通过, "架构冻结有效, 无需重构"; 四层架构审计 (system-architecture-review.md) 确认依赖单向向下、无循环 import。

### 1.2 Extension 隔离证据 (2026-08-06 import 方向复核)

| 检查项 | 证据 |
|:-------|:-----|
| 冻结原语层 (events/tasks/workflows/execution/runtime/recovery/assignment/orchestration/validation/metrics/project/workspace/runtimes/agents) 引用领域模块 | ✅ 0 处 (grep 复核) |
| Extension (understanding/product/providers/git/change/changeflow) 依赖面 | ✅ 仅 import events + 区内 (change→git, changeflow→change) |
| Intelligence 依赖面 | ✅ 仅 events + product 只读复用 |
| Core 可删性 (反向证明) | ✅ 删除 product 包后 `dashboard --view product` 仍 rc 0 (空快照); 删除 factory-console → Factory 照常运行 |
| 组合根约束 | ✅ `cli/commands.py` 对领域包只允许函数内延迟导入, **有测试断言** (`test_product_removal.py::test_cli_commands_has_no_top_level_product_import`); dashboard/collector 同规则 |

**已知只读例外 (已文档化, 不构成业务依赖)**: `dashboard/models.py` 顶层 `from git.models` (仅 git/change/changeflow 三视图渲染类型, `include_git` 缺省关)。

---

## 2. Testing — 4090 pytest + 92 Vitest

### 2.1 pytest 分域计数 (总计 **4090**, 全绿)

| 测试目录 | 用例数 | 测试目录 | 用例数 |
|:---------|-------:|:---------|-------:|
| tests/agents | 112 | tests/project | 34 |
| tests/assignment | 140 | tests/providers | 573 |
| tests/change | 202 | tests/recovery | 122 |
| tests/changeflow | 144 | tests/runtime | 219 |
| tests/cli | 45 | tests/runtimes | 98 |
| tests/console | 172 | tests/tasks | 27 |
| tests/dashboard | 165 | tests/understanding | 151 |
| tests/events | 69 | tests/validation | 82 |
| tests/execution | 100 | tests/workflows | 114 |
| tests/git | 197 | tests/workspace | 103 |
| tests/intelligence | 525 | **合计** | **4090** |
| tests/metrics | 113 | | |
| tests/orchestration | 73 | | |
| tests/product | 510 | | |

- 覆盖 24 个域目录, 与各模块一一对应; EventType 纯增量扩展 (基线只增不减)。

### 2.2 Vitest (Web UI, **92 passed / 12 文件**)

- `factory-console/web/frontend/src/test/`: App / DashboardPage / ProjectsPage / LifecyclePage / ApprovalPage / DecisionsPage / ProvidersPage / IntelligencePage / AppState / useAsync / components / api.client — 全部通过。

### 2.3 各阶段 pytest 演进 (零回退)

| Phase | 用例 | Phase | 用例 |
|:------|-----:|:------|-----:|
| P1 Event Logger | 69 | P8A Provider 抽象 | 2460 |
| P2 CLI | 141 | P8B-1 Selector | 2618 |
| P3A Validation | 223 | P8B-2 Capability/Cost | 2744 |
| P3B Agent+Skill | 335 | P8B-3 Provider 智能 | 2883 |
| P4A Workflow | 449 | P9a Product 基础 | 3063 |
| P4B-1 Adapter 接口 | 584 | P9b Generation | 3148 |
| P4B-2 Dispatch | 684 | P9c Approval 决策 | 3263 |
| P4B-3 Assignment | 824 | P9d Lifecycle 编排 | 3393 |
| P4C-1 Hermes 适配 | 908 | P10A-1 Intelligence 基础 | 3568 |
| P4C-2 Orchestration | 981 | P10A-2 Decision | 3666 |
| P4C-3 Recovery | 1103 | P10A-3 Recommendation | 3803 |
| P4C-4 Dashboard | 1203 | P10A-4 Experience | 3918 |
| P5A Example Layer | 1237 | P11A Console API | 4069 |
| P5A.1 Runtime Catalog | 1335 | P11B Console Web UI | **4090** |
| P5B Metrics | 1395 | P12A 系统审计 | 4090 |
| P6A Workspace | 1498 | P12B 真实项目验证 | 4090 |
| P6B 观测 Dashboard | 1616 | — | — |
| P6C Git 集成 | 1813 | — | — |
| P6D Change 智能 | 2015 | — | — |
| P6E Change Workflow | 2159 | — | — |
| P7 Understanding | 2310 | — | — |

**43 次提交, 每阶段独立可交付、可回退, 用例数只增不减。**

---

## 3. Validation — 真实项目全生命周期 (MarkPad, Phase 12B)

在**真实项目 MarkPad** (Flutter/Dart Markdown 编辑器) 上跑通完整生命周期,
需求: "MarkPad 表格编辑器增强" (单元格逐格编辑 / Tab 导航 / 内联编辑):

| 项 | 结果 |
|:---|:-----|
| 生命周期链 | LC-001 8 阶段: idea → research → prd → **approval** → ui → **approval** → architecture → task ✅ |
| 产物 | 6 Artifacts (idea/research/prd/ui + architecture/task_plan 决策链) ✅ |
| 人工审批 | APR-001 (PRD) + APR-002 (UI) 人工 approve; Decision (高风险) 绑定 Approval 等待人工 ✅ |
| 事件 | 34 个 (idea.created → lifecycle.started → stage.* → approval.* → provider.selected → generation.* → task) ✅ |
| 经验 | 2 条 (positive + negative); 正负聚合 factor=0.285; 推荐经验分 0.28 ≤ 能力分, 失败经验正确压低推荐 ✅ |
| 推荐可解释性 | score=0.738 = capability 0.90×0.35 + performance 0.80×0.30 + cost 0.70×0.20 + experience 0.28×0.15, 逐项可复算 ✅ |
| 回归 | 4090 pytest 全绿 (零回归), **Core 零修改** ✅ |

详细过程与 CLI 原文见 [real-world-validation.md](./real-world-validation.md)。

---

## 4. Security — 权限边界

| 边界 | 机制 | 证据 |
|:-----|:-----|:-----|
| **Console 只读** | ConsoleService 全部读方法, 零写 API; "不自动执行、不自动批准" | `tests/console/test_console_isolation.py`: 读方法前后数据空间逐字节一致 (唯一例外 events.db 的 CLI 审计事件); 删除 factory-console → Factory 照常 |
| **只 GET 路由** | `fastapi_adapter.py` 8 条路由全部 `@app.get` — 无 POST/PUT/DELETE | 路由清单: /api/dashboard /api/projects /api/projects/{id}/lifecycle /api/approvals /api/decisions/{id} /api/recommendations /api/experience /api/providers |
| 前端只读客户端 | `web/frontend/src/api/client.ts` 只暴露读方法 | 92 Vitest 覆盖 |
| 观测只读 | dashboard/metrics 全部基于 Event 的只读聚合, 无写入口 | system-architecture-review §2 |
| 事件不可篡改 | events 表 append-only (只 INSERT, 永不 UPDATE/DELETE), seq 自增回放锚点 | core-boundary §1 |
| 存储原子写 | JSON store 原子写 (tmp + os.replace), 损坏抛错不静默 | system-architecture-review 约定 §5 |
| 决策权在人 | Approval 状态机 + 高风险 Decision 强制绑定人工; CLI 仅发事件不越权 | approval-model.md / decision-intelligence-model.md |

---

## 5. 结论

- ✅ **架构**: 三区 + Human Layer 单向依赖, Core 冻结, 隔离有测试背书
- ✅ **测试**: 4090 pytest + 92 Vitest 全绿, 43 次提交零回退
- ✅ **验证**: 真实项目 MarkPad 完整生命周期闭环, 推荐可复算, Core 零修改
- ✅ **安全**: Console 只读 + 只 GET 路由, 事件 append-only, 决策权在人

**v1.0 达到 Release 质量。**

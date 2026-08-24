# Approval Gate 模型 (approval-model)

> 状态: IMPLEMENTED (已实现 — 见 ./audit/architecture-reality-audit.md)

> 通用 AI Software Factory 的**人工审核节点**统一模型:把"哪些环节必须由人拍板、如何拍板、
> 证据是什么"建模为可执行、可审计的 Gate 原语。Human Approval 是平台的核心价值
> (评审 §6: Dashboard 给人审核用; 冻结 §四: Approval Gate 模型就绪)。
> 关联文档: [workflow-model.md](./workflow-model.md)(门/三挡板) · [validation-model.md](./validation-model.md)(双验证/L1-L3)
> · [agent-skill-runtime-model.md](./agent-skill-runtime-model.md)(扩展模型) · [roadmap.md](./roadmap.md)(Phase 9/11)

---

## 1. 背景与定位

工厂已内建多个人工审核节点,但散落在不同机制里 (见 §4)。冻结报告 (§四) 确认将其统一为
**Approval Gate 模型**:

- 既有: 三挡板 (G1/G2/G3, 暂停流程) · 授权门 (发布授权) · Decision Gate (无决策记录不进修复) ·
  `validate approve/reject` (人工验收) · validate 退出码语义。
- 未来: Phase 9 (PRD/UI/架构人闸口) 与 Phase 10 (运维处置确认) 会引入更多审核场景;
  Phase 11 (候选) 提供统一 Web 审核台 (Human Approval Console)。
- **统一目标**: 一个 Gate 原语 + 一套事件 + 一种审核入口,覆盖所有"人闸口"。

---

## 2. ApprovalGate 模型

```yaml
ApprovalGate:
  phase:    <string>                    # 所属节点/阶段 (见 §3 节点表)
  required: mandatory | recommended | optional   # 必须 / 建议 / 可选
  approver: <role 或人>                  # 谁有权限批准 (见 §3)
  evidence: <产物/证据引用>               # 审核什么、依据什么 (见 §3)
  status:   pending | approved | denied  # 状态机三态
```

### 2.1 状态机

```
                    ┌───────────── 人工审核 ─────────────┐
                    ▼                                   ▼
   pending ──────▶ approved ──────▶ 流程继续 (进入下一节点)
      │
      └──────────▶ denied ────────▶ 打回返工 / 终止 (带理由)
```

- **pending**: 流程到达 Gate,产出候选产物 (PRD/UI 原型/架构方案/部署预案…),**等待人工**。
  此时流程必须停 (等效 workflow-model §3.3 暂停挡板; 或按 `required` 级别决定停或提醒)。
- **approved**: 人工确认通过 → 流程继续。状态转换**必须发事件** (`approval.granted`),
  并携带操作者身份与审核备注。
- **denied**: 人工驳回 → 打回对应节点返工或终止,必须带**驳回理由** (failure_class 语义,
  对齐 validation-model 失败分类)。转换发 `approval.denied`。

### 2.2 required 级别语义

| 级别 | 语义 | 行为 |
|:-----|:-----|:-----|
| **mandatory** | 必须人工批准, 否则流程不得前进 | Gate 未批准 → 流程阻塞 (CLI 退出码 4 语义), 无绕过路径 |
| **recommended** | 建议人工确认, 允许按预设条件自动放行 | 大改动必须人工 (如大重构的 Architecture), 小改动可自动通过 |
| **optional** | 可全自动, 人工仅抽查/事后查看 | 默认自动推进, 人工可随时介入审查 |

> **原则 (workflow-model §3.3)**: 自动推进 ≠ 跳过授权。mandatory 的 Gate 被跳过 = 流程事故
> (E1 级), 必须可审计检出。

---

## 3. 节点表 (冻结 §四)

| 节点 | 级别 | approver | evidence (审核依据) | 说明 |
|:-----|:----:|:---------|:--------------------|:-----|
| **Idea** | optional | 产品负责人 / 想法提出者 | 想法记录、市场调研摘要 (research.*) | 想法收集可自动; 仅重大方向需人确认 |
| **PRD** | **mandatory** | 产品负责人 | PRD 文档 (目标/用户/范围/验收标准) | **产品方向确认** — 三挡板 G1 的产品侧落点; 未批准不得进入 UI/架构 |
| **UI Design** | **mandatory** | 产品 + 用户代表 | UI 原型、交互说明、评审记录 (ui.reviewed) | **视觉方向确认** — 未批准不得进入开发 |
| **Architecture** | recommended | 架构师 + CTO/技术负责人 | 决策记录 (ADR)、影响范围分析、权衡说明 | 大重构必须, 小改动可选; 对齐 Decision Gate (无决策记录不进开发) |
| **Code** | optional | 测试工程师 / 协调器 (抽查) | 测试报告、变更清单、验证证据 (validation.*) | AI 自主执行, 人工抽查; 双验证机制已内建独立验证 |
| **Deploy** | **mandatory** | 发布授权人 | 构建产物、全量测试结果、健康检查、回滚预案 | **发布授权** — 对齐授权门 (workflow-model §3.3); 未授权不得发布 |
| **Incident** | optional | 值班负责人 / 事故决策人 | 事件链 (incident.*)、AI 诊断报告、处置建议 | 告警自动响应; 重大事故处置必须人工确认 |

> **节点演进**: 节点表是 Phase 9 (Idea→PRD→UI→Architecture) 与 Phase 10 (Deploy→Incident)
> 落地时挂载 Gate 的清单; Gate 原语本身与节点解耦, 新节点 = 新声明, Core 不改。

---

## 4. 与既有机制的关系

| 既有机制 | 归属 | 关系 |
|:---------|:-----|:-----|
| **三挡板** (G1 产品方向冲突 / G2 架构变更 / G3 Scope 扩展, workflow-model §3.3) | 暂停型挡板 | Approval Gate 的**暂停语义来源**: G1 ≈ PRD Gate 冲突, G2 ≈ Architecture Gate 触发, G3 是范围治理 (非节点, 仍走挡板) |
| **授权门** (发布构建需显式授权, workflow-model §3.3) | 非暂停授权 | 即 **Deploy Gate (mandatory)** 的现状实现 |
| **Decision Gate** (无决策记录不进入修复, workflow-model §4 Bug 流程) | 决策门 | Approval Gate 在**架构/修复决策**上的具体应用: 对应 Architecture/PRD Gate, 证据 = 决策记录 (ADR) |
| **validate approve/reject** (CLI, cli-design §2.6) | 人工验收 | 即 **Code Gate / L3 用户实测**的现状入口: 发 `validation.passed` + `human.decision` / `validation.failed` |
| **validate 退出码** (cli-design §5: 3=验证失败 / 4=需要人工) | 状态语义 | Approval Gate 的**机器可判读出口**: pending→4 (需要人工), denied→3 (打回), approved→0 |
| **Phase 9 人闸口** (PRD 批准后才进 UI/架构, roadmap §4) | 未来节点 | 即 **PRD/UI/Architecture Gate** 的落地场景 (事件 `product.prd.approved/rejected` 已规划) |

**区分**: 三挡板/授权门是"**流程要不要停**"的规则; Approval Gate 是"**产物要不要人审**"的
统一建模。Gate 落盘为状态 + 事件后, 二者通过同一条审计链 (事件日志) 汇合 — 三挡板触发
= Gate 置 pending 且流程暂停; 授权批准 = Gate pending→approved。

---

## 5. 实现方向 (冻结 §四)

### 5.1 Gate 原语 (Core)

- 新增 `ApprovalGate` 模型 (Pydantic, 沿用 tasks/agents models 模式: 枚举宽容 parse +
  id 即存储键 + `to_dict`), 状态机 `pending → approved | denied`。
- 存储: `approvals/` 独立 store (JSON 或 SQLite 投影, 实施时按 ADR 裁定), 与
  task/workflow 通过引用关联 (gate_id ↔ task_id/workflow_id/artifact)。
- **事件集成 (冻结 §三 namespace 扩展)**: 未来 `approval.*` 族 —
  `approval.required` (Gate 创建/待审) / `approval.granted` (批准, 带操作者+备注) /
  `approval.denied` (驳回, 带理由)。复用 Core Event Logger, 加枚举成员不改表
  (ADR-0002 路径)。Phase 9 落地时叠加 `product.prd.approved/rejected` 等 domain 事件。

### 5.2 CLI validate 退出码语义扩展

现状 (cli-design §5): `0` 成功 · `3` 验证失败 · `4` 需要人工 (三挡板/发布授权未批/第 3 次失败上报)。

扩展方向:

| 场景 | 现状 | 扩展 |
|:-----|:-----|:-----|
| Gate 待审 (pending) | 流程停, 退出码 4 | 保持 4 (需要人工); `factory approval list` 列出全部 pending |
| Gate 批准 | 人工 approve 后退出码 0 | 保持 0; `factory approval approve <id> --reason …` 显式化 |
| Gate 驳回 | `validate reject` 退出码 3 | 保持 3; `factory approval reject <id> --reason …` 统一入口 |
| 违反 mandatory | — | 新增可判读语义: 跳过 mandatory Gate 的行为必须可审计检出 (事件链断言) |

> **等价性铁律 (评审 §6)**: Web 上的确认 = CLI 的 approve/reject = 同一批事件
> (`approval.granted` / `product.prd.approved` / `validation.passed` + `human.decision`),
> 可审计、可回放。任何入口不得创建第二条审批路径。

### 5.3 Web UI 审核台 (Phase 11, 候选)

```
┌──────────────┐   只读查询 + 审批动作    ┌────────────────────────┐
│  Frontend     │ ──────────────────────▶ │  Factory API 薄层        │ ──▶ Core
│  React/Vue    │                         │  FastAPI: 只读 + approve │     (Task/Workflow/
│ 或轻量 HTML+JS│ ◀────────────────────── │  不引入新执行路径          │      Event/Validation)
└──────────────┘       审批结果           └────────────────────────┘
```

- **只暴露两类端点**: ① 只读查询 (dashboard/events/metrics 聚合的 HTTP 化, 含 Gate 待审清单)
  ② 审批动作 (approve/reject → 既有事件/状态机)。**不暴露**执行/写仓库能力。
- **定位**: 人类审核台 (Approval Console), 不是给 AI 用; CLI 保留为工程师主入口。
- **安全**: 审核动作全部落事件 (audit), 带操作者身份; 读多写少, 无破坏性写操作。
- **启动信号 (roadmap §6)**: Phase 9 人闸口与 Phase 10 处置确认在 CLI 上真实使用后,
  若人工审核频率成为瓶颈, 即启动 (Phase 11 标注"可并行", 冻结 §五)。

---

## 6. 审核纪律 (与 validation-model 公理一致)

1. **证据先行**: 每个 Gate 的 evidence 必须可回查 (产物指针、命令输出、实测记录) —
   "批准"不是点按钮, 是"审了证据再点"。
2. **驳回必须带理由**: denied 必须有 failure_class/理由, 供打回返工与指标
   (human_intervention 等) 统计。
3. **操作者留痕**: 每次 approved/denied 记录操作者身份, 全程可审计、可回放 (Event Replay)。
4. **人审 ≠ 包办**: 人工只裁决 Gate, 不亲自执行专业工作 (agent-model §1 协调器纪律);
   AI 产出永远只是"候选产物 + 证据" (roadmap §4 边界: 产品判断永远是人)。

下一份文档: roadmap.md(Phase 7–11 落地排序与验收)。

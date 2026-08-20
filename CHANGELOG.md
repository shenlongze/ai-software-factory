# Changelog

> AI Software Factory — 变更日志 (Keep a Changelog 风格, 中文)。
> 版本语义: `v1.0.0-rc1` 为 v1.0 发布候选 (Release Candidate), 功能冻结, 只做文档与修复。

---

## [v1.1.7] — 2026-08-20

**M1b 积压清道夫 (E3 第一个可售卖工作负载)**: 分诊 → 执行 → 证据包 → 审批 → 报告
+ M1a Review 3 个 Minor 修复。

### Added

- **`factory workload backlog --project <dir>`** — BacklogSweeper 积压清道夫
  (`session/workloads/backlog_sweeper.py`): 读取项目 `issues.json`
  ([{id,title,type}]) → 分诊 (bug/feature/dependency → 修复策略) → 对每个
  issue 执行 (复用 RepoModeRunner Execution Kernel → Sandbox patch + pytest)
  → 组装 EvidenceBundle (diff+测试+日志+决策+变更文件, 落盘
  `projects/<slug>/evidence/`) → 自动请求审批 (复用 ApprovalGate) → 运行报告
  (`projects/<slug>/sweeps/sweep-*.json`)。
- **确定性依赖修复** — `DependencyPatchGenerator`: 真实分析 requirements.txt /
  pyproject.toml, 生成可应用 unified diff (无 LLM 也能「干完一件看得见的活」);
  bug/feature 走 LLM patch (无 LLM → 诚实 skipped, 不伪造)。
- **`factory workload status --project <dir>`** — 最近一次清道夫运行报告 (只读)。
- **`factory approval list [--project X]` / `factory approval decide <id> approve|reject`**
  (T2, Minor #2) — 待审批列表 + 审批决策, 复用 exec ApprovalGate (终态落库 +
  org.execution.approved 审计), 与 `factory-exec approval` 同源。
- **EvidenceBundle 接入普通执行** (T3, Minor #3) — `execute_project`/`resume`
  完成后自动组装证据包 (`EvidenceBuilder.from_execution_result`, 复用
  from_repo_result 模式), `factory evidence list` 可见。
- **logs 字段填充** (T4, Minor #1) — 组装证据包时填充执行日志 (执行事件摘要:
  理解/计划/patch/测试; 任务队列/验证/终态), 失败安全。
- **demo/repo** — BacklogSweeper 演示仓库 (main.py + 测试 + requirements.txt +
  issues.json: dependency 可确定性修复, feature/bug 需 LLM)。

### Validation

- 实测: `factory workload backlog --project demo/repo` → ISS-001 dependency 真实
  修复 (requirements.txt 变更 + 测试✅) + 证据包可见 + pending 审批; approval
  list/decide 全链路可用。
- 新增 31 测试 (test_workload_backlog 20 / test_evidence_attach 7 /
  test_approval_decide 9 含注册); 全量回归 0 failed。

---

## [v1.1.5] — 2026-08-20

**M1 内核切片（AI Company OS 第一块地基）**: 存量仓库模式 + 工具发现 + 真 MCP 客户端。

### Added

- **`factory repo <path> <目标> [--patch]`** — 存量仓库模式: 理解(core/understanding) →
  计划(LLM 或确定性) → patch 应用(Sandbox 副本, 原仓库零影响) → pytest 验证。
- **`factory tools list`** — 发现本机 AI CLI (codex/hermes/openclaw/claude) +
  MCP server 配置 (~/.codex/config.toml / ~/.claude.json / .mcp.json)。
- **StdioMCPClient** — 真 MCP stdio 客户端 (JSON-RPC 2024-11-05, 不绑第三方 SDK);
  工具是增强层, 任何任务不依赖外部 CLI 完成。
- **core_loader** — 延迟加载 factory-core/factory-exec (对齐 actions 模式)。

### Validation

- 实测: 临时 git 仓库 + patch → 变更文件 + pytest 通过; tools 发现 3 CLI + 2 MCP。
- 新增 21 测试; tests/console+exec 5791 passed; 全仓库 11805 passed。

---

**S10-084 Product Intelligence Pipeline (P0)**: 从 Idea 到 PRD 的多角色资产链。

### Added

- **ArtifactRegistry** (`session/artifact_registry.py`): 版本化资产注册表
  (`projects/<slug>/artifacts/<type>/v<n>/artifact.md + artifact.json`, v+1 递增,
  旧版本保留 — 渐进明细/变更前提)。
- **ProductPipeline** (`session/pipeline_runner.py`): 7 角色资产链
  (PM→product / Market→market_analysis / Competitive→competitive_analysis /
  UX→ux_flow / Architect→architecture / QA→test_plan / SeniorPM→prd),
  LLM 可用 → 角色 prompt; 失败/无 LLM → deterministic 兜底 (复用既有引擎)。
- **审计血缘**: 每资产 `ARTIFACT_CREATED` 事件 (artifact_reference + parent_event_id 链)。
- **discovery.md 落盘**: "先帮我整理需求，不要创建项目" → 需求快照落盘为
  discovery 资产 (draft), 不创建项目。
- **入口**: 意图 `让PM分析/产品管线` + action `product_pipeline` + 路由。

### Validation

- 新增 8 测试 (registry 3 + pipeline 3 + action/intent 2 + discovery 1)。
- `tests/console` 全量通过 (4488, 含既有回归); 全仓库 11760+ passed。

### Notes

- 需求变更与渐进明细闭环 (ChangeProposal → 影响分析 → 审批 → 资产 v+1 →
  ReplanningEngine) 为 P1, 见 docs/sprint10/S10-084-plan.md §4。

---

**Discovery 沟通修复 (S10-082 遗留问题 #1 落地)**: 产品发现流程不再把一切输入当字段答案,
控制指令/查询/编辑与字段回答分层处理。

### Added

- **控制短语 (非答案)**: 发现/确认阶段识别 `取消` / `整理需求不创建` / `项目列表` / `创建项目`
  等指令, 不再被吞成字段答案 (问题/用户/核心功能)。
- **批量问题模式**: `问题有点多` → 一次性列出剩余必填问题; 支持 `问题:...; 用户:...; 功能:...`
  一次填充多个字段 (自动去标签前缀)。
- **修改已有信息**: `把目标用户改成创业公司` / `修改一下，功能改成X` 更新已填字段
  (发现阶段与确认阶段均支持, 确认阶段普通文本仍是改名)。
- **创建引导**: 信息不足时 `现在创建项目` → 列出还缺字段并询问是否补充 (不再创建空名项目)。

### Fixed

- 发现阶段输入其它意图 (`我现在有哪些项目` 等) 时, 产品流程让位, 原输入走普通意图链。

### Validation

- 新增边界测试覆盖: 正常发现/多段填充不重问、用户打断→项目查询、创建引导、
  任意阶段取消、修改已有信息 (含反例不误判)。
- `tests/console` 全量通过 (4470+ 用例, 含既有回归)。

---
## [v1.0.0-rc1] — 2026-08-07

首个发布候选: **AI Software Factory v1.0 全能力落地**。Core + Extension + Intelligence
+ Human Console 四层齐备, 真实项目 (MarkPad) 走通完整生命周期, 4111 后端测试 +
92 前端测试全绿。

### Architecture

- **Core 冻结 (8 项通用原语)**: 状态管理 · 生命周期 · 调度 · 执行抽象 · 事件审计 ·
  恢复 · 观测基础 · 组织 — `events/ tasks/ workflows/ agents/ assignment/ execution/
  runtime/ runtimes/ recovery/ orchestration/ validation/ metrics/ dashboard/ project/
  workspace/ cli/`。冻结后不修改 Core 行为, 新能力一律走 Extension 声明式注册。
  冻结审查: [docs/architecture-freeze-2026-08.md](./docs/architecture-freeze-2026-08.md)。
- **Extension 系统 (声明式注册, 零 Core 破坏)**: `understanding/ product/ providers/
  git/ change/ changeflow/` — 依赖面仅 `events` + 区内, 删除任一 Extension 不影响
  Core 运行 (有测试断言, 如 `test_product_removal.py`)。
- **Intelligence 层 (只读复用, 决策/推荐/经验)**: `intelligence/` — Decision
  (决策链 + Evidence 六来源强制 + Risk R1–R5 + Approval 绑定)、Recommendation
  (四因素可解释评分 0.35/0.30/0.20/0.15)、Experience (五域 + 30 天半衰期衰减)。
- **Human Console (人在环上)**: `factory-console/` — React 7 页面 + FastAPI
  8 只读 GET 路由, Simple/Expert 双模式, 零写 API (人工审批走 CLI 决策动词)。

### Capabilities

- **Idea → Development 生命周期**: 12 阶段模型 (docs/lifecycle-model.md) 中 6–9
  完整实现, 1–5 由 Product Intelligence 承接, 10–11 部分支撑。software_project
  8 阶段链: `idea → research → prd → [approval] → ui → [approval] → architecture
  → task`。`factory demo markpad` 一键走通 (docs/demo-guide.md)。
- **Decision Intelligence (Phase 9c / 10A-2)**: 决策链 (Product → Architecture →
  Task Plan)、Evidence 六来源强制、Approval 状态机 (5 态终态可逆, 高风险自动绑定
  人工审批)、三类挡板 (产品冲突/架构变更/Scope 扩展)。
- **Provider Intelligence (Phase 8A–8B3)**: LLM Provider 抽象 (统一 I/O + Adapter +
  Registry)、四因素可解释推荐 (Capability/Cost/Performance/Experience)、Cost/Usage/
  Performance 聚合, 换 Provider = 改配置。
- **Experience Loop (Phase 10A-4)**: 成功/失败/审批经验五域沉淀, 30 天半衰期新鲜度
  衰减, 推荐回馈 "影响但不支配" (冷启动中性分, 不惩罚新候选)。
- **可观测与恢复**: 事件是唯一事实源 (append-only SQLite), Dashboard 20 视图,
  六域指标, checkpoint + 事件回放断点续跑。
- **CLI**: 23 命令组 / 77 叶子命令。

### Validation

- **MarkPad 真实项目验证 (Phase 12B)**: 表格编辑器增强需求走通
  `Idea→Research→PRD→[审批]→UI→[审批]→Architecture→Task→Experience` 完整闭环 —
  **34 事件 / 6 Artifacts / 2 经验 / 2 次人工审批 / Core 零修改**。
  详见 [docs/real-world-validation.md](./docs/real-world-validation.md)。
- **测试**: **4111 pytest 全绿** (24 个域, 基线只增不减) + **92 Vitest** (Web UI
  12 文件)。分域明细见 [docs/quality-report.md](./docs/quality-report.md)。
- **架构冻结审计 (2026-08-06)**: 四层依赖单向向下、无循环 import、Extension 隔离
  复核通过 (docs/system-architecture-review.md)。
- **流程**: Phase 0 → 14B, **48 次提交**, 每阶段独立可交付、可回退;
  ADR-0001–0035 (docs/adr/), 设计文档 30+ 篇。

### Known limitations (v1.0.0-rc1 边界)

本版本为**单机、单人、开源核心**里程碑, 以下能力明确不在 v1.0 范围:

- **无 SaaS / 多租户托管**: 无云端托管服务, 无租户隔离、无账号体系; 部署与运维由使用者自理。
- **无身份认证/授权**: CLI 与 Human Console 均为本机信任模型, 无登录、无 RBAC;
  请勿直接暴露到公网。
- **无支付/计费**: 不包含用量计费、账单、订阅; Provider 成本仅用于推荐评分与观测。
- **无市场 (Marketplace)**: 无 Skill/Agent/Workflow 的在线分发市场; 共享靠 git 分发
  + Extension 声明式注册。
- **反馈闭环为设计稿**: docs/feedback-model.md 定义接口契约, 采集/分类后台留待未来
  Feedback 阶段实现 (本阶段不落库、不建服务)。

---

## 版本记录约定

- 自 v1.0.0-rc1 起维护本文件; 每阶段交付追加一节 (Keep a Changelog:
  Added / Changed / Fixed / Removed)。
- 测试基线随阶段只增不减 (pytest 全量绿 + Vitest 全量绿为合入门槛)。

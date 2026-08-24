# AI Software Factory — 架构评审报告

> 日期: 2026-08-06 | 状态: 评审完成, 等待确认
> 背景: 20 Phase 完成 (2159 tests), 文档体系重构后, 重新评估产品定位

## 1. 是否偏离初始目标?

**结论: 没有偏离, 而是演进加深。**

| 初始目标 | 当前实现 | 判定 |
|:---------|:---------|:----:|
| 管理多个软件项目 | Workspace Layer (6A) | ✅ 超出预期 |
| 统一调度 AI 工具 | Runtime Adapter + Orchestration (4B/4C) | ✅ 超出预期 |
| 保存项目上下文 | Event System + Checkpoint + Git/Change (1/4C-3/6C/6D) | ✅ 超出预期 |
| (演进) 理解项目状态 | Change Intelligence + L4 Validation | ✅ 新增价值 |
| (演进) 任务生命周期 | Task→Workflow→Assignment→Execution→Validation→Recovery | ✅ 完整闭环 |
| (演进) 人工审核节点 | 三挡板/Decision Gate/validate 退出码 | ✅ 已内建 |
| (演进) 任意阶段接入 | vision.md 理念 + 各 Layer | ✅ 方向确认 |

**核心价值排序确认**（与用户 7 点一致）:
1. 管理项目上下文 (Event 唯一事实源)
2. 理解项目当前状态 (Git/Change/Validation)
3. 调度不同 AI 能力 (Runtime/Orchestration)
4. 管理任务生命周期 (Task/Workflow/Execution)
5. 保存过程和决策历史 (Event/ADR/Checkpoint)
6. 支持人工审核节点 (三挡板/approval)
7. 支持任何阶段接入 (vision)

**定位演进**: "开发助手" → "AI 工作生命周期管理平台"
类比: Jira(任务) + Jenkins(流程) + K8s Dashboard(可观测) + Confluence(知识) + CI/CD(验证) 的 AI 时代对应。

## 2. 统一抽象模型评审

```
Agent (角色) ── Skills (能力)
     │
     ├── MCP Tools (外部工具: GitHub/Jira/Figma/AWS)
     │
     └── Runtime (执行方式: Hermes/Codex/Claude/Local)
```

**结论: 合理, 符合长期扩展。** 与当前实现的映射:

| 模型 | 当前状态 | 差距 |
|:-----|:---------|:-----|
| Agent 角色 | ✅ AgentRegistry (role/skills/status) | — |
| Skills 能力 | ✅ SkillRegistry (category/capabilities) | — |
| MCP 工具 | ❌ 未实现 (mcp/ 目录空) | 新增层 |
| Runtime 执行 | ✅ RuntimeAdapter (echo/hermes) | 需 per-agent runtime 偏好 |
| LLM Provider | ❌ 未抽象 (Hermes 硬绑定) | Phase 8 核心 |

**关键设计建议**: `runtime.preferences` (Phase 6A 已建字段) 承载 per-role runtime 偏好:
```yaml
runtime:
  architect:  { provider: claude }
  developer:  { provider: codex }
  tester:     { provider: hermes }
```
Assignment/Execution 已按 runtime_id 解析 → 只需 Provider 层实现。

## 3. Product Intelligence 独立 Layer 设计

**原则**: Core 提供通用原语 (Task/Workflow/Event/Validation), 各 Layer 是使用原语的高层编排 — 不破坏 Core。

```
Product Intelligence Layer (Phase 9)          [高层编排]
  Idea → Market Research → Product Analysis → PRD → [Human Approval] → UI → Architecture → Tasks
       │
       └── 复用 Core: task.create / workflow.run / event.log / validation / dashboard
```
接入方式: 与 orchestration/changeflow 同模式 (新模块 + CLI 扩展 + Dashboard 视图 + 复用 Core API)。人工批准 = 既有 validate 退出码/三挡板语义。

## 4. 任意阶段接入确认

| 接入点 | 输入 | 输出 | Layer |
|:-------|:-----|:-----|:------|
| Idea 阶段 | 一个想法 | 市场分析/PRD/UI/任务 | Phase 9 Product Intelligence |
| 已有代码 | Git 项目 | Understanding Report (阶段/技术栈/架构/缺失/风险/建议) | Phase 7 Project Understanding |
| 开发中项目 | 任务/仓库 | 继续 Task/Workflow | ✅ 已有 (Core) |
| 生产项目 | 服务 | Monitoring/Alert/Maintenance | Phase 10 Operations |

**生命周期模型确认合理**: 12 阶段 + 任意节点接入 (Factory 理解当前状态并继续)。

## 5. Git 可选化分析

**结论: 同意 — Git 应保持可选能力, Core 零依赖。**

- 现状已基本满足: git/ 独立模块; change/changeflow 依赖 git; 但 task/workflow/execution Core **零 Git 依赖** ✅
- 未来方向: git 作为 Skill/MCP/Integration 注册 (如 github MCP), change intelligence 经接口注入而非硬依赖
- 行动: 文档明确声明 "Core 零 Git 依赖, Git=可选能力"

## 6. Web UI 方向

**结论: 方向正确 — Dashboard 给人审核用 (Human Approval 是核心价值)。**

- CLI 保留: 工程师主入口
- Web UI (未来): 审核入口 — 查看状态/审核 AI 输出/确认 PRD/确认 UI/审核执行/查看 Metrics
- 架构: Factory API (FastAPI 薄层: 只读 + 审批动作) → Core; Frontend (React/Vue 或轻量 HTML+JS)
- 定位: 人类审核台 (Approval Console), 不是给 AI 用
- 不实现, 仅设计 (规划入 roadmap)

## 7. 文档修改计划

| 文档 | 修改点 |
|:-----|:-------|
| vision.md | 定位更新: AI 工作生命周期管理平台; 统一抽象 (Agent/Skill/MCP/Runtime/Provider); Git 可选 |
| design-principles.md | 强化: AI 可替换 (Provider); Git 可选能力; 人类审核台; 任意阶段接入 |
| lifecycle-model.md | 12 阶段确认 + 4 类接入点细化 (Idea/已有代码/开发中/生产) |
| roadmap.md | Phase 7-10 排序: Project Understanding → LLM Provider → Product Intelligence → Operations; + Web UI (人类审核台) 规划 |
| README.md | 定位更新 + 统一抽象模型图 |

## 8. 结论

当前架构**方向正确, 无根本性缺陷**。核心动作:
1. 确认定位升级 (生命周期管理平台)
2. 明确统一抽象 (Provider 层是最大差距 → Phase 8)
3. 声明 Git 可选 (Core 零依赖已满足)
4. 规划 Product Intelligence / Web UI 为独立 Layer (不破坏 Core)
5. 文档更新反映以上 (本次执行)

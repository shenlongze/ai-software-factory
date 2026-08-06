# AI Software Factory — 文档导航 (新人 5 分钟)

> 归属: Phase 14A | 目的: 给新人的**入口索引** — 先看什么、去哪看, 而不是罗列全部文档。
> 完整路线图与阶段状态见 [docs/roadmap.md](./roadmap.md) 与 [docs/design/](./design/README.md)。

## 5 分钟路径 (新人必读)

1. [README.md](../README.md) — 项目是什么 (Vision / Problem / Solution / 四条核心理念)
2. [architecture-overview.md](./architecture-overview.md) — 三区 · 11 层架构总览 (先有地图)
3. [project-structure.md](./project-structure.md) — 代码在哪、怎么长这样
4. [adr/0031-decision-intelligence.md](./adr/0031-decision-intelligence.md) + [adr/0033-experience-loop.md](./adr/0033-experience-loop.md) — 认知层两个关键 ADR (决策/经验)
5. [configuration-model.md](./configuration-model.md) — 怎么配置、配在哪
6. [quality-report.md](./quality-report.md) — 质量基线: 4111 pytest + 92 Vitest, 全绿才算完成

验证命令 (仓库根目录): `pytest -q` (4111) / `cd factory-console/web/frontend && npx vitest run` (92)。

---

## 分类导航

### Architecture — 架构

| 文档 | 一句话 | 链接 |
|:-----|:-------|:-----|
| 架构总览 | 三区 (Core/Extension/Human) · 11 层, 全系统地图, 先读这篇 | [architecture-overview.md](./architecture-overview.md) |
| 架构审计报告 | Phase 12A 四层系统审计: 与代码逐项对照的结论 | [system-architecture-review.md](./system-architecture-review.md) |
| 项目结构 | 目录结构 + 各包职责, 找代码用这篇 | [project-structure.md](./project-structure.md) |

### Design ADR — 架构决策

- **ADR 目录**: `docs/adr/` 编号 0001–0035, 每个 ADR = 一个决策 (为什么这么做, 而不是怎么做)。
  从 [adr/0001-eventtype-and-events-schema.md](./adr/0001-eventtype-and-events-schema.md) 开始按需阅读;
  认知层推荐先读 0030–0035 (Intelligence → Decision → Recommendation → Experience → Human Console)。

### User Guide — 用户指南

| 文档 | 一句话 | 链接 |
|:-----|:-------|:-----|
| 配置模型 | 全部配置项与分层 (全局/项目/任务), 怎么改配置 | [configuration-model.md](./configuration-model.md) |
| Human Console | 人类审核台 (普通/专业模式): 看状态、看推荐、批准/驳回 | [human-console-model.md](./human-console-model.md) |

### Demo — 演示与验证

| 文档 | 一句话 | 链接 |
|:-----|:-------|:-----|
| 预约系统演示 | Idea→Development 端到端演示场景, 跟着跑一遍最快理解系统 | [demo-scenario.md](./demo-scenario.md) |
| 真实项目验证 | MarkPad 全生命周期验证记录 (34 事件 / 2 经验 / 6 Artifacts) | [real-world-validation.md](./real-world-validation.md) |

### Development — 开发参与

| 文档 | 一句话 | 链接 |
|:-----|:-------|:-----|
| 贡献指南 | 提 PR 的流程、规范与验收标准 (Phase 14A 配套) | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| 质量报告 | 质量基线: 测试数量、覆盖率、已知缺口, 改代码前先看 | [quality-report.md](./quality-report.md) |

### Business — 商业与场景

| 文档 | 一句话 | 链接 |
|:-----|:-------|:-----|
| 商业定位 | Open Source Core + 商业服务的分层策略 (只分析不实现) | [business-positioning.md](./business-positioning.md) |
| 应用场景 | 5 类目标场景与典型用法 (团队研发/独立开发者/... ) | [use-cases.md](./use-cases.md) |

### 治理 — 许可与安全

| 文档 | 一句话 | 链接 |
|:-----|:-------|:-----|
| License 决策 | 为什么 Apache-2.0 而非 MIT | [license-decision.md](./license-decision.md) |
| 行为准则 | 社区行为规范与举报渠道 | [CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md) |
| 安全策略 | 漏洞报告渠道 / 支持版本 / 响应时间 | [SECURITY.md](../SECURITY.md) |
| 反馈闭环设计 | 用户反馈 → Decision → Experience 的接口设计 (未实现) | [feedback-model.md](./feedback-model.md) |

---

## 深入阅读 (按需)

- 生命周期: [lifecycle-model.md](./lifecycle-model.md) (12 阶段) / [workflow-model.md](./workflow-model.md)
- 领域模型: [agent-model.md](./agent-model.md) / [skill-model.md](./skill-model.md) / [memory-model.md](./memory-model.md)
- 认知层: [intelligence-layer-model.md](./intelligence-layer-model.md) / [decision-intelligence-model.md](./decision-intelligence-model.md) / [recommendation-engine-model.md](./recommendation-engine-model.md) / [experience-learning-model.md](./experience-learning-model.md)
- 设计与阶段计划: [docs/design/README.md](./design/README.md)

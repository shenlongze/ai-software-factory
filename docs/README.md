# AI Software Factory — 文档导航（2026-08-21 更新）

> 给新人/协作 agent 的入口索引：先看什么、去哪看。历史/被取代文档见 [docs/archive/](./archive/README.md)。

## 5 分钟路径（必读，按顺序）

1. **完整产品方案书**（仓库根 `AI Software Factory — 完整产品方案书.md`）— **主文档**：21 章蓝图
   （定位/架构/能力/治理/学习/工具/行业/交互/路线/术语/竞品/自我进化/合规/安全/企业级）+ **§1.4 当前实现状态对照**（✅/🚧/📐 锚定代码）
2. **总体规划** [MASTER-PLAN-2026-08.md](./MASTER-PLAN-2026-08.md) — AI Company OS 执行主线（业务流/数据流/CLI/API/里程碑 M1-M7）
3. **节点详设** [MASTER-PLAN-DETAIL-2026-08.md](./MASTER-PLAN-DETAIL-2026-08.md) — 以链路为主线的节点级设计
4. **[README.md](../README.md)** — 项目是什么（Vision / Problem / Solution）
5. **[CHANGELOG.md](../CHANGELOG.md)** — 版本与变更（当前 **v1.1.10**）

## 当前状态（2026-08-21）

- **版本**: v1.1.10 · 三部门循环（Claude=产品 · Hermes=架构/Review · Codex=工程）
- **已交付**: M1 内核切片（repo 模式 + 工具发现 + 真 MCP）· M1a 证据包+分级审批 · M1b 积压清道夫
- **测试基线**: 全量回归绿（11856+）
- **下一步**: M2 员工内核（AgentEntity + HandoffBus）· 三部门循环 Claude 用户价值评估

## 分类导航

| 区域 | 入口 | 一句话 |
|:-----|:-----|:-------|
| 主蓝图 | 完整产品方案书（仓库根） | 21 章 + 状态对照 + 可行性取舍 |
| 执行计划 | [MASTER-PLAN-2026-08.md](./MASTER-PLAN-2026-08.md) | M1-M7 里程碑/版本/验收 |
| 节点详设 | [MASTER-PLAN-DETAIL-2026-08.md](./MASTER-PLAN-DETAIL-2026-08.md) | 链路 + 节点输入/输出/接口 |
| 架构设计 | [docs/design/](./design/README.md) · [docs/architecture/](./architecture/README.md) | 系统/CLI/运行时设计 |
| 审计与现状 | [docs/audit/](./audit/README.md) · [docs/architecture/capability-audit/](./architecture/capability-audit/README.md) | 真实能力审计 |
| 发布与运维 | [USER_GUIDE.md](./USER_GUIDE.md) · [DEPLOYMENT.md](./DEPLOYMENT.md) | 安装/使用/部署 |
| 历史归档 | [docs/archive/](./archive/README.md) | 已取代/历史文档（不删除） |
| 每轮交付 | [docs/sprint10/](./sprint10/README.md) | S10-0XX 设计与报告 |

## 文档纪律

- **主文档唯一**：规划以 MASTER-PLAN 为准，能力以完整产品方案书为准，旧 roadmap 已归档
- **状态锚定代码**：任何能力文档标注 ✅/🚧/📐（见方案书 §1.4），防"设计与实现漂移"
- **归档不删除**：历史文档移 docs/archive/，保留内容与引用

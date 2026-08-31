# K8 /api/board Audit

> 日期: 2026-08-29 | 纯审计

## 真实行为
- GET /api/board → **返回 HTML 视图页** (AI Factory 自身项目视图), 非 JSON API
- 存在 /api/board/* 10 个子端点 (chain/default/doc/docs/graph/split/summary/tasks/timeline)

## 回答
| 问题 | 答案 |
|------|------|
| 数据来自哪个 Core Entity? | 旧 workspace project (S0.5-era), 非 S43 unified_contract |
| 是否来自 SSOT? | 是 (project 存储), 但是旧 SSOT |
| 是否是 Projection? | 是 (board 视图投影) |
| 谁消费? | AfMonitorPage / DashboardPage (旧页面) |
| 与 Control Tower 重叠? | **是** (AfMonitorPage 监控 ≡ ControlTowerPage 塔) |
| 与 Project/Sprint/Task 重叠? | 部分 (旧项目视图 vs 新 projects-os) |
| 应否成为正式 OS API? | **否** — 历史遗留 HTML 控制台 |
| 应否 deprecated? | **是** (建议, 待架构决策) |
| 应否重命名/收敛? | 收敛到 /api/ops/* + /api/projects-os/* |

## 结论
/api/board = 历史遗留控制台。新 Human Console 用 /api/ops/* + /api/projects-os/* (SSOT 投影, S43 Contract)。建议: 专业视图迁移后 deprecate。

# ADR-0034 — Phase 11A: Human Console Layer

> 日期: 2026-08-06 | 状态: Accepted

## 背景

将 Factory 提升为普通用户可用的产品入口 (Human Control Center)。Phase 11A 只建立 Backend Console Layer, 11B 再开发 Web UI。

## 决策

### 1. factory-console/ 独立 Extension
不污染 factory-core。Console = Human Layer: 只读 Core/Extension 数据, 零写操作。

### 2. 只读 API (路由函数, 无 Web 依赖)
6 路由 (projects/lifecycle/approvals/decisions/recommendations/experience/providers) 纯函数返回 Pydantic 响应模型; 未来 11B 挂 FastAPI 薄层。

### 3. ConsoleDashboard 七域
active_projects/pending_approvals/running_agents/recent_decisions/cost_summary/experience_summary/activity; Service 失败安全 (store 可选注入)。

### 4. 普通模式 / 专业模式
默认简单 (项目→状态→需决定→为什么推荐); 展开专业 (Provider/Agent/Skill/Cost/Evidence/Event)。

### 5. 边界
Console 只能通过 Event/Artifact/Decision/Recommendation/Experience/Approval 读状态; 禁自动批准/修改 Decision/权重/替代 Human。

### 6. 收尾裁定
4 实现 bug (lifecycle_status 层级/list_approvals 兜底/get_decision 兜底/_recommendation_factors 宽容) + SECTIONS ClassVar (pydantic v2); 事件枚举 +3 (134→137)。

## 验证

- pytest 4069 全绿 (3918 + 151)
- CLI 冒烟: console dashboard 七域汇总 + console approvals 清单
- Core 零修改 (仅 events 枚举)

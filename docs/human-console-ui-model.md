# Human Console — UI 模型 (Phase 11B)

> 日期: 2026-08-06 | 关联: ADR-0034 (11A Console Layer) / ADR-0035 (11B Web UI)
> 定位: 把 AI Software Factory 从"工程师的 CLI"提升为"普通用户可用的产品入口"的交互模型。

## 1. UI 理念

### 1.1 人是决策者, AI 是执行者
Console 的全部界面围绕一条铁律设计: **执行权永远在人工一侧**。
AI 产出推荐与证据, 人做决定。Web UI 不提供任何写路径
(Permission Boundary) — 审批/决定/创建等动作都指向既有引擎的决策通道
(CLI 状态机), 界面只负责"看得懂、判得准"。

### 1.2 默认简单, 渐进披露 (Progressive Disclosure)
用户看到的第一屏是普通模式: 只有"项目 → 状态 → 需要我决定什么 → 为什么这样推荐"。
复杂域 (Provider / Agent / Cost / Evidence / Event) 折叠在专业模式中,
一键展开, 不打扰默认路径。

### 1.3 只读投影, 失败安全
所有数据来自 11A Console API 的只读投影; 后端失败安全
(缺 store → 空数据), 前端冷启动不臆造 (无数据 → '—' 或空态)。

### 1.4 中文优先的产品文案 + 英文技术术语并存
产品层文案 (导航/提示/空态) 用中文; 领域术语 (Provider / Approval / Evidence)
保留英文, 与后端事件/CLI 术语一致, 降低学习成本。

## 2. 普通用户模式 (Simple)

目标用户: 非工程师的团队负责人/业务方。只回答四个问题:

1. **现在有几个项目在跑?** — Dashboard hero: "正在管理 N 个项目"
2. **AI 当前在做什么?** — 项目工作区 (Lifecycle): 当前阶段 + 状态
3. **有什么需要我决定?** — 待审批数 + 审批中心 (Confidence / Risk / Evidence)
4. **为什么这样推荐?** — 决策视图: 候选评分 + 推荐 + 原因 (前 2 条证据)

普通模式隐藏: Provider 目录、成本明细、Agent 内部、事件流、证据全链。
导航仅 5 项 (Dashboard/项目/审批/决策/智能)。

## 3. 专家模式 (Expert)

目标用户: 工程师/管理员。在普通模式之上展开:

- **Providers 导航** 出现 (Provider 目录: 能力/成本/性能/经验/调用数)
- Dashboard 追加 成本汇总 / 运行中 Agent / 最近活动 (事件审计流)
- 决策视图显示 Capability/Cost/Performance/Experience 因子细分
- 证据链展开全部; 审批显示 by 来源
- 智能视图显示推荐证据链

切换方式: 右上角 segmented control (普通模式默认, 状态仅前端内存,
刷新回到普通模式 — 安全默认)。

## 4. 页面地图

| 页面 | 数据源 (全部 GET) | 普通模式 | 专家模式 |
|---|---|---|---|
| Dashboard | /api/dashboard | 项目数/待决定/最近决策 | + 成本/Agent/活动 |
| 项目 | /api/projects | 表格 + 点击进工作区 | 同左 |
| 项目工作区 | /api/projects/{id}/lifecycle | 阶段/下一步/待审批 | 同左 |
| 审批 | /api/approvals | 卡片 + 只读决定指引 | + by 来源 |
| 决策 | /api/dashboard + /api/decisions/{id} | 候选/推荐/原因 | + 因子细分 |
| 智能 | /api/experience /api/providers /api/recommendations /api/dashboard | 经验/Provider/Agent/推荐 | + 证据链 |
| Providers | /api/providers | 隐藏 | 目录表 |

## 5. 只读交互模式 (Permission Boundary 的 UI 表达)

界面上所有"动作"按钮 (Approve / Request Change / Reject / 创建新想法)
都只打开一个**只读指引 Modal**: 说明该操作的真实执行通道
(如 `factory approval decide`), 强调"本操作不向系统写入任何状态"。
前端 api client 只暴露 GET 方法; 后端 adapter 不注册任何写路由 —
双保险, 测试锁定。

## 6. 未来商业化入口 (预留, 不实现)

产品化演进方向 (Phase 11B 不实现, 仅保持架构不挡路):

- **用户系统**: 普通/专家模式可升级为 角色权限 (Viewer / Approver / Admin)
- **多租户**: factory-console 独立 extension + 只读 API 天然可横向加
  auth/路由前缀, 不污染 factory-core
- **Marketplace / SaaS**: Web UI 是天然商业化入口 — Dashboard hero
  的"创建新想法"按钮预留为未来写通道的 UI 锚点; 决策/审批视图
  是付费增强 (审计/协作/报告) 的挂载点
- **付费墙策略**: 普通模式免费 (只读价值), 专家模式/协作/审计导出 付费

## 7. 验证

- 前端 Vitest ≥80% 覆盖 (component 渲染 / Simple-Expert 切换 / Approval
  交互 / Decision 渲染 / API mock / permission)
- npm run build (tsc --noEmit + vite build) 通过
- 冒烟: uvicorn 起 adapter → /api/dashboard 200 JSON; 静态托管 SPA

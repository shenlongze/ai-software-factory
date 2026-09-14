# Open-Core Boundary — AI Software Factory

> 开源边界声明(S10-035 Task 006 最终版)。洋葱式开源: 外层开源获客, 内层闭源变现。

## Community Edition(Open Source, Apache-2.0)

| 模块 | 说明 |
|---|---|
| Kernel | Identity / Config / Event / Runtime / Extension 接口(核心, 开源) |
| CLI | 统一入口(init/doctor/config/start/service/project/run/demo/...) |
| Runtime | Agent Runtime / Execution Loop / 沙箱 |
| Basic Router | 五层决策链(User > Agent/Skill > Project > System > Fallback) |
| Agent | 单 Agent 执行(角色/技能/权限链基础) |
| Skill | 技能注册 + 基础权限链 |
| Model Catalog | Provider→Model 元数据 |
| Control Plane | providers.json 生命周期 + api_key_ref |
| 全事件审计 | append-only 事件库 + audit 查询 |
| Demo Workspace | 隔离演示环境 |

## Enterprise(Closed Source, Future)

| 模块 | 说明 |
|---|---|
| Governance | 企业级治理引擎(审批策略/流程编排) |
| RBAC | 角色权限控制(多用户/多租户) |
| Compliance | 合规报告/审计导出/策略审计 |
| Enterprise RAG | 企业知识库(权限集成/跨项目检索) |
| Analytics | 成本分析/用量报表/治理仪表盘 |
| 智能路由 | usage 反馈学习(Phase 5) |
| Multi-Agent 协作 | 团队级编排 |
| Marketplace | 插件市场 |

## 边界原则

1. **洋葱式**: 开源外层(CLI/Router/Agent/审计), 闭源内层(治理/合规/分析)
2. **Community 完整可用**: 开源版可独立安装运行真实 AI 任务
3. **Enterprise 值得付费**: 治理/RBAC/合规是企业采购理由
4. **不夸大**: 本文件只列已实现(Community)与规划(Enterprise); Enterprise 未实现不宣称

## 当前状态

- Community: v0.1.0(可安装可运行, 8148 tests green)
- Enterprise: 规划中(无代码, 不夸大)

## 联系方式

- Issues: https://github.com/shenlongze/ai-software-factory/issues
- Enterprise 咨询: 通过 GitHub 联系

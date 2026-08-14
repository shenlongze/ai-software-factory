# S10-030 Task 005 — Open Source Boundary

> 日期:2026-08-14 | Sprint: S10-030 MVP Release | 战略设计,未修改代码
> 目标:设计 Community Edition(开源)与 Enterprise(闭源)边界,落实洋葱式开源战略

---

## 1. 边界原则

1. **洋葱式**:开源外层(可独立/无核心价值泄露),闭源内层(治理/编排核心)
2. **开源获客,企业变现**:Community 足够好用(吸引用户),Enterprise 值得付费(治理/合规)
3. **不破坏平台**:开源部分独立可用,但完整价值需 Enterprise
4. **代码现实**:当前单仓库;边界 = 目录/模块级(不拆仓库,先定边界)

## 2. 模块归属

### 2.1 Community Edition(开源)

| 模块 | 理由 |
|---|---|
| CLI(init/doctor/config/start/service/demo) | 获客入口,无核心价值 |
| LLM Control Plane(providers.json) | 配置管理,无壁垒 |
| Model Catalog(models.json) | 数据,无壁垒 |
| **AI Router v1.1(五层链)** | 决策框架本身;智能增强(usage 学习)留企业 |
| Agent Runtime(单 Agent 执行) | 基础执行能力 |
| Skill System(基础权限链) | 能力包基础 |
| 真实执行链(Task→LLM→Artifact) | 核心价值但 Community 需要体验 |
| MCP 适配 | 生态扩展 |

### 2.2 Enterprise(闭源/付费)

| 模块 | 理由 |
|---|---|
| **Governance Engine** | 企业核心卖点:审批策略/权限/RBAC |
| **Organization(组织域)** | 公司/员工/角色管理(企业多租户) |
| **Policy Engine** | 策略引擎(动态规则替代硬编码) |
| **Audit 增强** | 审计浏览器/合规报告/导出 |
| **Enterprise RAG** | 跨项目知识/权限集成(区别于社区单项目) |
| Multi Agent 协作 | 团队级编排 |
| 智能路由(usage 反馈学习) | Router 增强(Phase 5) |
| 审计/合规 API | 企业集成 |
| 企业部署包(Docker/离线/支持) | 交付形态 |

## 3. 边界表(详细)

| 能力 | Community | Enterprise |
|---|---|---|
| 单 Provider 配置 | ✅ | ✅ |
| 多 Provider + Router 五层 | ✅ | ✅ |
| Router 智能增强(学习) | ❌ | ✅ |
| 单 Agent 执行 | ✅ | ✅ |
| Multi Agent 协作 | ❌ | ✅ |
| 基础审批门 | ✅ | ✅ |
| 策略引擎(动态规则) | ❌ | ✅ |
| 组织/角色/多租户 | ❌(单机) | ✅ |
| 事件审计 | ✅(基础查询) | ✅(浏览器+报告+导出) |
| RAG | 单项目(未来) | 企业级+权限 |
| CLI | ✅ 完整 | ✅ 完整 |
| UI | ✅ 基础 | ✅ 增强(审计/治理视图) |
| Docker 部署 | ❌(源码) | ✅ |
| 支持 | 社区 | 企业 SLA |

## 4. 开源许可建议

| 选项 | 分析 |
|---|---|
| MIT | 最宽松,获客最易;核心闭源部分不受影响(代码物理分离) |
| Apache 2.0 | 宽松+专利保护;企业友好 |
| AGPL | 强 copyleft;阻碍商业化(不适合) |
| BSL(商业源码许可) | 源码可看但商用受限;过渡方案 |
| Open Core(推荐) | **核心(编排)闭源 + 外围开源(洋葱式)** — 与既有战略一致 |

**建议:Community 用 Apache 2.0(获客友好),Enterprise 闭源(付费)。**
(与 Dify/GitLab CE-EE 模式一致;不选 AGPL 避免阻碍企业采用)

## 5. 仓库/分发策略

```
当前: 单仓库 (私有)
方案 A (推荐, MVP 期): 单仓库转公开, Community 代码全可见, Enterprise 模块不在仓库
  - 简单;企业模块本地私有开发
  - 风险: 企业模块与社区耦合(需边界纪律)

方案 B (成熟期): 拆多仓库
  - ai-factory-core (公开, 洋葱外层)
  - ai-factory-enterprise (私有, 洋葱内层)
  - 独立产品仓 (ai-router 等)
  - 优点: 边界清晰;缺点: 维护成本
```

**MVP 用方案 A(单仓库公开),模块独立产品化时转方案 B。**

## 6. 开源边界实施原则(不实现,指导未来)

```
1. 目录级边界: factory-console/{gov,enterprise}/ 等标记 Enterprise 目录
2. Enterprise 模块不依赖 Community 私有实现(只依赖稳定 API)
3. 发布时: Community tarball 排除 Enterprise 目录
4. 测试: Enterprise 模块测试独立标记(不影响社区 CI)
5. 文档: 开源版 README 明确"哪些功能在 Enterprise"
```

## 7. 商业转化路径

```
开源用户 (Community)
  → 体验 5 分钟 (README)
  → 个人项目 (免费够用)
  → 团队需求 (Multi Agent / 组织) → Enterprise 试用
  → 企业合规 (治理/审计/部署) → Enterprise 采购
```

## 8. 结论

**开源边界 = 洋葱式开源落地:Community(CLI/Router/Agent/Skill)开源获客,Enterprise(Governance/组织/策略/审计/企业 RAG)闭源变现。**

- 与 S10-029 商业模式一致(开源获客 → Enterprise 变现)
- MVP 期:单仓库转公开(方案 A),Enterprise 模块标记后不提交
- 成熟期:独立产品仓(方案 B,配合 Router 独立化)

---

> Task 005 完毕 | 开源边界设计完成 | Community 开源获客 / Enterprise 治理变现

# 项目目录结构 v0.3 候选 + 评审记录

> 日期: 2026-09-13 | 性质: **候选方案 · 未冻结 · 非事实源**（讨论中，勿作为依据引用）
> 来源: Founder 设计稿（2026-09-13）
> 评审: Hermes（架构层评审，未改任何代码）
> 上一版: `docs/ssot/architecture.md` v0.2（已冻结，7 层 + R1-R8）

---

## ⚠️ 前置：物种裁决（2026-09-13，Founder 决定）

**决定：选物种 B —— 可编排 AI 操作系统。承认当前 0 实现，重新做能力模型 + 编排引擎。**

取证（三条互相印证，说明现状是物种 A）：

| 证据 | 内容 |
|------|------|
| `factory-console/golden_path.py` | 模块级函数序列 `generate_prd → approve_prd → generate_plan → approve_plan → execute_approved`，写死的固定顺序，无编排器 |
| `factory-console/canonical_golden_path.py` | `detect_lifecycle(text)` + `describe()` 返回 `stage` —— 会话是**固定生命周期的状态机**，只判断"走到第几步" |
| `factory-console/os_core_resolution.py` | `_resolve(required_capability_refs)` 返回 `matches`，`match_type: "deterministic"` —— **资格查表**，不是能力组合 |

**文档矛盾（待重写）**：
- `docs/AI Software Factory — 产品说明书（全产品线）.md` §0.2 = **11 步固定线性链** + 两个审批门（物种 A）
- `docs/ssot/product.md` §4 = `Idea → 表达 → 理解 → 编排 → 执行 → 验证 → 交付`，且开篇写"无固定流程（可编排）"（物种 B）

**直接后果（三条）**：
1. 现有 199,769 行生产代码（含 canonical 主链）**不是 B 的地基**，是 B 下面**一个应用**（Software Factory）的实现。此前"保留 canonical 主链作为地基"的判断作废。
2. 说明书 §0.2 的 11 步链**降级为"第一个应用（SF）的流程定义"**，不再是"用户主链"。
3. 本文件以下的结构讨论（v0.3 候选）**前提已变**：需按 B 重新审视，其中 `contracts/kernel/capability.py` + `core/capability/` + `services/orchestration/` 从"可选域"变为**必须最优先设计**。

---


## 一、候选结构原文（Founder 设计稿，逐字保留）

```
ai-factory-os/
│
├── src/ai_factory_os/
│   │
│   ├── contracts/                    【契约层 · 零依赖】
│   │   ├── domain/                     域契约
│   │   │   ├── identity.py               人 / Agent / Service
│   │   │   ├── organization.py           公司 / 部门 / 角色 / 成员
│   │   │   ├── authorization.py          权限
│   │   │   ├── project.py                项目 / 里程碑
│   │   │   ├── work.py                   WorkItem / Task
│   │   │   ├── execution.py              Run / Record
│   │   │   ├── artifact.py               产出物
│   │   │   ├── template.py               模板
│   │   │   ├── notification.py           通知
│   │   │   ├── governance.py             Policy / Approval / Budget
│   │   │   ├── secret.py                 凭证
│   │   │   ├── schema.py                 Schema 版本
│   │   │   └── i18n.py                   国际化
│   │   ├── kernel/                     内核契约
│   │   │   ├── conversation.py           会话
│   │   │   ├── intent.py                 Intent（会话↔能力唯一语言）
│   │   │   ├── capability.py             能力注册
│   │   │   ├── scheduler.py              调度
│   │   │   ├── node.py                   节点
│   │   │   ├── events.py                 事件
│   │   │   └── plugin.py                 插件
│   │   ├── ai/                         AI 契约
│   │   │   ├── prompt.py
│   │   │   ├── model.py
│   │   │   ├── agent.py
│   │   │   ├── tool.py
│   │   │   └── memory.py
│   │   ├── products/                   产品契约
│   │   │   ├── routing.py                LLM 智能路由
│   │   │   ├── audit.py                  审计/证据链
│   │   │   ├── data_governance.py        数据治理
│   │   │   ├── governance_platform.py    治理平台
│   │   │   ├── backlog_sweeper.py        积压清道夫
│   │   │   ├── knowledge_base.py         企业知识库
│   │   │   ├── channels.py               消息渠道
│   │   │   └── factory_spec.py           行业工厂模板
│   │   └── errors.py
│   │
│   ├── core/                         【内核】
│   │   ├── conversation/               ★ 主控制面
│   │   │   ├── session/
│   │   │   ├── understanding/
│   │   │   ├── intent/
│   │   │   ├── routing/
│   │   │   ├── execution/
│   │   │   └── projection/
│   │   ├── capability/                 ★ 能力注册表
│   │   │   ├── registry/
│   │   │   ├── resolver/
│   │   │   ├── matcher/
│   │   │   └── invoker/
│   │   ├── scheduler/
│   │   ├── node/
│   │   ├── events/
│   │   └── gate/
│   │
│   ├── services/                     【服务层 · 15 域】
│   │   ├── organization/
│   │   ├── authorization/
│   │   ├── work/
│   │   ├── execution/
│   │   ├── artifact/
│   │   ├── template/
│   │   ├── scheduler/
│   │   ├── notification/
│   │   ├── secret/
│   │   ├── orchestration/
│   │   ├── compliance/
│   │   ├── governance/
│   │   ├── observability/
│   │   ├── intelligence/
│   │   │   ├── learning/
│   │   │   ├── memory/
│   │   │   ├── knowledge/{rag,graph}/
│   │   │   └── profile/
│   │   ├── platform/
│   │   │   ├── tenancy/
│   │   │   ├── quota/
│   │   │   ├── developer/
│   │   │   ├── registry/
│   │   │   ├── apikeys/
│   │   │   └── featureflag/
│   │   └── products/
│   │       ├── routing/
│   │       ├── audit/
│   │       ├── data_governance/
│   │       ├── governance/
│   │       ├── backlog_sweeper/
│   │       ├── knowledge_base/
│   │       ├── channels/
│   │       └── factory_spec/
│   │
│   ├── plugins/                      【插件】
│   │   ├── factories/
│   │   ├── agents/
│   │   ├── skills/
│   │   ├── tools/
│   │   ├── mcp/
│   │   ├── models/
│   │   ├── connectors/
│   │   ├── controllers/{browser,computer}/
│   │   ├── healers/
│   │   ├── notifiers/
│   │   ├── triggers/
│   │   └── storages/
│   │
│   ├── infrastructure/               【技术底座】
│   │   ├── storage/{postgres,vector,sqlite}/
│   │   ├── sandbox/
│   │   ├── llm/
│   │   ├── messaging/
│   │   ├── process/
│   │   ├── observability/{logging,metrics,tracing}/
│   │   ├── secrets/
│   │   ├── crypto/
│   │   └── migration/
│   │
│   ├── api/                          【HTTP 适配器】
│   │   ├── conversation/
│   │   ├── organization/
│   │   ├── authorization/
│   │   ├── project/
│   │   ├── execution/
│   │   ├── artifact/
│   │   ├── template/
│   │   ├── notification/
│   │   ├── governance/
│   │   ├── observability/
│   │   ├── intelligence/
│   │   ├── platform/
│   │   ├── products/
│   │   ├── webhook/
│   │   ├── auth/
│   │   ├── ratelimit/
│   │   └── router.py
│   │
│   └── bootstrap/                    【装配 · 唯一可 import 全部】
│       ├── registry.py
│       ├── loader.py
│       ├── wiring.py
│       └── lifecycle.py
│
├── apps/                             【会话的四种投影】
│   ├── cli/session/
│   ├── web/session/ + dashboard/
│   ├── desktop/session/
│   └── mobile/session/ + quick-intent/ + notification/
│
├── sdks/{python,js}/
│
├── tests/{contracts,architecture,services,products,integration,e2e}/
│
├── docs/{ssot,manual,archive}/
│
├── scripts/
├── bin/
├── .github/
├── pyproject.toml
├── README.md
└── LICENSE
```

---

## 二、评审结论（一句话）

**这版是三次设计里最好的一次**（products/ · platform/ · intent · sdks 四处是实质进步），
**但它把今天的病在图内复现了一遍**：已埋 5 组"同概念异名"、4 处"同名跨层"、"governance 一个概念四个家"。

---

## 三、正面（真的解决了）

| # | 进步点 | 为什么重要 |
|---|-------|-----------|
| 1 | `services/products/` + `contracts/products/` | 把"信念 6：可产品化模块第一天隔离"落成了目录（routing/audit/data_governance/knowledge_base/channels/factory_spec） |
| 2 | `services/platform/` 六个子域（tenancy/quota/developer/registry/apikeys/featureflag） | "平台是事实不是口号"首次有了代码位置 |
| 3 | `contracts/kernel/intent.py` | **这版最有价值的一行** —— 它是"无固定流程（可编排）"的载体 |
| 4 | `infrastructure/{secrets,crypto,migration,observability}` | 补上了安全 / 迁移 / 可观测三块地基 |
| 5 | `services/orchestration/` | 上一版缺失的"编排"终于有家（产品第一性能力） |
| 6 | `apps/*/session/` 统一命名 | 会话作为唯一入口在界面层落地 |
| 7 | `sdks/{python,js}/` | 支撑 CLI + API + 多端三入口 |

---

## 四、致命问题（不修则必然重演今天）

### P1 同名跨层 —— 层级语义崩塌
```
scheduler    → contracts/kernel/ · core/scheduler/ · services/scheduler/   (core 与 services 同名)
execution    → contracts/domain/ · core/conversation/execution/ · services/execution/
routing      → contracts/products/ · core/conversation/routing/ · services/products/routing/
```
core 与 services 同名并存 = 一定有人问"调度到底在 core 还是 services"。
这正是今天 `os_core_scheduler` / `ops_scheduler` / `session/scheduler` / `org/execution.plan_tasks`
四个调度打架的**图示预演**。

### P2 "governance" 一个概念四个家
```
contracts/domain/governance.py            Policy/Approval/Budget
contracts/products/governance_platform.py 治理平台
services/governance/                      治理服务
services/products/governance/             治理平台（产品化）
```

### P3 core 被塞胖 —— 会变成第二个 factory-console
`core/conversation/` 装了 6 个子域：`session · understanding · intent · routing · execution · projection`
- `understanding/`（产品理解，现 `product_understanding.py` 3000+ 行）不是内核，是**服务**
- `projection/` 不是内核，是**读侧**（且原 `projections/` 层在这版被合并进 `api/`，投影失去了独立层）
- `core/conversation/execution/` 与 `services/execution/` 撞名
- `core/capability/{registry,resolver,matcher,invoker}` 是**实现**，不是契约+默认实现

→ core 应只留：会话状态机 + Intent 解析入口。understanding / routing / projection 全部下沉。

### P4 23 个平级域 × R3 铁律 = 数学上不可满足
`services/` 实为 **16 个域**（稿子标"15 域"，实际数 16 —— 文档与内容不符，正是今天的病），
加 `services/products/` 8 个 = 24 个平级域。
R3 要求"A 不许 import B 的实现，只能走契约"。24 个域之间必然大量互调
（orchestration 要调 work/execution/artifact/notification/governance…）。
→ 必须区分**垂直业务域**（可互调）与**横切能力**（只能契约/事件），图里没有这个区分。

---

## 五、严重问题

### P5 图内已埋 5 组"同概念异名"（今天的病，原样复现）
| 概念 | 名字 A | 名字 B | 名字 C |
|------|-------|-------|-------|
| 通知 | `services/notification/` | `plugins/notifiers/` | `contracts/domain/notification.py` |
| 凭证 | `services/secret/` | `infrastructure/secrets/` | `contracts/domain/secret.py` |
| 知识 | `services/intelligence/knowledge/` | `services/products/knowledge_base/` | `contracts/products/knowledge_base.py` |
| 治理 | `services/governance/` | `services/products/governance/` | `contracts/products/governance_platform.py` |
| 工厂 | `plugins/factories/` | `contracts/products/factory_spec.py` | — |

### P6 `products/` 违反自己的信念三
信念三：**"产品依赖 OS，OS 不依赖产品。方向永远单向。"**
但 `products/` 位于 `src/ai_factory_os/` **之内** → products 成了 OS 的一部分 → OS 依赖产品。
要么移出 `src/`（如 `products/` 平级于 `src/`），要么承认这条信念不成立。

### P7 `products/` 与 OPEN-CORE.md 冲突（未和解）
`OPEN-CORE.md` 定：**闭源 Enterprise = Governance / RBAC / Compliance / RAG / Analytics / Marketplace**。
本稿把这些放进 `services/`（OS 内核域）+ `services/products/`（OS 内），
**结构上没有"开源层 / 闭源层"的切分线**。开源版与商业版如何各自组装，图里无答案。
→ 洋葱式开源（你 8年Java+6年销售那套增长战略）需要这条线，否则将来拆包 = 重构。

### P8 `contracts/contracts/domain/` 装错了东西（不是"域"）
`authorization · secret · schema · i18n · notification · template` 六项是**横切关注点**，
不是业务域。其中：
- `i18n.py` → 技术能力，应属 `infrastructure/` 或 `api/`
- `schema.py`（Schema 版本）→ 应属 `infrastructure/migration/` 侧
- `secret.py` → 应属 `contracts/infrastructure/` 侧
放 `contracts/domain/` 会让人以为"国际化是一个业务域"。

### P9 `api/` 混入横切（auth / ratelimit / webhook）
`api/` 的定义是"HTTP 适配器，只依赖 contracts"。但 `auth/` 要 secrets+crypto、
`ratelimit/` 要 storage → 必然依赖 `infrastructure`。
R6 只说"api 不许 import infrastructure.storage 具体实现"，没解决 auth/ratelimit 该去哪。
且 `api/` 有 17 个子目录与 services 一一对应 → 会变成 CRUD 反射泥潭（当前
`web/backend/fastapi_adapter.py` 单文件 8596 行就是这个泥潭的产物）。

### P10 `sdks/` 的生成方式未定
SDK 应由 `api/` 的 OpenAPI **生成**，不能手写。图里没写生成方式 → 会长成手写副本
（同 fastapi_adapter 病）。

---

## 六、仍然缺席（第三次提出）

### P11 缺"施工图"
这是**终态图**（第三版）。今天 542 文件 / 199,769 行生产代码 / `factory-console` 单包 128,352 行
如何一格一格进这棵树、每步如何保证测试全绿，图里没有一个字。
**结构图根治不了层级，施工顺序才能。**

### P12 旧链去向仍缺席
`factory-console/session/` = **128 文件 / 58,836 行**（旧 orchestrator 链，已判定 dead
但被 4 个测试文件锁活）—— 仓库最大单块质量，**图里无落点**。
注意 `apps/cli/session/`、`apps/web/session/` 是**界面层**，旧链是后端逻辑，
不能往 apps 里塞 —— 这是最容易搬错的一格。

### P13 tests/ 与 src/ 不对应
`tests/{contracts,architecture,services,products,integration,e2e}` 缺
`core/ · plugins/ · infrastructure/ · api/ · apps/` 的测试位置；
且没有"每个 services 域必须有同名 tests 目录"的守卫 —— 今天的 `tests/console/` 257 个文件
就是没有这条守卫的产物。

---

## 七、与产品定义（SSoT product.md）的对齐核查

| product.md 条目 | 本稿 | 说明 |
|---|---|---|
| ① 让一个人用自然语言组织 AI 完成复杂工作 | ✓ | |
| ② 是 OS，不是 Coding Agent/IDE/框架 | ⚠️ | 缺"禁止变成什么"的禁令清单 |
| ③ 三层身份：OS / SF=第一个Factory(CURRENT) / 其他Factory | ✗ | Factory 降级为 `plugins/factories/`，且与 `factory_spec` 异名 |
| ④ 用户主链 …→编排→执行→验证→交付→经验回流 | ⚠️ | 编排有家了 ✓；**验证/证据/结果/交付/发布/验收 仍无家** |
| ⑤ 五平台能力：会话/编排/治理/记忆学习/扩展生态 | ✓ | 五项均有落点 |
| ⑥ 核心基座 + 一切插件，不绑模型/厂商 | ✓ | |
| ⑦ 终态：创建/管理/运行/进化 AI 公司、"经营一家公司" | ✗ | **"经营"面仍为零**：无 cost/usage/计价/单位经济学域 |

---

## 八、优先级建议（供讨论）

**必须现在补（补晚=重构）**
1. 消除同名跨层（P1）+ governance 四家（P2）
2. core 瘦身（P3）：understanding / routing / projection 下沉
3. 区分垂直域 vs 横切能力（P4），否则 R3 不可满足
4. 统一名词表（P5）：通知/凭证/知识/治理/工厂 各定一个名字
5. `products/` 移出 `src/`，与 OPEN-CORE 边界和解（P6/P7）
6. `intent` 的实现落点 + 谁有权产生 Intent（当前只有契约，实现无家）

**可以后补**
- i18n / schema / secret 的契约归属微调（P8）
- api/ 横切处理（P9）、SDK 生成方式（P10）
- tests 守卫（P13）
- 私有化拓扑细则、数据治理细则、行业/OPC 模板内容

**无论如何都要做（第三次提出）**
- 施工图（P11）+ 旧链去向（P12）

---

## 九、HARD STOP

本文件为**评审记录 + 候选方案留档**：未改任何代码、未建任何目录、未 commit。
结构本身**未冻结**，讨论中。

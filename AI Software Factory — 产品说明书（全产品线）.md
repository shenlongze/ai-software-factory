# AI Factory OS — 产品说明书（全产品线）

> 版本: v2.0 | 日期: 2026-09-08 | 依据: 方案书 §24 战略校准 + Cognitive Golden Path 实现
> **主文档《AI Software Factory — 完整产品方案书（终极版）》是愿景/原则源**；本说明书按
> 产品维度拆出能力模块，供独立立项/商业化评估。
> 产品定位已收敛: **AI Factory OS**（AI Enterprise Operating System）— 软件开发是
> **第一个完整生产场景**，不是能力边界。

---

## 0. 产品定位与主链（v2.0 校准）

### 0.1 产品身份三层

```
AI Factory OS            ← 统一操作系统/平台（产品身份）
├── AI Software Factory  ← 第一个完整生产场景（软件开发, CURRENT）
├── AI Product Factory   ← 产品设计/市场/运营场景（EXPANSION）
├── AI Operations Factory← 企业运营场景（EXPANSION）
└── Enterprise Custom Workforce（EXPANSION）
```

- **当前产品身份**: AI Factory OS — 让人通过自然语言直接组织复杂工作的 AI 操作系统。
- **当前完整场景**: AI Software Factory — 软件开发是今天最完整、最深的生产场景。
- **扩展方向**: 产品设计/市场/数据分析/招聘/企业运营等（**Future / Expansion,
  未写成已实现**）。

### 0.2 用户主链（External Natural）

```
我想做什么
  → 和 AI 讨论（Conversation）
  → AI 持续理解我的目标（Product Understanding）
  → 我看到并确认/修改（Understanding Confirmation）
  → 形成正式方案（PRD）
  → 我确认（PRD Approval）
  → 生成执行计划（Development Plan）
  → 我确认（Plan Approval）
  → AI 执行（Production Runtime）
  → AI 验证（Verification）
  → AI 修复（Recovery）
  → 交付结果（Delivery）
```

> **没有用户确认，不允许进入生产。** 这是产品原则，不是实现细节。

### 0.3 两个 Plane

- **Cognitive Plane**（What / Why）: Conversation · Product Understanding ·
  PRD / Plan · Decision · Context — 解决"系统理解用户要做什么"。
- **Production Plane**（How / Execute / Verify）: Task/Node · Production
  Runtime · Verification · Evidence · Recovery — 解决"可靠地做出来"。
- **Governance** 贯穿两者（Approval / Audit / Budget）。

### 0.4 模块属性分类

| 属性 | 含义 | 例 |
|------|------|----|
| **Platform Capability** | 平台内部能力（不单独卖, 但可被外部消费） | Understanding · PRD/Plan 域 · Runtime 内核 |
| **Commercial Product** | 可独立立项/销售的解决方案 | 治理平台 · 审计证据链 · 存量清理服务 |
| **Application Product** | 面向一类用户交付价值的应用 | 行业工厂线 · 渠道平台 |

> 模块即产品 ≠ 烟囱: 各能力模块共享统一身份/数据/契约/治理/审计，是同一 OS 的
> 能力切面，不是 8 个互相独立的小产品。

---

## 产品线总览（CURRENT / PARTIAL / FUTURE 标注）

| # | 产品 | 属性 | 目标客户 | 商业模式 | 优先级 | 当前状态（代码事实） | 规格 |
|---|------|------|---------|---------|--------|---------------------|------|
| 1 | **AI 治理平台** | Commercial | 企业 CTO/合规/审计 | SaaS/私有化 | P0 信任层 | ✅ PARTIAL 核心实现（审批/预算/审计） | governance-platform-spec |
| 2 | **AI 变更审计与证据链** | Commercial | 审计/合规/研发管理 | 订阅 | P0 | ✅ 审计链/证据真实（audit_events 5160+） | audit-evidence-chain-spec |
| 3 | **存量代码清理（积压清道夫）** | Commercial | 企业研发 | 按件/订阅 | P0 wedge | ✅ 分诊→修复→证据→审批真实 | backlog-sweeper-spec |
| 4 | **AI 工作流编排** | Platform Capability | 开发者/ISV | 开源+云 | P1 | 🚧 执行内核真实（Node/NodeRun/Verification） | agent-orchestration-spec |
| 5 | **企业知识库** | Commercial | 知识密集企业 | 订阅 | P1 | 🚧 经验检索 ✅ · 三级 RAG 📐 | knowledge-base-spec |
| 6 | **AI 员工渠道平台** | Application | 运营/客服 | 按渠道 | P2 | 📐 FUTURE（渠道未实现） | channel-platform-spec |
| 7 | **AI 经验学习平台** | Platform Capability | AI 平台团队 | 订阅 | P2 | 🚧 记忆雏形 ✅ · 闭环 📐 FUTURE | learning-platform-spec |
| 8 | **行业工厂产品线** | Application | 行业客户 | 按行业 | P1+ | 🚧 IT 工厂 ✅（软件场景）· 多行业 FUTURE | industry-factory-spec |

> 状态图例（与代码事实对齐）: ✅ = 真实存在并有测试/运行时证据 · 🚧 = 部分实现 ·
> 📐 = 设计/未来（不得写成当前能力）。

---

## 产品 1: AI 治理平台

**定位**: 组织里所有 AI 的信任层（审批门/预算/审计/合规），不管底层用哪个执行引擎。

**核心能力**（来源 §6 + Governance）:
- 分级审批门（approval, 真实 M3）✅
- 成本治理（预算护栏, PARTIAL）🚧
- 权限/合规报告 📐 FUTURE

**对外接口**: 审批/预算/审计 API（部分）；CLI 有
**部署**: 内嵌为平台治理内核 + 独立为"管理所有 AI"治理平台
**商业模式**: SaaS / 私有化
**属性**: Commercial Product（也可作为平台 Platform Capability 被外部消费）

## 产品 2: AI 变更审计与证据链

**定位**: AI 每次变更的完整证据链（diff+test+决策+审计）——"看完证据敢签字"。

**核心能力**:
- 证据链/审计事件（audit_events 真实, 追加不可变, 5000+）✅
- Artifact + Verification 证据（Production Runtime 产出真实）✅
- 审计报告/回放 📐 FUTURE

**属性**: Commercial Product。审计是 OS 治理面的一部分，独立产品化面向合规场景。

## 产品 3: 存量代码清理服务（积压清道夫）

**定位**: 自动处理存量 issue 队列（分诊→修复→证据→审批→报告），首个可独立交付的 wedge。

**核心能力**:
- BacklogSweeper（分诊/执行/证据/审批/报告）✅
- 确定性真实修复（dependency）✅ · 分级审批默认不自动应用 patch ✅

**属性**: Commercial Product（首个 wedge，验证商业闭环）。

## 产品 4: AI 工作流编排

**定位**: 复杂工作的执行编排内核——Node/NodeRun 状态机 + 验证 + 恢复 + 证据。
（注意: 这是 **Platform Capability**, 不是与平台平行的独立产品——它是 OS 的
Production Plane 执行核。）

**核心能力**（来源 §4 + Golden Path Production Plane）:
- Node/NodeRun 执行事实（create_node_run/execute_task 真实）✅
- 递归任务树 / 依赖调度（真实 M3c/M4）✅
- Verification + Artifact + Evidence（真实）✅
- 恢复（Recovery, 真实 M3）✅
- 角色 Agent（developer/pm/architect 等）: 注册真实; 生产触发 PARTIAL 🚧

**属性**: Platform Capability。可独立开源/托管（对标 LangGraph），但首先是 OS 的执行内核。

## 产品 5: 企业知识库

**定位**: 企业知识管理与 RAG 检索（经验 + 文档 + 知识图谱）。

**核心能力**:
- 经验检索（experience_store）✅ 雏形
- 三级 RAG / 知识图谱 📐 FUTURE

**属性**: Commercial Product（企业知识密集场景）。

## 产品 6: AI 员工渠道平台

**定位**: AI 员工出现在用户日常渠道（WhatsApp/Telegram/Slack/微信…），渠道内交互。

**核心能力**:
- 渠道矩阵 📐 FUTURE（未实现）
- 渠道内派活/审批/证据 📐 FUTURE

**属性**: Application Product（消息入口扩展）。**注意**: 渠道是 Conversation 主入口的
接入面，不能成为第二套用户主链——所有渠道最终都指向同一 Conversation/理解/生产链。

## 产品 7: AI 经验学习平台

**定位**: 让 AI 越用越好（经验/画像/评价回写），且可控。

**核心能力**:
- 经验模型 + 检索 ✅ 雏形（写有读少）
- 学习闭环（经验→决策→评价回写）📐 FUTURE（未闭环）
- 学习护栏 📐 FUTURE

**属性**: Platform Capability。记忆的价值是复用已验证知识/经验/事实，不是保存聊天记录。
学习闭环当前为 **Future**（诚实标注）。

## 产品 8: 行业工厂产品线

**定位**: 每行业一条产品线（IT/产品/市场/运营…），同一底座复制。

**核心能力**:
- FactorySpec 声明式规格 📐 PARTIAL
- IT 工厂（软件开发）✅ CURRENT（Golden Path 全链真实）
- 多行业（产品/市场/运营）📐 FUTURE EXPANSION

**属性**: Application Product。行业实例 = AI Factory OS 在具体领域的复制；
**软件开发是当前最完整的行业实例**，其它行业是平台扩展方向（未实现不写成已实现）。

---

## 统一契约（所有模块通用）

```
1. 统一身份/数据/契约: 字段/接口/错误码/审计事件注册表
2. Conversation 是用户表达目标的唯一主入口; 其它入口（CLI/API/管理台/渠道）是
   专业/治理/系统入口, 不是第二套用户主链
3. Cognitive Plane 与 Production Plane 通过统一 Understanding→PRD→Plan→Production
   链连接; 两个 Approval Gate（PRD / Plan）由 Governance 强制
4. 模块=产品 ≠ 烟囱: 独立部署但共享统一 OS 身份, 零摩擦集成
```

---

## 商业化路径（校准）

```
当前可验证（CURRENT）:
  AI Software Factory（软件场景, Golden Path 全链自动化已验证）
  → 积压清道夫 wedge（按件）→ 治理/审计订阅（信任层）

扩展方向（EXPANSION/FUTURE, 未实现不写成当前）:
  AI Product Factory · AI Marketing Factory · AI Operations Factory
  · Enterprise Custom Workforce
```

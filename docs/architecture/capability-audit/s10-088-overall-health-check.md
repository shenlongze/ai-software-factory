# AI Factory 全面体检报告

> 日期: 2026-08-20 | 首席架构师 + 产品负责人 + 技术尽调 | 不美化, 基于真实证据

---

## 一、最初产品愿景(恢复,非反推)

**目标**: AI Software Factory / AI Workforce Operating System
用户提出想法后,AI 团队像真实软件公司一样:理解需求 → 分析市场 → 定义产品 → 设计方案 → 组织研发 → 多 Agent 协作 → 写代码 → 测试 → 发布 → 运行 → 学习优化。

**用户体验**: 用户说"我想做一个 CRM",像走进一家软件公司,一支 AI 员工团队(PM/市场/竞品/UX/架构/工程/QA)协作产出完整软件。

**AI 组织模型**: 多角色真实 Agent 实体,每个有独立 Role/Skill/Memory/Tools/Evaluation,通过协作总线交接,产出互被消费。

**生产流程**: Idea → Discovery → Market → Competitive → Product Brief → PRD → UX → Architecture → Engineering → Development → QA → Release → Operation → Learning。

**核心原则**: 用户决策(审批门)+ 真实资产 + 可审计 + Agent 因经验变强。

---

## 二、生产生命周期逐阶段检查

| Phase | 状态 | 证据 | 分类 |
|---|---|---|---|
| **1. Idea** | 半实现 | 想法进 Discovery,无独立 Idea Artifact(0 个 idea 资产) | C→B |
| **2. Discovery** | 半实现 | 多轮字段收集真实(problem/user/features);但无 Scenario/Requirement 深度分析;发现 0 个 discovery.md | B |
| **3. Market Analysis** | **缺失** | 0 个 market_analysis.md;无 Market Analyst | D |
| **4. Competitive** | **缺失** | 0 个 competitive_analysis.md;无 Competitive Analyst | D |
| **5. Product Strategy** | 半实现 | PM 角色是 prompt,无 Product Brief 资产 | C |
| **6. PRD** | **模板填充** | 15 个 PRD.md 全部模板("XX 是一款面向 YY 的产品");无用户故事/验收标准/非功能需求 | C |
| **7. UX** | 缺失 | 0 个 UX 资产 | D |
| **8. Architecture** | 缺失 | 0 个 architecture.md | D |
| **9. Engineering** | 半实现 | engineering.json + tasks.json 真实(模块从功能拆解);但无 PRD→Arch 消费链 | B |
| **10. Development** | 半实现 | LLM 真调 + patch 生成真;**但项目目录 0 个 .py**(patch 从未成功落地);S10-083 交付管线已建 | B |
| **11. QA** | 缺失 | 无 QA Agent;验证 = 开发者自验(syntax check 0 文件) | D |
| **12. Release** | 缺失 | 无发布流程 | D |
| **13. Operation** | 缺失 | 无生产反馈 | D |
| **14. Learning** | 半实现 | Memory store/检索真实;Agent 学习闭环未接线 | B |

**汇总:真实 2 / 半实现 5 / 空实现 1 / 缺失 6**

---

## 三、Agent Reality Matrix

| Agent | 存在 | 独立 | 输入 | 输出 | 影响后续 |
|---|---|---|---|---|---|
| PM | 名义(prompt) | ❌ | 发现字段 | 模板 PRD | 弱 |
| Market | ❌ | - | - | - | - |
| Competitive | ❌ | - | - | - | - |
| UX | ❌ | - | - | - | - |
| Architect | 名义(技能名) | ❌ | - | - | - |
| Backend | ✅ 真实(exec) | ✅ | task 描述 | patch | **❌ 未落地** |
| Frontend | ✅ 真实(exec) | ✅ | task 描述 | patch | **❌ 未落地** |
| QA | ❌ | - | - | - | - |
| DevOps | ❌ | - | - | - | - |

**核心结论**: **一个 LLM 切换 prompt(工厂层)+ 单 Agent 执行链(exec 层真实)。** 不是多 Agent 协作。
- exec 层有**真实单 Agent 运行时**:DeveloperAgent → ExecutionLoop(LLMPlanner 真调 provider)→ Evaluator(5 层评分)
- 工厂层"角色"= 同一模型换提示词,角色产出互不消费

---

## 四、Artifact 体系

```
Idea ✗ → Discovery △(字段, 无资产) → Market ✗ → Competitive ✗
→ Product Brief ✗ → PRD △(模板) → UX ✗ → Architecture ✗
→ Tasks ✅(engineering.json/tasks.json) → Code ✗(0 个 .py)
→ Test △(syntax check) → Release ✗
```

- 谁产生: 单模型(exec 层真调 provider)
- 谁消费: 无(资产互不消费)
- 版本化: ❌ 无
- 可追溯: 部分(审计事件有,资产血缘无)

---

## 五、Execution / Audit / Observability

**S10-083 成果真实**:
- ✅ 执行时间线: 时间/角色/动作/task/tokens/cost(85 条真实记录,report usage 真)
- ✅ 项目状态视图: 阶段/任务/代码文件/任务明细
- ✅ 交付管线: patch → 白名单过滤 → 容错 apply → 0 文件 FAILED
- ✅ 空目录 PASS 已消除("4 任务失败"是诚实结果)

**缺口**: Decision Trace("为什么这么决定")仅部分(agent 选择 reason 有,评审链有);patch 未成功落地(0 .py 是执行真实性的最终审判)。

---

## 六、MCP / Tool 体系

**现状:框架真实,工具是 Mock。**
- MCP Adapter 442 行真实框架
- **唯一实现 MockMCPClient(echo tool,不连公网)**
- AI 完成真实工作能访问: **本地文件(git/沙箱)**
- 不能访问: 公网/数据库/外部服务/真实 API

---

## 七、Memory / Learning

**真实的部分**:
- ExperienceStore/检索(S10-067)
- PatternLearner + LearningEngine(学习循环:提取→存储→学习)
- Agent 选择时 skill match 引用经验

**未接线的部分**:
- Agent 执行后不自动学习(需显式触发)
- 无"第二次同类任务引用第一次经验"闭环(计划 M4)
- 评价器(5 层评分)存在但不驱动 Agent 改进

---

## 八、代码健康

```
factory-core 33.8K + factory-console 52.2K + factory-exec 28.1K + factory-org 11.8K
生产 127K + 测试 162K
```

| 代码 | 占比 | 价值 |
|---|---|---|
| 基础设施 (CLI/API/存储/配置/审计/权限) | ~45% | 必要但非产品价值 |
| 状态机/编排 (orchestrator/workflow/生命周期) | ~20% | 过度工程倾向 |
| 真实能力 (LLM 调用/发现/交付管线/时间线) | ~20% | 核心价值 |
| 名义/占位 (角色名/资产模板/Mock MCP) | ~15% | 需重建或删除 |

**过度工程**: orchestrator 3056 行单文件;18 项目全部"未命名产品"时代遗留;多套生命周期状态机。

---

## 九、当前真实架构图

```
User → CLI/Web/REPL
  ↓ (真实)
Conversation/Intent Router (真实)
  ↓
Action Registry (真实, 40+ action)
  ↓
ExecutionOrchestrator (真实, 但单模型编排)
  ↓
AgentRuntime → DeveloperAgent → ExecutionLoop → LLM (真实, 单 Agent)
  ↓
Sandbox → patch (真实生成, 格式问题未落地)
  ↓
Delivery 管线 (真实, S10-083)
  ↓
项目目录 0 .py (✗ 断点)
  ↑
PM/Market/UX/Architect/QA (✗ 名义/缺失)
MCP (✗ Mock) | Memory (△ 半接线) | Learning (△ 半接线)
```

---

## 十、最终评分

| 维度 | 分数 | 依据 |
|---|---|---|
| 平台基础 (CLI/API/存储/审计) | **78/100** | 真实且完整 |
| Agent 能力 | **25/100** | 单 Agent 真实,多 Agent 缺失 |
| 产品能力 (市场/竞品/PRD/UX) | **12/100** | 全缺失或模板 |
| 软件生产能力 (代码落地) | **18/100** | 管线在,0 行代码落地 |
| 自治能力 (学习/改进) | **15/100** | 半接线 |
| 商业演示能力 | **20/100** | 无法端到端演示真实交付 |

**综合成熟度:28/100**

---

## 十一、最终建议

**1. 是否偏离最初目标?**
**是,严重偏离。** 127K 代码中,当初愿景的"AI 软件公司"从未建成。当前 = 单 LLM + 流程状态机 + 大量基础设施。但 S10-087 计划已正确识别此偏差(决策 B),方向已拉回。

**2. 最大三个问题**
1. **多 Agent 协作缺失** — 角色是 prompt,不是实体;无 HandoffBus
2. **真实工具缺失** — MCP 是 Mock,AI 无法访问真实世界
3. **代码从未落地** — 0 个 .py;生产链末端断裂

**3. 应该停止开发**
- ❌ 停止一切新能力、新 CLI/API、新审计字段、新状态机
- ❌ 停止流程优化小修(doctor 增强/命令美化)
- ❌ 停止模板资产"转正"

**4. 下一阶段建设(按序)**
1. **M1 内核切片(v1.1.5)**: repo_mode + MCP 真连(1-2 个真实工具)+ 执行循环接线 — 让代码真正落地一个仓库
2. **M2 员工内核(v1.1.6)**: AgentEntity/Registry/装配器/HandoffBus/7 角色 — 多 Agent 真实协作
3. **M3 深度(v1.1.7~1.1.8)**: PRD 深度/审批/工程深度
4. **M4 自我提升(v1.1.9)**: 学习/评价闭环
5. **M5 真实 E2E(v1.2.0)**: 一句话 → 专家 → PRD → 工程 → 代码 → pytest 绿 → 历史可查

**5. 未来 5 个 Sprint**

| Sprint | 内容 | 验收 |
|---|---|---|
| S10-087 | 专家装配器 + HandoffBus + 工具发现 | "让PM分析"走真 Agent 链 |
| S10-088 | MCP 真实连接 + repo_mode | `factory repo` 改一个文件 + 测试绿 |
| S10-089 | 7 角色 AgentEntity + 资产互引 | 市场/竞品/PRD 互引, 影响决策 |
| S10-090 | PRD 深度 + 审批门 + 工程深度 | 执行中"加导出"→PRD v2+新任务 |
| S10-091 | 学习闭环 + 真实 E2E + Demo | 一句话→代码→pytest绿→历史可查 |

---

## 结论

AI Factory 目前是**"单 LLM + 流程状态机的受控流水线"**,不是**"AI 软件公司"**。127K 代码中真正产生用户价值的能力约占 20%,其余是基础设施、状态机与名义能力。但地基(执行管线/交付/审计/时间线)真实且方向正确,S10-087 重建计划已对准最初愿景。**下一个正确动作:执行 M1 内核切片(让代码真实落地),而非继续扩展。**

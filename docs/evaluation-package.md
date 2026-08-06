# 外部评估包 (Evaluation Package) — v1.0.0-rc1

> 面向三类读者: **投资人** (价值与护城河) · **技术评审** (架构与工程可信度) ·
> **企业客户** (适用性与边界)。
> 配套材料: [demo-guide.md](./demo-guide.md) (5 分钟演示) · [quality-report.md](./quality-report.md) ·
> [real-world-validation.md](./real-world-validation.md) · [CHANGELOG.md](../CHANGELOG.md)。

---

## 1. Problem — 为什么 AI Coding 不够

传统 AI Coding 是 `User → Prompt → Code` 的单次问答模式: AI 是"即用即走"的代码生成器。
当 AI 能力越来越强, 它暴露的是**生产组织**问题, 而不是生成质量问题:

| # | 局限 | 后果 |
|:-:|:-----|:-----|
| 1 | 无长期记忆 | 项目上下文、历史决策、进行中状态随会话丢失, 工作无法延续 |
| 2 | 无经验积累 | 成功、失败、用户反馈不沉淀, 同样的坑反复踩, 团队能力不增长 |
| 3 | 无能力评估 | 用哪个模型/Agent 做哪类任务全凭感觉, 性能/成本/匹配度不可见 |
| 4 | 无决策透明 | AI 只给结果不给解释; "完成了"是自报告, 无独立验证, 不可审计 |
| 5 | 无法组织生产 | 单点问答支撑不了多角色协作、长流程编排、人工审核与知识沉淀 |

一句话: **AI 能力越强, 人越累** —— 上下文、判断、验收、记忆全部压在人的肩膀上。

---

## 2. Solution — Factory 模型: 生命周期管理 + 经验闭环 + 人工闸门

把软件生产组织成一条**可管理的生命周期链**, 每个环节的产物变成下一环节的证据:

```
Idea → Research → PRD → [Human Approval] → Architecture → Task → Development → Experience
   ▲                                                                                │
   └────────────────────────── 经验回流, 指导下一次选择 ──────────────────────────────┘
```

三个支柱, 对应三大卖点:

1. **生命周期管理** — 一个想法从 Idea 到交付的每一步都有状态、产物 (Artifact)、
   事件 (Event) 与决策 (Decision); 任意阶段接入 (只有想法 / 已有代码 / 开发中 /
   生产中), 从当前节点继续而不是重建。
2. **人工闸门 (Human in the loop)** — AI 负责分析、推荐、解释; 人负责决策、批准、
   负责。高风险推荐自动绑定人工审批 (Approval 状态机), 产品冲突/架构变更/Scope
   扩展三类挡板命中即暂停上报。Human Console 给人看状态、看理由、批准或驳回。
3. **经验闭环 (Experience Loop)** — 成功、失败、用户反馈全部沉淀为经验 (五域:
   provider / agent / workflow / project / decision), 30 天半衰期衰减, 经推荐引擎
   "影响但不支配" 未来选择。工厂不是用过即弃的工具, 而是**越用越懂你的系统**。

配套三个工程性质: **能力持续生长** (新能力走 Extension 声明式注册, 零核心破坏) ·
**一切以证据为准** (交付完成由独立 L1–L4 验证判定, 每个推荐/决策附证据链与置信度) ·
**事件是唯一事实源** (append-only 事件库, 可回放重建状态, 断点续跑零丢失)。

---

## 3. Differentiation — 与三类竞品的本质区别

| 对比对象 | 它们的模式 | Factory 的不同 |
|:---------|:-----------|:---------------|
| **Cursor / Copilot** (代码助手) | 编辑器内补全/对话生成: 无生命周期、无项目级状态、无人工闸门, 能力停在"单次问答" | 生产系统: 生命周期管理 + 决策链 + 独立验证 + 经验沉淀; 助手是工厂里的一个"工人", 不是工厂本身 |
| **Devin** (自主编码智能体) | 端到端黑箱: 给结果, 过程不可见、不可审计、无人工闸门, 高风险动作默认自动执行 | 可解释 + 人在环上: 每步 Artifact/Event/Decision/Evidence 可追溯, 高风险必经人工审批, 推荐分数可逐项复算; "自动完成"是自报告, 完成与否由独立验证判定 |
| **Agent Framework** (LangChain/AutoGen/CrewAI 等) | 积木/编排库: 提供组件但**无流程、无治理、无记忆策略**, 落地还是要自己造生产系统 | 带流程与治理的平台: 工作流状态机 + 审批挡板 + L1–L4 验证 + 经验闭环 + 只读可观测 (Dashboard 20 视图), 开箱即用的生产秩序 |

护城河表述: **单点工具拼生成质量, Factory 拼生产秩序与经验资产** — 同样的模型
能力, 在 Factory 里被组织成可管理、可验证、可积累的生产过程; 而且经验随使用
增长, 越用越难被替代。

---

## 4. Evidence — 凭什么可以信

| 维度 | 证据 |
|:-----|:-----|
| **测试** | **4111 pytest 全绿** (24 个域, 每阶段基线只增不减) + **92 Vitest** (Web UI 12 文件); 分域明细见 quality-report.md |
| **架构冻结** | 2026-08-06 冻结审查通过: Core = 8 项通用原语, 冻结后不修改; Extension 声明式注册零 Core 破坏; 依赖单向向下、无循环 import (system-architecture-review.md); 反向证明: 删除 product 包后 Factory 照常运行 (有测试断言) |
| **真实项目验证** | MarkPad (Flutter/Dart 编辑器) 表格编辑器增强需求走通 `Idea→Research→PRD→[审批]→UI→[审批]→Architecture→Task→Experience` — **34 事件 / 6 Artifacts / 2 经验 / 2 次人工审批 / Core 零修改** (real-world-validation.md) |
| **决策可解释** | Recommendation 四因素 0.35/0.30/0.20/0.15, 分数 + 方向 (+/-) + 理由文本, 可逐项复算; 决策链 (Product→Architecture→Task Plan) + Evidence 六来源强制 + Risk R1–R5 |
| **演进纪律** | Phase 0 → 14B, **48 次提交**每阶段独立可交付可回退; ADR-0001–0035 记录全部关键决策; 设计文档 30+ 篇 |
| **流程规模** | CLI 23 命令组 / 77 叶子命令 · Dashboard 20 视图 · 六域指标 · 12 阶段生命周期中 6–9 完整实现, 1–5 由 Product Intelligence 承接, 10–11 部分支撑 |

---

## 5. How to evaluate — 建议评估路径 (约 30 分钟)

> 全部离线可跑 (Mock Provider), 不需要任何 API key。要求: Python 3.12+ (可选 node)。

```bash
# ① 全新克隆 (没有隐藏状态, 从零开始)
git clone <repo-url> && cd ai-software-factory

# ② 一键环境搭建 (幂等; --check 只读验证)
bash scripts/setup.sh
bash scripts/setup.sh --check

# ③ 一键完整生命周期演示 (8 阶段: 每阶段 Artifact/Event/Decision 日志 + 汇总)
bash scripts/demo.sh

# ④ 保留工厂根, 用只读命令检视事件库 (可回放/可审计的证据)
.venv/bin/factory demo markpad --keep-root
.venv/bin/factory --root <输出里的 root 路径> dashboard --view all

# ⑤ 复跑测试 (可信度最直接的验证)
.venv/bin/python -m pytest -q          # 预期: 4111 passed
cd factory-console/web/frontend && npx vitest run   # 预期: 92 passed
```

评估清单 (建议逐项打勾):

- [ ] `bash scripts/demo.sh` 输出 8 阶段日志且退出码 0, 无 API key
- [ ] 每阶段输出 Artifact + Event + Decision (三要素齐全)
- [ ] 两次人工审批 (PRD/UI) 均有 `by=` 记录, 审批状态机真实
- [ ] 经验含正向 + 负向信号, 推荐分数可逐项复算
- [ ] `pytest -q` = 4111 passed; `vitest run` = 92 passed
- [ ] 按 demo-guide.md 的三句讲解模板能讲清 Provider 选择 / Approval / 经验闭环
- [ ] 阅读 CHANGELOG.md Known limitations, 确认边界符合你的使用预期

---

## 6. 适用性与边界 (诚实声明)

**适合**: 一个人拥有 AI 软件团队 · 创业团队快速验证产品 · 企业研发部门管理多个
AI Agent · 外包团队自动化项目生命周期 · 作为 AI Agent 平台基础设施。
(五个场景详解: [use-cases.md](./use-cases.md))

**v1.0.0-rc1 不做** (单机、单人、开源核心):

- 无 SaaS / 多租户托管 · 无身份认证/授权 (CLI 与 Console 为本机信任模型, 勿暴露公网)
- 无支付/计费 · 无 Skill/Agent/Workflow 在线市场 (共享靠 git + Extension 声明式注册)
- 反馈闭环 (feedback-model.md) 为接口设计稿, 采集/分类后台留待未来阶段
- 生产执行默认用 Mock/Echo Runtime; 接真实 LLM 需配置 Provider Adapter (hermes-runtime 等)

> 对投资人的话: 现在看的是**生产秩序引擎**的完整性与可验证性; SaaS/认证/计费/市场
> 是产品化的下一步, 接口已预留 (feedback-model 设计稿 + Extension 注册机制)。

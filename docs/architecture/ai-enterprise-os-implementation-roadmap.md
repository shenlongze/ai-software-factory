# AI Enterprise OS — Implementation Roadmap (Freeze 后)

> 日期: 2026-08-07 | 状态: 实施战略裁决 (Architecture Freeze 后)
> 目标: 从"完整架构" → "可被用户验证的产品"
> 原则: 零新架构模型; Core/Runtime 冻结; 诚实区分 Implemented/Designed/Future

## 1. 当前系统真实能力评估（诚实）

### Already Implemented（用户现在下载能得到）

```
✅ Desktop (dmg) + Runtime (Managed Services + Command)
✅ factory-org MVP (Company/Department/Role/Employee/Authority/Knowledge + Default Deny)
✅ 生命周期管理 (Product 9d: Idea→PRD→Approval→Task) — 管理闭环
✅ Intelligence 决策/推荐/经验 (10A: 四因素/证据/五域) — 但 Provider 是 Mock
✅ Console (Web UI 只读) + Demo (markpad, Mock 生成)
✅ 4433 tests | 151 事件 | 35 ADR
```

### Designed（架构已冻结, 未实现）

```
📐 Agent Runtime 真实执行 (18) — ExecutionRequest/Sandbox/Tool
📐 真实 LLM Provider 接入 (8A 抽象有, 无真实 Adapter 调用)
📐 Planning 完整 (17: Goal→Task Graph→Matching)
📐 Communication 系统 (16C)
📐 Governance 完整 (17A: Policy/Risk/Cost)
📐 Learning 完整 (19)
```

### Future

```
🚫 企业级 (多租户/集团) | 商业 (支付/SaaS) | 行业模板 (20) | ERP 融合
```

**关键结论: 用户现在拿到的是"管理平台 + 演示", 不是"生产系统"。**

---

## 2. MVP 产品重新定义

**选择 A: 个人 AI Software Company（1 人 + AI 公司）**

| 候选 | 用户价值 | 技术闭环 | 商业可能 |
|:-----|:---------|:---------|:---------|
| A. 个人 AI Software Company | 高 (直接能用) | 中 (16A 已有) | 高 (订阅) |
| B. 企业 AI Department | 高 | 低 (需多租户) | 高 |
| C. AI Development Team | 中 (窄) | 中 | 中 |
| D. AI Employee Platform | 低 (抽象) | 低 | 中 |

**理由: A 是"1 人雇佣 AI 团队做真实项目" — 价值最直观, 16A 已奠基, 与 markpad demo 无缝。**

---

## 3. 实现优先级（产品价值排序, 非架构顺序）

```
P0 (必须, 3 个月):
  P0-1  真实 LLM Provider 接入 (1 个 Adapter: Anthropic/OpenAI, 8A 已抽象)
  P0-2  Agent Execution 最小 (18 裁剪: Task→Agent→LLM→Patch→Artifact)
  P0-3  Sandbox 最小 (工作副本 + 补丁, 不碰用户环境)
  P0-4  最小 Review/Approval (执行权 != 审核权)
  P0-5  Learning 最小 (Experience 回流 → 推荐加权, 复用 10A-4)

P1 (重要, 6 个月):
  P1-1  Planning 最小 (Goal→Task 拆解, 手工+AI 建议)
  P1-2  Communication 最小 (16C 裁剪)
  P1-3  Policy 最小 (默认 deny 强制执行)
  P1-4  Desktop 集成 (公司创建→目标→执行→汇报 全链)

P2 (未来):
  完整 Governance (Risk/Cost) / 多租户 / 行业模板 / Self Improvement 自动提案
```

**裁决: Execution > Governance。先让"AI 真的干活", 再完善"干活受控"。**
**（Governance 最小 = Default Deny + Approval, 17A 完整延后）**

---

## 4. 第一个完整闭环

```
Human → Goal → Planning(最小) → Task → Employee Selection(16A)
→ Agent Runtime(最小) → LLM Provider(真实) → Sandbox(最小)
→ Artifact → Review → Approval → Learning
```

### 必须 (真实实现)
```
LLM Provider 真实调用 (1 家) | Agent Runtime 最小 (请求→响应→补丁)
Sandbox 最小 (临时工作副本) | Artifact 生成 (patch) | Approval (Human 确认)
Learning (Experience 记录 + 回流)
```

### 可 Mock（占位, 后续补）
```
Planning 智能拆解 (先手工/简单规则) | Communication 完整 (最小记录即可)
Governance Policy 完整 | 多 Agent 并行
```

---

## 5. Agent Execution 最小方案

**第一个 AI Employee: Developer Agent**

```
Capability: code.modify (声明 Level 2) + 知识: 项目规范
Provider:   真实 LLM (Anthropic 或 OpenAI — 首个 Adapter)
Tool:       filesystem (沙箱内读写) — 最小
Sandbox:    临时目录副本 + patch 输出

最小接口:
  execute(task_context, provider, sandbox) → artifact(patch) + report
  输入: 任务目标 + 上下文 (知识/Artifact 引用)
  输出: 代码补丁 + 说明 + 自测结果
  门禁: Authority 检查 (code.modify?) + Approval (人工确认应用)
```

---

## 6. Communication MVP

```
最小 CommunicationRecord (16C 裁剪):
  Who / To / Purpose / Input / Output / Result   (6 字段)

未来增加:
  Context (深度引用) / Decision (决策链) / Event refs / TTL 归档 / 摘要提炼
```

---

## 7. Learning MVP（第一次"越用越聪明"）

```
只需要 (复用 10A-4, 零新模型):
  Experience Record (任务/结果/成功率 — 已有)
  失败原因 (结构化: 哪步失败)
  推荐优化 (下次匹配加权: 高绩效 Agent 优先)

Self Improvement 保留 Proposal 接口 (不实现自动修改)
```

---

## 8. 30 分钟 Demo 设计

```
用户: 一个普通开发者
操作 (0-30min):
  0:00  下载/启动 Desktop → 创建 AI Company (software_company)
  0:05  雇佣 Developer Agent (真实 LLM Provider)
  0:08  提出需求: "给 markpad 加表格单元格编辑" (Goal)
  0:10  AI 分析需求 → 拆任务 (最小 Planning)
  0:15  Developer Agent 真实编码 (LLM → 沙箱 → patch)
  0:22  AI 自测 (简单验证) → 汇报 (输出/成本/时长)
  0:25  Human Review → Approval → 应用补丁
  0:28  展示: 代码真的变了 + Experience 已记录 (下次更准)

最终展示: AI Factory 真正生产 (非 Mock)
```

---

## 9. 技术债风险

```
⚠️ 过度抽象: 22 份设计文档 vs 1 层实现 (16A)
   → 冻结接口, 优先实现, 文档只作规范
⚠️ 模型过多: 10 大模型 + 各层 Entity
   → MVP 只用最小集 (Company/Employee/Task/Artifact/Experience/Approval)
⚠️ 假能力风险: Mock Provider 演示 ≠ 真实能力
   → P0-1 真实 LLM 是最大价值跃迁, 优先
⚠️ 建议冻结: 架构已冻结, 实现期不接受新模型 (变更走 Review)
```

---

## 10. 最终建议（未来 3 个 Phase）

```
Phase A: 产品闭环 (P0, 3 个月)
  目标: "1 人 + AI 公司能真实生产一个小功能"
  范围: 真实 LLM + 最小执行/沙箱/审批/学习 + Desktop 全链
  不做: 完整治理/多 Agent/Communication 深度/自动规划

Phase B: 能力扩展 (P1, 6 个月)
  目标: "AI 团队协作完整化"
  范围: Planning 智能 + Communication + Policy + 多员工并行
  不做: 多租户/行业模板/Self Improvement 自动

Phase C: 企业化 (P2, 12 个月)
  目标: "AI Enterprise OS 产品化"
  范围: 治理完整 + 多租户 + 行业模板 + 商业化
  不做: ERP 融合 (更远期)
```

---

## 结论

```
AI Enterprise OS 架构已冻结 (v1.0)
实施路线: Phase A (真实生产闭环) → B (团队协作) → C (企业化)
最大跃迁: 真实 LLM Provider 接入 — 从"管理平台"到"生产系统"
等待确认后进入 Phase A 实现
```

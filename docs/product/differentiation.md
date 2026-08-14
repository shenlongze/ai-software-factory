# Differentiation — Why AI Factory?

> 位置: docs/product/differentiation.md | Sprint: S10-040 | 竞争定位重审

---

## 核心回答

**"为什么用户需要 AI Factory?"**

> **因为 AI 工具已经很多, 但管理 AI 员工的组织层缺失。**
> Devin/Cursor/Claude Code 是优秀的"员工"; AI Factory 是管理员工的"操作系统"。

## 对比

| 维度 | AI Factory | OpenAI Agents SDK | LangGraph | CrewAI | AutoGen | Devin |
|---|---|---|---|---|---|---|
| 定位 | 治理驱动的 AI 员工 OS | Agent 构建 SDK | Agent 编排框架 | 多 Agent 框架 | 多 Agent 框架 | 自主 Agent 产品 |
| 多 Provider 中立 | ✅ | ❌(OpenAI) | ✅ | ✅ | ✅ | ❌ |
| 审批门/人审 | ✅ 内置 | 需自建 | 需自建 | 需自建 | 需自建 | ⚠️ 部分 |
| 全事件审计 | ✅ 内置 | 需自建 | 需自建 | 需自建 | 需自建 | ⚠️ 黑盒 |
| 组织隐喻(员工/角色) | ✅ | ❌ | ❌ | ⚠️ | ⚠️ | ❌ |
| 真实执行闭环 | ✅ | ✅ | ⚠️ | ⚠️ | ⚠️ | ✅ |
| 成本优化(Router) | ✅ 内置 | ❌ | 需自建 | 需自建 | 需自建 | ❌ |
| CLI 完整入口 | ✅ | ⚠️ | ❌ | ❌ | ❌ | ⚠️ |
| 治理/合规基础 | ✅ 内置 | ❌ | ❌ | ❌ | ❌ | ❌ |

## 分层定位

```
AI Factory (治理层 + 组织层)
    ↑ 管理/审计/审批/组织
Devin / Cursor / Claude Code (执行层)
    ↑ 生成代码/操作
SDK / LangGraph / CrewAI / AutoGen (构建层)
    ↑ 构建 Agent 的积木
```

- **构建层**(SDK/框架): 用户自己搭治理/审计/存储 — 复杂
- **执行层**(Devin/IDE): 强大但不透明、不可审计
- **AI Factory(治理+组织层)**: 开箱即用的"管理 AI 员工"平台

## 为什么用户需要 AI Factory(三点)

1. **可控**: 审批门 + 全审计 — "AI 做了什么我能看到、能批准、能追溯"
2. **中立**: 多 Provider — "不绑一家, 按任务选最优模型, 成本可控"
3. **组织化**: 员工/角色/技能 — "AI 不是碎片工具, 是一支可管理的团队"

## 竞争窗口

- 大厂(OpenAI/Anthropic)可能内置治理 → 窗口期 12-24 个月
- 差异化靠: ① 中立(不绑厂商)② 组织隐喻(管理多 AI)③ 治理底座(审计/审批)

## 不正面竞争的领域

- 不做 IDE(Cursor 主场)
- 不做最强编码模型(Claude/OpenAI 主场)
- 不做编排框架(LangGraph/CrewAI 主场)
- **做它们缺的一层: 治理 + 组织 + 审计**(开源获客 → Enterprise 变现)

## 定位口号

> **"Devin 替你干活, AI Factory 管理你的 AI 员工。"**

---

> Task 004 完毕 | 差异化: 治理 + 中立 + 组织化 | 不做 IDE/模型/框架

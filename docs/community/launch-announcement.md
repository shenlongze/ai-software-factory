# Launch Announcement — AI Factory v0.1.0

> 位置: docs/community/launch-announcement.md | Sprint: S10-046 | 发布公告草稿
> 适用: GitHub Release / 技术社区(HN/Reddit/V2EX/掘金/博客)

---

# 🚀 AI Factory v0.1.0 — AI Workforce Operating System

> **Devin 替你干活, AI Factory 管理你的 AI 员工。**

## 为什么做 AI Factory

过去一年, AI 编码工具爆发: Claude Code、Cursor、Devin、Copilot...
它们都很强, 但它们都是**一个员工**。

但企业/团队真正的问题是: 当你有 5 个 AI 员工, 你怎么管理它们?
- 哪个模型做哪个任务最划算?
- 谁批准 AI 的产出?
- 每个 AI 花了多少钱?
- 出了事怎么追溯?

**这就是 AI Factory 解决的问题 — AI 的组织层。**

```
传统:   Human → Code
AI 时代: Human → AI Organization → AI Workers → Software Output (全部可审计)
```

## 解决什么问题

| 痛点 | AI Factory 方案 |
|---|---|
| AI 不可控 | 审批门: AI 提议, 人工批准 |
| 无审计 | 全事件审计: 谁/什么/何时/哪个模型/多少钱 |
| 成本失控 | 多模型 Router: 按任务选最划算的模型 |
| 上下文丢失 | 项目生命周期 + Agent 角色(Experience 增强中) |
| 工具碎片化 | 一个平台管理所有模型 + Agent |

## Demo(1 条命令, 40 秒)

```bash
pip install ai-software-factory   # 或 git clone + setup.sh
export DEEPSEEK_API_KEY=...
factory init --non-interactive --provider deepseek
factory demo run "给 main.py 加一个 hello 函数"
```

**真实 LLM 执行**(非 mock), 成本 < $0.01, 全流程审计。

## 核心能力

- **多模型中立**: DeepSeek / OpenAI / Anthropic / Ollama(含本地)
- **真实执行**: Task → Agent → LLM → 沙箱 → Artifact
- **LLM Router**: 五层决策链(User > Agent/Skill > Project > System > Fallback), 可解释
- **全审计**: append-only 事件库
- **CLI First**: 17+ 命令, 无 UI 也完整
- **开源**: Apache-2.0, Open-Core 模式

## 未来方向

```
v0.2: CLI/UI 体验增强 + Evaluation
v0.3: Project RAG + Memory + 智能路由
v1.0: Enterprise Governance (RBAC/合规/策略引擎)
```

**路线图诚实标注**: 当前实现 vs 未来规划, 不夸大。

## 数据

- v0.1.0: 8191 tests green
- 全新环境验证: install → init → demo run → artifact 全通
- 真实执行: 40 秒, <$0.01/任务

## 加入

- 仓库: https://github.com/shenlongze/ai-software-factory
- 文档: Quick Start(中/英) + 5 分钟上手
- 反馈: GitHub Issues(bug/question/feature)
- 我们是种子用户驱动的产品: **你的反馈决定 v0.2**

---

## 分发渠道建议

| 渠道 | 内容 | 时机 |
|---|---|---|
| GitHub Release | 本公告精简 + Release Notes | 转公开后 |
| Hacker News | 英文版: "Show HN: AI Workforce Operating System" | 转公开后 |
| V2EX / 掘金 | 中文版 | 转公开后 |
| 技术博客 | 长文: "为什么 AI 需要操作系统" | 1 周内 |
| 朋友圈/技术群 | seed-user-kit 链接 | 立即 |

---

> Task 005 完毕 | 发布公告就绪 | 分发渠道清单

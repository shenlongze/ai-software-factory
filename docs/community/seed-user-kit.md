# Seed User Kit — AI Factory

> 位置: docs/community/seed-user-kit.md | Sprint: S10-046 | 给第一个用户的完整资料
> 用途: 邀请种子用户时一次性提供(介绍/安装/首个 Demo/反馈入口)

---

# 欢迎试用 AI Factory 🚀

## 1. 项目介绍

**AI Factory = AI 员工操作系统(AI Workforce Operating System)**

让 AI 像软件公司员工一样工作: 理解需求 → 规划 → 开发 → 受治理 → 可审计。

```
传统开发:   Human → Code
AI 时代:    Human → AI Organization → AI Workers → Software Output
```

**核心差异**: 不是"一问一答的聊天机器人", 而是管理一支 AI 团队 —
有岗位、有审批、有审计、有成本账单。

- 多模型中立: DeepSeek / OpenAI / Anthropic / Ollama
- 真实执行: Task → Agent → LLM → 沙箱 → Artifact(非 mock)
- 全审计: 谁/什么/何时/哪个模型/多少钱
- 成本透明: 每次执行 tokens + cost 可见

## 2. 安装方法

### 方式 A: 源码(当前推荐)

```bash
git clone https://github.com/shenlongze/ai-software-factory.git
cd ai-software-factory
bash scripts/setup.sh        # 自动: Python 3.12+ venv + 依赖 + 冒烟
```

### 方式 B: pip(发布后)

```bash
pip install ai-software-factory
```

### 配置 LLM(1 分钟)

```bash
export DEEPSEEK_API_KEY="sk-..."              # 你的 key(不落盘)
factory init --non-interactive --provider deepseek
factory doctor                                # 诊断, 全 PASS 即可
```

> 支持 provider: deepseek / openai / anthropic / ollama(本地, 无需 key)

## 3. 第一个 Demo(1 条命令, ~40 秒)

```bash
factory demo run "给 main.py 加一个 hello 函数"
```

你会看到:
```
✔ 任务: 给 main.py 加一个 hello 函数 已完成 (status=success, 用时 20.9 秒)
  result-id   EXS-xxxx
  下一步:
    - 查看报告: factory run-status --id EXS-xxxx
    - 查看审计: factory audit
```

**这是真实 LLM 调用 — 不是演示数据。整个流程成本 < $0.01。**

### 或者用自己的项目

```bash
factory project create --repo-path ~/my-app --name my-app
factory run --project ~/my-app --objective "给 main.py 加一个乘法函数" --agent backend-1
```

## 4. 反馈入口

我们非常需要你的反馈来改进产品。

### 方式 1: GitHub Issues(推荐)

- 提 bug: https://github.com/shenlongze/ai-software-factory/issues/new?template=bug_report.md
- 提问: https://github.com/shenlongze/ai-software-factory/issues/new?template=question.md
- 功能建议: https://github.com/shenlongze/ai-software-factory/issues/new?template=feature_request.md

### 方式 2: 结构化反馈(5 分钟)

复制 [seed-user-feedback.md](./seed-user-feedback.md) 模板, 填写后发 Issue(标题 [feedback])。

### 我们想知道的

1. 从安装到第一次成功, 花了多久? 卡在哪?
2. 哪个概念最难懂?(provider / agent / objective)
3. 你会用它做什么? 缺什么?
4. 愿意继续用吗? 愿意付费吗?

## 5. 小提示

- 用 `factory demo` 不会碰你的真实数据(隔离 ~/.factory-demo)
- 失败时会显示 `❌ Failed + Reason + Solution`(跟着做就行)
- 文档: [Quick Start](../getting-started/quick-start-zh.md) · [5 分钟上手](../getting-started/5-minute-demo.md)

---

**再次感谢你的试用! 你的反馈直接决定 v0.2 做什么。**

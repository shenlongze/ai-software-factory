# AI Software Factory

> **治理驱动的 AI 软件生产平台 —— 管理你的 AI 员工, 而不是用 AI 聊天。**

让 AI 像软件公司员工一样工作: 理解需求 → 规划 → 开发 → 受治理 → 可审计。

`v1.0.0-rc1` · CLI First · 本地部署 · 全事件审计

---

## 它解决什么问题

传统的 AI 编码工具是"一问一答": 你发一个 prompt, 它吐一段代码, 然后呢?

| 痛点 | 后果 |
|---|---|
| **不可控** | AI 说"完成了"就完成了, 没有独立验证, 也没有人能解释它为什么这么做 |
| **无审计** | 哪个模型干了什么、花了多少钱、谁批准的 —— 全部无从追溯 |
| **上下文丢失** | 会话一关就"失忆", 项目背景、历史决策、进行中状态全部归零 |
| **成本失控** | 所有任务都交给同一个大模型, 账单悄悄膨胀, 无人知晓 |
| **无法组织** | 多任务、多项目、多人并行时, 没有流程、没有分工、没有记录 |

**AI Software Factory 把 AI 从"聊天机器人"变成"员工"**: 有岗位、有职责、有流程、
有审批、有审计、有成本账单。你不是在跟 AI 对话 —— 你是在管理一支 AI 团队。

## 快速开始

### 1. 安装 (2 分钟)

> 当前以源码安装为准, 一键脚本自动完成环境搭建; `pip install ai-software-factory` 即将支持。

```bash
git clone https://github.com/shenlongze/ai-software-factory.git
cd ai-software-factory
bash scripts/setup.sh        # 自动: Python 3.12+ venv + 安装 + 冒烟验证 (幂等, 可重复执行)
```

### 2. 配置你的 LLM (1 分钟)

```bash
export DEEPSEEK_API_KEY=sk-xxxx...                              # 你的 DeepSeek API Key
factory init --non-interactive --provider deepseek              # 生成配置
factory doctor                                                  # 诊断环境, 全部 PASS 即可开始
```

> Key 只以环境变量引用写入配置 (`env:DEEPSEEK_API_KEY`), **不落盘、不写明文**。
> 支持 provider: `deepseek` / `openai` / `anthropic` / `ollama`。

### 3. 5 分钟体验 (核心)

```bash
factory start                                                   # 启动服务 (backend + frontend)
# 浏览器打开 http://localhost:8011, 看 AI 员工工作

# 或全 CLI (无需 UI, 一样完整):
factory project create --repo-path ~/my-app                     # 接入你的已有项目
factory project list                                            # 查看已注册项目
factory run --project ~/my-app --task T-001 --agent backend-1   # 派第一个任务
factory run-status --id <结果ID>                                # 查询执行结果
```

> `--task T-001` 是任务锚点 ID, 可换成任意编号; 详细目标可用 `--objective` 补充, 验收标准用 `--requirement` 指定。

### 你会看到什么

- ✅ **真实 LLM 执行** — 不是 demo 数据, 是真实模型在工作
- ✅ **审批门** — AI 产出等你批准, 决策权在人
- ✅ **全审计** — 谁 / 什么 / 何时 / 哪个模型 / 多少钱, 全程可查

### 零污染演示 (可选)

不想碰自己的项目? 用隔离的 Demo Workspace 30 秒看效果:

```bash
factory demo init       # 创建隔离演示环境 (~/.factory-demo, 不碰你的数据)
factory demo status     # 查看演示状态
factory demo reset      # 清空重建
```

## 能力一览

| 能力 | 说明 |
|---|---|
| ✅ **多模型路由** | DeepSeek / OpenAI / Claude / Ollama, 按 能力 / 成本 / 性能 为每个任务选最合适的模型 |
| ✅ **真实代码执行** | 沙箱内真实执行 + 独立验证 — 自报告 ≠ 完成 |
| ✅ **人工审批** | 高风险动作必须人工批准, 平台只推荐、不静默执行 |
| ✅ **全事件审计** | append-only 事件库, 一切操作可追溯、可回放、可对账 |
| ✅ **项目生命周期** | 项目从接入、任务派发到交付全程可管理 |
| ✅ **CLI First** | 无 UI 也完整可用, Web 管理台用于观察与审批 |

## 架构 (一句话)

> 治理底座 + 可插拔能力: 事件是唯一事实源, 新能力以扩展注册, 零核心破坏。
> 技术细节见 [docs/architecture/](./docs/architecture/)。

## 开发者

- 源码构建 / 测试 / 贡献指南: [docs/development.md](./docs/development.md)
- 生命周期模型: [docs/lifecycle-model.md](./docs/lifecycle-model.md)
- 愿景与理念: [docs/vision.md](./docs/vision.md)
- 用户指南: [docs/user-guide.md](./docs/user-guide.md) · 应用场景: [docs/use-cases.md](./docs/use-cases.md)
- 测试基线: **8148 pytest 全绿** (v1.0.0-rc1)

## 企业 / 商业

需要私有化部署、审计合规、企业治理版? 欢迎通过 GitHub 联系:

- Issues: <https://github.com/shenlongze/ai-software-factory/issues>
- 仓库: <https://github.com/shenlongze/ai-software-factory>

---

*v1.0.0-rc1 · 治理驱动的 AI 软件生产平台 —— 管理你的 AI 员工, 而不是用 AI 聊天。*

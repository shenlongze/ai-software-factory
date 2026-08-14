# 快速开始 — AI Software Factory(5 分钟)

> v1.0.0-rc1 · CLI First · 本地部署 · 全事件审计

## 5 分钟内完成

1. 安装
2. 初始化(`factory init`)
3. 配置 LLM
4. 诊断(`factory doctor`)
5. 创建项目
6. 运行第一个 AI 任务(`factory run`)
7. 查看产物(artifact)

---

## 1. 安装

```bash
# 方式 A — 源码安装(当前推荐)
git clone https://github.com/shenlongze/ai-software-factory.git
cd ai-software-factory
bash scripts/setup.sh          # 创建 .venv, 安装依赖, 冒烟检查

# 方式 B — pip(即将支持)
# pip install ai-software-factory
```

安装后 `factory` 命令可用:

```bash
./bin/factory --help
```

## 2. 初始化

```bash
factory init --non-interactive --provider deepseek
```

创建你的工作区(`~/.factory/`),包含 agents/skills/projects/providers 目录,
并写入 `providers.json`(含你选择的 provider)。

> `providers.json` 只存 API key 的**引用**
> (`api_key_ref: "env:DEEPSEEK_API_KEY"`)——绝不存明文 key。

## 3. 配置 LLM

AI Factory 从不落盘明文 key。在环境变量中设置:

```bash
export DEEPSEEK_API_KEY="sk-..."   # 以 DeepSeek 为例
```

支持的 provider(`providers.json` 中):`deepseek` / `openai` / `anthropic` /
`ollama`(本地,无需 key)。

## 4. 诊断

```bash
factory doctor
```

检查环境/Provider/模型目录/Runtime/Router——每项输出 PASS / WARN / FAIL 及修复提示。

```bash
factory doctor --json   # 机器可读(供 CI)
```

## 5. 创建项目

```bash
factory project create --repo-path /path/to/your/code --name my-project
factory project list
```

或使用隔离的演示工作区:

```bash
factory demo init
factory demo status
```

## 6. 运行第一个 AI 任务

```bash
mkdir -p /tmp/todo-app && echo "print('hello')" > /tmp/todo-app/main.py

factory run \
  --project /tmp/todo-app \
  --task E2-001 \
  --agent backend-1
```

触发真实执行链:Task → Agent → LLM(经 Router 决策)→ 沙箱 → 产物。
LLM 调用是**真实的**(DeepSeek/OpenAI/你的 provider)——不是演示数据。

## 7. 查看产物

```bash
factory run-status --id <result-id>
```

运行会打印 `result_id`(如 `EXS-...`)。status 显示:

```
status      success
artifact    patch     ~/.factory/exec/patches/EXS-....patch
artifact    report    ~/.factory/exec/EXS-....report.md
usage       {'prompt_tokens': ..., 'completion_tokens': ..., 'estimated_cost_usd': ...}
```

每一步都有审计——查看事件:

```bash
factory audit
```

---

## 你会看到什么

- **真实 LLM 执行** — 非 mock 输出
- **审批门** — AI 产出等待人工批准
- **全审计** — 谁/什么/何时/哪个模型/花了多少钱

## 故障排查

| 问题 | 修复 |
|---|---|
| `factory doctor` 提示 provider key 缺失 | `export DEEPSEEK_API_KEY=...` 后重跑 |
| `factory run` 报 provider not found | `factory config check` — 验证 `providers.json` |
| 想按任务用不同模型 | 配置 `agent.yaml` / `project.yaml`(Router 规则) |

## 下一步

- `factory demo init` — 隔离演示工作区
- `factory service list` — backend / frontend / runtime 状态
- `factory start` — 启动后端 + 前端
- 文档:[愿景](./product/vision-zh.md) · [开发指南](../../docs/development.md)

---

*命令均基于 v1.0.0-rc1 验证。*

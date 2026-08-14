# 5 分钟让 AI Factory 第一次工作

> 位置: docs/getting-started/5-minute-demo.md | 面向第一次安装用户
> 不介绍内部架构, 只回答: "我怎么让 AI Factory 第一次工作?"

---

## 你需要什么

- 一台 Mac / Linux(或 Windows + WSL)
- Python 3.12+
- 一个 LLM API Key(DeepSeek / OpenAI / Anthropic, 任选)

## 5 分钟路径

### 第 1 步: 安装(1 分钟)

```bash
git clone https://github.com/shenlongze/ai-software-factory.git
cd ai-software-factory
bash scripts/setup.sh
```

> setup.sh 自动创建 Python 环境并安装, 完成后 `factory` 命令可用。

### 第 2 步: 配置你的 LLM(1 分钟)

告诉 AI Factory 用哪个模型服务:

```bash
factory init --non-interactive --provider deepseek
```

然后让你的 API Key 对 AI Factory 可见(它只读环境变量, 不存文件):

```bash
export DEEPSEEK_API_KEY="sk-你的真实Key"
```

> 换其他服务商? `--provider openai` / `--provider anthropic` / `--provider ollama`(本地, 无需 key)。

### 第 3 步: 检查是否就绪(30 秒)

```bash
factory doctor
```

看到 `PASS` 或只有 `WARN` 提示(按提示处理 key)即可开始。

### 第 4 步: 创建你的第一个项目(30 秒)

```bash
mkdir -p ~/my-first-project
echo "print('hello from AI Factory')" > ~/my-first-project/main.py
factory project create --repo-path ~/my-first-project --name my-first-project
```

### 第 5 步: 让 AI 执行第一个任务(2 分钟)

```bash
factory run \
  --project ~/my-first-project \
  --task T-001 \
  --agent backend-1
```

> `T-001` 是任务编号(随便起), `backend-1` 是负责写代码的 AI 员工。
> 想看效果? 把任务改成: `--objective "给 main.py 加一个加法函数"`(v0.2 支持, 当前用 --task)。

### 第 6 步: 看结果

```bash
factory run-status --id <上一步输出的 EXS-...>
```

会看到:
- `status: success`
- `artifact: patch`(AI 写的代码)
- `usage: 1234 tokens · $0.0009`(花了多少钱)

不想碰自己的项目? 直接看演示:

```bash
factory demo init && factory demo status
```

## 常见问题

| 问题 | 解决 |
|---|---|
| `factory doctor` 提示 key 缺失 | 确认执行了 `export DEEPSEEK_API_KEY=...` |
| `factory run` 报 provider not found | 先 `factory init --non-interactive --provider deepseek` |
| 想换模型 | 改 `--provider`, 或配置多 provider 后由 Router 自动选 |
| 担心污染数据 | 用 `factory demo`(隔离环境, 不碰真实数据) |

## 下一步

- 完整用户指南: [quick-start-zh.md](./quick-start-zh.md)
- 更多场景: [first-use-cases.md](../product/first-use-cases.md)

---

*命令均基于 v0.1.0 验证。*

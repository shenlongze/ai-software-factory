# Demo Experience — 5 分钟 AI Factory Flow

> 位置: docs/product/demo-flow.md | Sprint: S10-040 | 演示设计(基于真实执行链)
> 原则: 真实执行, 禁止 fake 数据

---

## 演示核心叙事

**"Devin 替你干活, AI Factory 管理你的 AI 员工。"**

5 分钟内展示: Idea → Project → Agent → Router → LLM Execution → Artifact, 全程真实。

## 5 分钟 Demo Flow

### 0:00-0:30 — 开场(30 秒)

**讲**: "这不是聊天机器人, 是 AI 员工操作系统。看它从一句话到真实代码。"

### 0:30-1:30 — Idea → Project(60 秒)

```bash
# 演示用隔离环境, 不污染真实数据
factory demo init
factory project create --repo-path /tmp/demo-app --name demo-app
factory project list          # 看到 P-xxx 注册成功
```

**讲**: "一个想法/项目注册进平台, 有 ID、可追踪。"

### 1:30-2:30 — Agent + Router(60 秒)

```bash
factory agent                 # 看到 backend-1 (backend-developer)
factory router                # 看到 Router 决策链 + 当前决策 (deepseek)
```

**讲**: "AI 员工有角色有技能; Router 决定这个任务用哪个模型(可解释: 为什么选 deepseek)。"

### 2:30-4:00 — LLM Execution(90 秒)

```bash
factory run --project /tmp/demo-app --task T-001 --agent backend-1
```

**讲**: "真实 DeepSeek API 调用 — 不是演示数据。看它生成 patch、跑验证。"

> 关键展示: status: success / usage: tokens + cost

### 4:00-4:45 — Artifact(45 秒)

```bash
factory run-status --id EXS-...      # patch / report / usage
cat ~/.factory/exec/EXS-....patch    # 真实代码产物
```

**讲**: "产物可查看: patch 文件、执行报告、成本账单。"

### 4:45-5:00 — Audit + 总结(15 秒)

```bash
factory audit                 # 全事件时间线
```

**讲**: "每一步都记录: 谁/什么/何时/哪个模型/多少钱。这就是治理。"

## 演示脚本(可复制)

```bash
# 前置 (演示前一次性)
bash scripts/setup.sh
export DEEPSEEK_API_KEY="sk-..."    # 真实 key
factory init --non-interactive --provider deepseek

# 5 分钟演示
mkdir -p /tmp/demo-app && echo "print('hello')" > /tmp/demo-app/main.py
factory project create --repo-path /tmp/demo-app --name demo-app
factory project list
factory agent
factory router
factory run --project /tmp/demo-app --task T-001 --agent backend-1
factory run-status --id <EXS-...>
factory audit
```

## 演示要点(讲什么/不夸大)

| 环节 | 讲什么 | 不夸大 |
|---|---|---|
| 真实执行 | "这是真实 DeepSeek 调用" | 不说"全自动" — 有审批门 |
| 审批门 | "AI 产出等你批准" | 不隐去人工步骤 |
| 成本 | "整个流程 <$0.01" | 不给虚价格 |
| 审计 | "每一步可追溯" | 不称"企业级合规"(Enterprise Future) |

## 演示验收标准

```
[ ] 一句话输入 → 项目注册
[ ] Router 决策可见 (source/reason)
[ ] 真实 LLM 执行 (usage tokens > 0)
[ ] Artifact 产出 (patch/report)
[ ] 审计可见 (factory audit)
[ ] 全程成本 < $0.01
[ ] 时长 ≤ 5 分钟
```

## 后续自动化(记录, 非本 Sprint)

- `factory demo run <goal>`: 一键 建目录+建 task+执行+展示(消除手动步骤)
- 演示视频录制(3 分钟版本)

---

> Task 003 完毕 | 5 分钟 Demo Flow 设计完成 | 真实执行链, 无 fake

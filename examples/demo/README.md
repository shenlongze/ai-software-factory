# AI Factory Demo — 真实执行链体验

> 位置: examples/demo/ | 目标: 让用户体验 AI Factory 核心流程
> 原则: **必须使用真实执行链, 禁止 fake 数据** (S10-033 Task 004)

---

## 体验流程

```
用户输入需求
    ↓
创建项目
    ↓
选择 Agent
    ↓
执行任务 (真实 LLM)
    ↓
生成 Artifact
    ↓
查看 Audit
```

## 零基础演示(推荐): `factory demo`

AI Factory 内置隔离演示工作区(`~/.factory-demo/`,不污染真实 `~/.factory`):

```bash
# 1. 初始化演示工作区 (创建目录 + providers.json + models.json 种子)
factory demo init

# 2. 查看状态
factory demo status
#   Demo 根目录: ~/.factory-demo (存在)
#   providers.json: 就位 (1 provider, 1 enabled)
#   models.json: 就位 (4 个模型元数据)

# 3. 重置 (清空重建, 绝不碰 ~/.factory)
factory demo reset
```

## 完整演示: 真实项目 + 真实执行

```bash
# 1. 用户输入需求 — 创建一个演示项目目录
mkdir -p /tmp/demo-app && echo "print('hello from AI Factory')" > /tmp/demo-app/main.py

# 2. 创建项目 (注册到 AI Factory)
factory project create --repo-path /tmp/demo-app --name demo-app
#   ✔ 项目注册成功
#     id      P-xxxx

# 3. 选择 Agent (backend-1 = 后端开发 Agent)
factory agent
#   backend-1 | role=backend-developer | skills=[development, python]

# 4. 执行任务 (真实 DeepSeek/OpenAI LLM 调用)
factory run --project /tmp/demo-app --task E2-001 --agent backend-1
#   ✔ 执行完成
#     request_id  EXR-...
#     result_id   EXS-...
#     status      success

# 5. 生成 Artifact — 查看产物
factory run-status --id EXS-...
#   artifact  patch        ~/.factory/exec/patches/EXS-....patch
#   artifact  test_result  ~/.factory/exec/EXS-....test.txt
#   artifact  report       ~/.factory/exec/EXS-....report.md
#   usage     {'prompt_tokens': ..., 'estimated_cost_usd': ...}

# 6. 查看 Audit — 全事件时间线
factory audit
#   按类型计数 + 最近事件 (谁/什么/何时/哪个模型/多少钱)
```

## 前置条件

```bash
# 1. 安装 + 初始化
bash scripts/setup.sh
factory init --non-interactive --provider deepseek

# 2. 配置 LLM key (环境变量, 不落盘)
export DEEPSEEK_API_KEY="sk-..."

# 3. 诊断确认
factory doctor
```

## 演示要点(讲什么)

| 环节 | 讲什么 |
|---|---|
| 真实执行 | "这是真实 DeepSeek API 调用, 不是演示数据" |
| 审批门 | "AI 产出等待人工批准 — 这是治理" |
| 成本透明 | "整个流程成本不到 $0.01" |
| 全审计 | "每一步都记录: 谁/什么/何时/哪个模型/多少钱" |

## 验证: 这是真实执行, 不是 mock

| 证据 | 位置 |
|---|---|
| usage tokens > 0 | `factory run-status` 输出 |
| estimated_cost_usd > 0 | `factory run-status` 输出 |
| 审计事件 (event_seq) | `factory audit` 时间线 |
| patch 文件真实生成 | `~/.factory/exec/patches/EXS-*.patch` |

> 任何一步输出空 usage / 零事件 → 说明链路未真实执行, 请报告问题。

---

*命令均基于 v1.0.0-rc1 验证。真实执行链已在 S10-023 (真实 LLM 闭环) 与 S10-031 (全新环境端到端) 验证。*

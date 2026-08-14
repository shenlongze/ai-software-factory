# Quick Demo — factory demo run 设计

> 位置: docs/product/quick-demo-design.md | Sprint: S10-041 | 只设计, 不实现
> 目标: 一条命令完成首次 AI Factory 体验

---

## 1. 目标

```bash
factory demo run "给 main.py 加一个 hello 函数"
```

一条命令完成: workspace 准备 → project 创建 → task 创建 → agent 执行 → artifact 展示。
**首次体验从 7 步拼接 → 1 条命令(≤5 分钟)。**

## 2. 命令设计

```
factory demo run <goal> [--agent backend-1] [--provider deepseek] [--no-cleanup]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| goal(必填) | — | 目标描述, 如 "创建一个 Todo API" |
| --agent | backend-1 | 执行 Agent |
| --provider | (Router 决策) | 模型 Provider(默认走 Router) |
| --no-cleanup | false | 保留演示目录(默认清理) |

## 3. 内部流程(复用现有能力, 零新 AI)

```
factory demo run "给 main.py 加 hello 函数"
  │
  ├─ 1. workspace 准备: ~/.factory-demo/ (隔离, 复用 demo init 逻辑)
  ├─ 2. project 创建:   建 /tmp/factory-demo-<ts>/  + 写入 main.py 骨架
  │                      (复用 project create 逻辑, 内部调用)
  ├─ 3. task 创建:      生成 task E2-DEMO (objective=goal)
  ├─ 4. agent 执行:     factory run --project <dir> --task E2-DEMO --agent backend-1
  │                      (复用 exec CLI run, 真实 LLM)
  ├─ 5. artifact 展示:  打印 status + usage + patch 摘要
  └─ 6. 清理(默认):     删除临时目录 (--no-cleanup 保留)
```

## 4. 复用点(全部现有, 零新 AI 能力)

| 步骤 | 复用 |
|---|---|
| workspace | cli_factory demo init 逻辑 |
| project | cli_factory project_cmd / org register |
| task | tasks store (或直接 exec run --objective) |
| execute | exec.cli.cmd_exec_run(真实执行链) |
| 展示 | run-status 输出格式化 |

## 5. 输出示例

```
=== AI Factory Quick Demo ===
✔ workspace 就绪 (~/.factory-demo)
✔ 项目已创建: P-xxxx (demo)
✔ 任务: 给 main.py 加 hello 函数
✔ 执行: backend-1 → deepseek (Router 决策)

  status      success
  artifact    patch  ~/.factory-demo/exec/patches/EXS-....patch
  usage       1234 tokens · $0.0009

✔ 完成! 用时 42 秒, 成本 < $0.01
```

## 6. 为什么这是最佳首次体验

| 对比 | 旧路径 | demo run |
|---|---|---|
| 步骤数 | 7+ | 1 |
| 概念门槛 | task 锚点/agent/目录 | 只需描述目标 |
| 时间 | 10-15 分钟(含学习) | ≤5 分钟 |
| 演示完整性 | demo 不执行 | 完整 Idea→Artifact |

## 7. 实现要点(未来实现时)

1. 默认 provider: 走 Router 决策(ControlPlane selected)
2. 失败安全: key 缺失 → 明确提示(不静默)
3. 临时目录: /tmp 下唯一命名, 默认清理
4. 审计: 走正常 exec 链(事件完整记录)
5. 不修改: exec CLI / AgentRuntime / Router(纯 CLI 层组合)

---

> Task 002 完毕 | factory demo run 设计完成 | 复用现有能力, 零新 AI, 只组合

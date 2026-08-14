# CLI User Flow — 未来用户路径设计

> 位置: docs/product/cli-user-flow.md | Sprint: S10-041 | 设计(记录, 分阶段实现)
> 目标: 让 CLI 用户路径从"工具命令"变为"目标驱动"

---

## 1. 当前 CLI 用户路径(命令导向)

```
factory init --non-interactive --provider deepseek     # 配置
export DEEPSEEK_API_KEY=...                            # key
factory doctor                                         # 诊断
factory project create --repo-path ~/my-app            # 项目
factory run --project ~/my-app --task T-001 --agent backend-1   # 任务
factory run-status --id EXS-...                        # 结果
factory audit                                          # 审计
```

**问题**: 用户需理解 provider/task 锚点/agent/result-id 等概念, 命令多而散。

## 2. 未来 CLI 用户路径(目标驱动)

```
阶段 0 (v0.1, 现状): 命令导向 — 功能全, 概念门槛高
阶段 1 (v0.2): 目标导向 — factory demo run 一条命令
阶段 2 (v0.3): 会话导向 — factory task <描述> 交互式
```

### 阶段 1: 目标导向(推荐优先实现)

```bash
# 首次体验: 一条命令
factory demo run "做一个 Todo 应用"      # 自动 目录+任务+执行+展示

# 日常使用: 目标式任务
factory run --objective "给 main.py 加 hello" --project ~/my-app
# (无需 task 锚点 ID; 内部生成 task)

# 显式控制(高级)
factory run --task T-001 --agent tester-1 --project ~/my-app
```

### 阶段 2: 会话导向(远期)

```bash
factory init                 # 一次性配置
factory task                 # 进入交互会话: 描述目标 → 选 agent → 执行 → 查看
```

## 3. 命令演进矩阵

| 命令 | v0.1(现在) | v0.2(建议) | 远期 |
|---|---|---|---|
| factory init | ✅ | ✅ 不变 | ✅ |
| factory doctor | ✅ | ✅ 不变 | ✅ |
| factory config | ✅ | ✅ 不变 | ✅ |
| factory project create | ✅ --repo-path | ✅ + --init(空目录) | ✅ |
| factory run | ✅ --task 锚点 | ✅ + --objective(目标式) | ✅ |
| factory demo run | ❌ 无 | ✅ **新增**(一键演示) | ✅ |
| factory run --wait | ❌ | ✅ 阻塞到完成 | ✅ |

## 4. 用户体验原则

1. **目标优先**: 用户描述"要什么", 平台决定"怎么做"(Router/Agent)
2. **概念渐进**: 首次只用 goal; 高级概念(task/agent/provider)按需暴露
3. **反馈即得**: 每条命令有明确输出(✓/✗ + 下一步)
4. **失败可操作**: 错误消息含修复指引, 不裸抛

## 5. 认知负担目标

| 场景 | 现状 | 目标 |
|---|---|---|
| 首次体验 | 7 步, task 锚点概念 | 1 条命令(factory demo run) |
| 日常任务 | 需 task 锚点 | 目标式 --objective |
| 高级控制 | 概念全暴露 | 按需 --help 进阶 |

## 6. 实现建议(优先级)

```
P1: factory demo run (S10-041-002 设计) — 首次体验
P1: factory run --objective (无 task 锚点) — 日常
P2: factory project create --init — 空目录起步
P2: factory run --wait — 阻塞到完成
```

---

> Task 003 完毕 | CLI 用户路径: 命令导向 → 目标导向(分阶段)

# S10-041 Task 001 — First Experience Audit

> 日期:2026-08-14 | Sprint: S10-041 First UX | 基于真实命令实测(非假设)
> 目标: 分析首次体验的认知负担, 找出阻塞

---

## 1. 当前首次体验路径

```
factory init                  → 配置 LLM
factory project create        → 注册项目
factory run                   → 执行任务
factory demo                  → 隔离演示
```

## 2. 逐步认知负担分析

### factory init

| 项 | 分析 |
|---|---|
| 当前步骤 | factory init --non-interactive --provider deepseek + export DEEPSEEK_API_KEY |
| 用户认知负担 | 低-中: 需理解"provider"概念 + 环境变量注入 |
| 阻塞点 | 无(引导清晰) |
| 优化建议 | init 输出补一句 "下一步: factory doctor 验证" |

### factory project create

| 项 | 分析 |
|---|---|
| 当前步骤 | factory project create --repo-path <dir> --name <name> |
| 用户认知负担 | 中: 需先有项目目录; --repo-path 语义(是目录不是仓库 URL) |
| 阻塞点 | 用户可能没有现成项目 → 卡住 |
| 优化建议 | 支持 --init(自动建空目录 + 最小文件)或 demo 场景自动准备 |

### factory run

| 项 | 分析 |
|---|---|
| 当前步骤 | factory run --project <dir> --task T-001 --agent backend-1 |
| 用户认知负担 | **高**: ① task 锚点 ID 概念(用户问"T-001 是什么?")② agent 概念 ③ project 目录 |
| 阻塞点 | **B2/B3(S10-040 记录)**: 用户不知道任务怎么写、目录从哪来 |
| 优化建议 | run 支持纯目标式: factory run --project <dir> --objective "给 main.py 加 TODO 功能" — 无需 task 锚点 |

### factory demo

| 项 | 分析 |
|---|---|
| 当前步骤 | factory demo init / status / reset |
| 用户认知负担 | 低: 隔离环境, 无概念门槛 |
| 阻塞点 | demo 只是准备 workspace, 不执行任务 → 用户看完仍不知"怎么跑任务" |
| 优化建议 | **factory demo run** 一键: 建目录+建 task+执行+展示(见 Task 002) |

## 3. 认知负担评分

| 命令 | 负担 | 说明 |
|---|---|---|
| factory init | 2/5 | provider + key 概念 |
| factory project create | 3/5 | 需有目录 |
| factory run | **4/5** | task 锚点 + agent + 目录 三概念 |
| factory demo | 2/5 | 简单但不完整 |

**最大负担: factory run 的 task 锚点概念。**

## 4. 阻塞点(最终清单)

| # | 阻塞 | 严重度 | 影响 |
|---|---|---|---|
| B1 | 私有仓库(分发) | P0 | 陌生用户无法 clone |
| B2 | run 需 task 锚点 ID | P1 | 用户不知怎么写任务 |
| B3 | 需手动准备项目目录 | P1 | 用户卡在"我没有项目" |
| B4 | demo 不执行任务 | P1 | 演示不完整 |
| B5 | 5 分钟路径散在多命令 | P1 | 用户需读文档拼接 |

## 5. 优化建议(设计方向)

```
方案 A (推荐): factory demo run <goal>
  一条命令: 自动建目录 + 建 task + 选 agent + 真实执行 + 展示 artifact
  → 消除 B2/B3/B4/B5, 首次体验从"7 步拼接"变"1 条命令"

方案 B: factory run --objective "..." (目标式)
  → 消除 B2(task 锚点), 保留手动目录

方案 C: init 后引导完整路径 (interactive walkthrough)
  → 降低认知负担, 但交互复杂
```

**推荐: 方案 A(demo run)为主 + 方案 B(run --objective)为辅。**

## 6. 结论

- 首次体验功能通(实测), 但 **run 的 task 锚点概念是最大认知门槛**
- **factory demo run 一条命令** 是最优解法(消除 4 个阻塞)
- 文档应围绕"5 分钟一条命令"重构(Task 004)

---

> Task 001 完毕 | 最大阻塞: run task 锚点概念 | 最优解: factory demo run 一键化

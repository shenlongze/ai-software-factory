# S10-040 Task 001 — User Journey Audit

> 日期:2026-08-14 | Sprint: S10-040 User Validation | 基于真实用户路径分析(实测验证过)
> 目标: 分析新用户完整路径, 找出体验阻塞与改进点

---

## 1. 用户目标

**新用户目标: 在 5-10 分钟内, 安装 AI Factory, 配置好 LLM, 运行第一个真实 AI 任务, 看到产物。**

## 2. 操作步骤与当前体验

| 步骤 | 操作 | 当前体验 | 阻塞点 |
|---|---|---|---|
| 1. install | git clone + bash scripts/setup.sh | ✅ 自动(venv + 依赖 + 冒烟) | 仓库私有(外部用户需授权) |
| 2. init | factory init --non-interactive --provider deepseek | ✅ 3 ✓(环境/workspace/providers.json) | 无 |
| 3. doctor | factory doctor | ✅ 诊断 5 维 PASS/WARN/FAIL | WARN 需用户自己理解(有提示) |
| 4. config | export DEEPSEEK_API_KEY + factory config show | ✅ key 环境注入(不落盘) | 用户需知道"export 环境变量" |
| 5. project create | factory project create --repo-path <dir> | ✅ 真实注册 P-xxx | 需先有项目目录 |
| 6. run | factory run --project --task --agent | ✅ 真实 DeepSeek 执行 | ① 需 --task 锚点 ID(概念门槛) ② 需手动 mkdir 项目目录 |
| 7. artifact | factory run-status --id <id> | ✅ patch/report/usage | 结果 ID 需从上一步复制 |

## 3. 体验评分(每步)

| 步骤 | 评分 | 说明 |
|---|---|---|
| install | 8/10 | 自动但私有仓库阻塞分发 |
| init | 9/10 | 引导清晰 |
| doctor | 8/10 | 诊断清晰, WARN 可操作 |
| config | 7/10 | key 概念需理解(环境变量) |
| project create | 8/10 | 简单 |
| run | 6/10 | **task 锚点 ID 概念 + 手动目录 = 最高门槛** |
| artifact | 7/10 | 结果 ID 复制不便 |

**整体: 7.6/10 — 可用, 但 run 步骤有认知门槛。**

## 4. 阻塞点(按严重度)

| # | 阻塞 | 严重度 | 影响 |
|---|---|---|---|
| B1 | **私有仓库** | 高 | 陌生用户无法 clone(分发) |
| B2 | **task 锚点 ID 概念** | 中 | 用户不知 --task T-001 含义(README 有说明但需读) |
| B3 | **需手动建项目目录** | 中 | run 前需 mkdir + 放文件 |
| B4 | **key 环境变量概念** | 低 | 非技术用户不熟悉 export |
| B5 | **结果 ID 复制** | 低 | run-status --id 需手动复制 |

## 5. 改进建议(记录, 非本 Sprint 实现)

| # | 建议 | 优先级 |
|---|---|---|
| 1 | 仓库转公开(消除 B1) | P0(用户决策) |
| 2 | `factory run` 缺省 task 用"生成式目标"(--objective 直接描述, 无锚点 ID) | P1 |
| 3 | `factory demo run <goal>` 一键: 自动建目录 + 建 task + 执行 + 展示(消除 B2/B3/B5) | P1 |
| 4 | README/Quick Start 强调 key 环境变量(已有, 可加截图) | P2 |
| 5 | run-status 支持 `factory run --wait`(阻塞到完成并打印结果) | P2 |

## 6. 结论

- **用户路径功能上全通**(S10-031/035 实测: install→init→doctor→config→project→run→artifact)
- **体验门槛**: run 步骤的 task 锚点概念 + 手动目录准备
- **最大阻塞**: 私有仓库(外部用户不可达)
- **下一验证目标**: 种子用户实测 5 分钟体验, 收集反馈

---

> Task 001 完毕 | 用户路径 7.6/10 | 阻塞: 私有仓库(P0) + task 概念(P1) + demo run 一键化(P1 建议)

# AI Factory — CLI 命令参考文档 v1.0

> 生成日期: 2026-08-12 | 方式: 实测运行 + 代码核对
> 说明: 记录当前 CLI 的**真实情况** — 命令组、子命令、实测状态、前置条件
> 入口: `factory` (安装后) 或 `.venv/bin/factory` · 全局参数: `--root <工厂根>` `--json`

---

## 0. 总览

| 指标 | 值 |
|:---|:---|
| 命令组 | 26 个 (顶层) |
| 命令函数 (cmd_*) | 91 个 |
| 入口 | `factory [--root ROOT] [--json] <命令组> <子命令>` |
| 数据 | 事件溯源 (append-only SQLite) + JSON 目录信源 |
| 实测基线 | 纯本地命令 ✅ 全通; 需 LLM/外部工具的命令 → 诚实失败 |

**实测结论 (2026-08-12):**
- **纯本地、无外部依赖的命令:全部真实可用** (init/task/agent/skill/workflow/product 生命周期等, 实测通过)
- **需真实 LLM/外部工具的命令:诚实失败** (明确报错原因, 不崩溃不伪造, 事件已记录) — 非 bug, 是需要前置条件
- **无"存在但坏了"的命令** — 所有命令可运行, 错误处理健全

---

## 1. 工厂基础 (4 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory init` | 初始化工厂: 目录骨架+事件库 (幂等) | ✅ 全通 | 无 |
| `factory status` | 总览: Projects/Tasks/Agents/Events 计数 | ✅ 全通 | 无 |
| `factory event logs` | 事件日志查询 | ✅ 全通 | 无 |
| `factory validate` | 三层验证引擎 L1/L2/L3 | ✅ 全通 | 无 |

## 2. 任务管理 (4 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory task create --title ...` | 创建任务 | ✅ 全通 | 无 |
| `factory task list` | 任务清单 | ✅ 全通 | 无 |
| `factory task status <id>` | 任务详情 | ✅ 全通 | 无 |
| `factory task update <id>` | 更新任务 | ✅ 全通 | 无 |

**Task 状态**: BACKLOG → ARCHITECTURE → DEVELOPMENT → TESTING → DONE

## 3. 智能体与技能 (8 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory agent add --id --role --skills` | 注册 Agent | ✅ 全通 | 无 |
| `factory agent list` | Agent 清单 | ✅ 全通 | 无 |
| `factory agent assign` | 分配 Agent 到任务 | ✅ 全通 | 无 |
| `factory agent assignments` | 分配记录 | ✅ 全通 | 无 |
| `factory agent release` | 释放 Agent | ✅ 全通 | 无 |
| `factory skill add --id --name` | 注册技能 | ✅ 全通 | 无 |
| `factory skill list` | 技能清单 | ✅ 全通 | 无 |

## 4. 工作流 (4 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory workflow list` | 工作流定义 | ✅ 全通 | 无 |
| `factory workflow add --id [--steps]` | 注册工作流 | ✅ 全通 | 无 |
| `factory workflow run <task> [--auto]` | 启动/自动执行 | ✅ 全通 | 需 Agent+Runtime |
| `factory workflow status <task>` | 工作流进度 | ✅ 全通 | 无 |

**状态**: Workflow: CREATED/RUNNING/COMPLETED/FAILED · Step: PENDING/RUNNING/COMPLETED/FAILED
**注意**: `run --auto` 完整自动执行需已注册 Agent(role/skill 匹配)+ Runtime

## 5. 运行时 (5 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory runtime add --id [--type]` | 注册运行时 | ✅ 全通 | 无 |
| `factory runtime list` | 运行时清单 | ✅ 全通 | 无 |
| `factory runtime test <id>` | 冒烟测试 | ⚠️ 诚实失败 | 需 adapter 可执行 (hermes 需装 CLI) |
| `factory runtime catalog list` | 能力目录 | ✅ 全通 | 无 |
| `factory runtime catalog show <id>` | 目录详情 | ✅ 全通 | 无 |

**内置**: hermes (需 CLI) / echo (mock) / mock

## 6. LLM Provider (7 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory provider list` | Provider 注册表 | ✅ 全通 | 无 |
| `factory provider show <id>` | Provider 详情 | ✅ 全通 | 无 |
| `factory provider test <id>` | 冒烟测试 | ⚠️ 诚实失败 | 需 API key/CLI |
| `factory provider usage` | 用量记录 | ✅ 全通 | 无 |
| `factory provider stats` | 性能统计 | ✅ 全通 | 无 |
| `factory provider compare` | 对比 | ✅ 全通 | 无 |
| `factory provider recommend` | 四因素推荐 | ✅ 全通 | 需 TaskRequirement |

**推荐**: score = 0.4×capability + 0.3×cost + 0.3×performance

## 7. 执行 (3 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory execution list` | 执行记录 | ✅ 全通 | 无 |
| `factory execution run` | 触发执行 | ✅ 全通 | 需 Provider |
| `factory execution status` | 执行状态 | ✅ 全通 | 无 |

## 8. 恢复与检查点 (3 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory checkpoint create <task>` | 停靠点快照 | ✅ 全通 | 无 |
| `factory checkpoint list` | 快照清单 | ✅ 全通 | 无 |
| `factory recover <task>` | 事件回放恢复 | ✅ 全通 | 需事件 |

## 9. 观测 (2 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory dashboard [--view]` | 控制台总览 (Rich) | ✅ 全通 | 无 |
| `factory metrics` | 六域指标 | ✅ 全通 | 无 |

## 10. 工作区与项目 (4 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory workspace init` | 初始化工作区 | ✅ 全通 | 无 |
| `factory workspace show` | 工作区状态 | ✅ 全通 | 无 |
| `factory project list` | 项目清单 (examples/*/project.yaml) | ✅ 全通 | 无 |
| `factory project show <name>` | 项目详情 | ✅ 全通 | 无 |

## 11. Git 与变更 (9 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory git status` | Git 状态 (只读) | ✅ | 需 git 仓库 |
| `factory git diff` | Git 差异 (只读) | ✅ | 需 git 仓库 |
| `factory git commits` | 提交记录 | ✅ | 需 git 仓库 |
| `factory change commits` | 提交-任务关联 | ✅ | 需 git 仓库 |
| `factory change analyze` | 变更分析 | ✅ | 需 git 仓库 |
| `factory change validate` | L4 验证 | ✅ | 需 git 仓库 |
| `factory change triggers list` | 触发器清单 | ✅ 全通 | 无 |
| `factory change triggers register` | 注册触发器 | ✅ 全通 | 无 |
| `factory change evaluate/workflows` | 评估/联动 | ✅ | 需场景 |

## 12. 项目理解 (1 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory understand <path>` | 项目理解报告 | ✅ | 需项目目录 |

## 13. Product 智能 (19 命令, 最大组)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory product idea create/list/show` | 想法管理 | ✅ 全通 | 无 |
| `factory product approval request/decide/list/history` | 审批门 | ✅ 全通 | 无 |
| `factory product workflow start/status/resume` | 产品工作流 | ✅ 全通 | 无 |
| `factory product generate --type {research,prd,ui}` | AI 生成产物 | ⚠️ 诚实失败 | 需真实 LLM |
| `factory product experience list/record` | 经验记录 | ✅ 全通 | 无 |
| `factory product lifecycle start/status/advance/templates` | 生命周期 | ✅ 全通 (实测流转) | 无 |

**生命周期**: software_project 8 阶段: idea→research→prd→approval→ui→approval→architecture→task

## 14. 决策智能 (4 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory intelligence decision create` | 决策链 | ✅ | 需 evidence (强制) |
| `factory intelligence recommend` | 推荐 | ✅ | 需 options |
| `factory intelligence experience list/evaluate` | 经验 | ✅ 全通 | 无 |

**规则**: 禁无证据决策 (NoEvidenceError); 高风险→审批绑定

## 15. Console (2 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory console dashboard` | Console 数据 | ✅ 全通 | 无 |
| `factory console approvals` | 审批数据 | ✅ 全通 | 无 |

## 16. 组织建模 (7 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory org company create/show` | 公司 | ✅ 全通 | 无 |
| `factory org employee hire/list` | 员工 | ✅ 全通 | 无 |
| `factory org authority check` | 权限 (Default Deny) | ✅ 全通 | 无 |
| `factory org knowledge add/list` | 知识 | ✅ 全通 | 无 |

## 17. exec 执行 (6 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory exec run` | 真实执行 (沙箱+Provider) | ⚠️ 诚实失败 | **需真实 LLM (API key)** |
| `factory exec status` | 执行结果 | ✅ 全通 | 无 |
| `factory exec approval approve/deny/apply/list` | 执行审批 | ✅ 全通 | 无 |

## 18. 积压清道夫与审批 (M1b/M1 闭环, 6 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory workload backlog --project <dir>` | 积压清道夫: 分诊→执行→证据包→审批→报告 | ✅ 全通 (demo 全 dependency 3/3 确定性修完) | 无 |
| `factory workload status --project <dir>` | 最近一次清道夫运行报告 | ✅ 全通 | 无 |
| `factory approval list [--project X]` | 待审批列表 (复用 ApprovalGate; 每行附证据包 id) | ✅ 全通 | 无 |
| `factory approval decide <id> approve\|reject` | 审批决策 (终态落库+审计; approve 后提示下一步) | ✅ 全通 | 无 |
| `factory approval apply <id> [--project <dir>]` | 应用已批准 patch (ApprovalGate.apply 薄代理; 未批准/非 git 硬拒绝) | ✅ 全通 | **已批准** |
| `factory evidence list/show` | 证据包视图 (M1a; show 附关联审批状态) | ✅ 全通 | 无 |

## 19. 演示 (1 命令)

| 命令 | 作用 | 实测 | 前置 |
|:---|:---|:---|:---|
| `factory demo markpad` | 一键完整生命周期演示 | ✅ 全通 (实测50事件) | Mock Provider |

---

## 关键认知

1. **91 命令无"存在但坏了"的** — 全部可运行, 错误处理健全
2. **分三档**:
   - ✅ 纯本地命令 (约 70 个): 真实可用, 实测通过
   - ⚠️ 需真实 LLM (exec run / product generate / provider test): 诚实失败, 需 API key
   - ⚠️ 需外部工具 (provider test hermes): 诚实失败, 需安装 CLI
3. **"诚实失败"是特性不是 bug** — runtime=None → 明确 FAILED; LLM 缺 key → 明确报错; 不伪造成功
4. **业务价值的关键 = 接真实 Provider** — 命令骨架全在, 但"产出真东西"依赖真实 LLM (v1 命门)
5. **无独立命令手册文档** — 本文件补上; 此前靠 `factory --help` 现查

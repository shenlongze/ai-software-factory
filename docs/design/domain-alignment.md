# 域清单对齐（刀0）

> 日期: 2026-09-15 | 性质: **设计（提案 · 待 Founder 裁决）** | 依据: 全仓实测, commit `c0e04f23`
> Founder 口径（2026-09-15 原话）:
> **"我要做的代码必须严格分类，严格管理，不能东一个西一个"**
> 改动范围: **零代码** —— 只对齐口径, 不动任何 .py
> 存活期: 裁决后并入 `docs/ssot/`, 本文删除（避免出现第二份事实源）

## 0. 一句话

域清单现在有**三份且互不相同**, 所以 `api-structure.md` §8 的刀2（"迁 7 个已同源的域"）没有参照系。
要做的**不是**把 9 / 12 / 14 凑成一个数 —— 它们本来就是四层不同的东西:

| 层 | 是什么 | 举例 | 该由谁定 |
|---|---|---|---|
| 契约域 | `contracts/` 跨层 DTO, 无逻辑无 IO | `contracts/work.py` | SSoT · arch |
| 服务域 | `services/<域>/` 域用例 = 唯一业务入口 | `services/work/` | SSoT · arch |
| API 分组 | `api/domains/<域>/` HTTP 适配, URL 前缀 | `/api/work` | `api-structure.md` |
| 产品环 | 生命周期视图（idea→…→自动修复） | "任务拆解" | SSoT · product |

⇒ 缺的东西只有一样: **每层各留一份权威清单 + 三层必须一一对应 + 中间一张映射表**。

## 1. 四层实测对照（2026-09-15）

| 层 | 权威文档 | 文档写的 | 实测 | 差异 |
|---|---|---|---|---|
| 契约域 `contracts/` | ssot/architecture.md §二 | 11 | **12** | 多 `llm`（3 文件, 已在使用, 未登记） |
| 服务域 `services/` | ssot/architecture.md §四 | 7 | **9** | 多 `metrics` · `validation` |
| API 分组 `api/domains/` | api-structure.md §1 | 14 | **14** | 数一致, 但 **0 接线**（14×3 py, router 各 13 行） |
| 产品环 | 无文档 | — | — | 未落 SSoT |
| 老区端点 | api-structure.md §6 | 391 端点 | **392 端点 / 71 组** | 端点 +1, 组数未登记 |

实测明细（可复现, 见 §8）:

```
contracts 12   conversation errors events execution governance identity
               learning llm organization resource scheduling work
services   9   conversation execution governance learning metrics
               organization resource validation work
api/domains 14 conversation understanding architecture decomposition orchestration
               execution validation delivery operations metrics audit governance
               organization platform
```

## 2. 服务域 ↔ CLI / API 接线真相（实测 import 点）

| 服务域 | CLI 侧 | API 侧（在跑） | 判定 |
|---|---|---|---|
| `organization` | 1 | 1 | ★ 双侧同源 |
| `work` | 2 | 1 | 双侧（API 1 处） |
| `learning` | 1 | 1 | 双侧（API 1 处） |
| `conversation` | 1 | 0 | 仅 CLI |
| `execution` | 1 | 0 | 仅 CLI |
| `metrics` | 2 | 0 | 仅 CLI |
| `validation` | 1 | 0 | 仅 CLI |
| `governance` | 0 | 0 | ✗ 两侧都没接（实现在 services/governance, 消费方仍走老区 governance_service） |
| `resource` | 0 | 0 | 仅 `__init__.py`（契约声明, 无实现无消费 —— 见 D2） |

> 注: **API（新）`api/domains/` 对全部 9 域 = 0** —— 空壳未接线（刀1 只建骨架, 与文档一致）。

★ **顺带解开刀2 的"7 个"**: 实测 CLI 侧有接线的服务域 =
`conversation` · `execution` · `learning` · `metrics` · `organization` · `validation` · `work` = **正好 7 个** ✓
例外 2 个: `governance`（两侧都没接）· `resource`（仅声明）。
⇒ 刀2 可精确写成: **给这 7 个域补 API 侧接线**。

## 3. 映射表（产品环 ↔ 服务域 ↔ API 分组 ↔ 老区组）

| # | 产品环 | 服务域（实测） | API 分组 | 老区组（实测端点数） |
|---|---|---|---|---|
| 1 | 会话 | `conversation` | conversation | conversations 17 · sessions 14 |
| 2 | 需求分析 | ✗ 无 | understanding | （api-structure 定: 并入 conversations） |
| 3 | 架构分析 | ✗ 无 | architecture | ✗ 老区无对应组 |
| 4 | 任务拆解 | `work` | decomposition | task-trees 3 · tasks 3 · schedules 5 |
| 5 | 编排 | ✗ 无独立域（在 `services/execution/orchestration/`） | orchestration | workflows 3 · projects 65 · projects-os 5 · board 12 |
| 6 | 执行 | `execution` | execution | production-runs 15 · runtimes 4 · runtime-sessions 6 · agents 8 · runtime 1 · runs 2 |
| 7 | 验收 | `validation` | validation | acceptances 3 · approval-gates 1 |
| 8 | 交付 | ✗ 无 | delivery | releases 11 · releases-truth 1 · rollbacks 6 · artifacts 3 |
| 9 | 运维 | ✗ 无（恢复在 `services/execution/recovery/`） | operations | incidents 7 · ops 4 · recovery 4 · health-incidents 3 · operations 2 |
| 10 | 监控 | `metrics` | metrics | control-tower 4 · monitor 1 · decisions 1 |
| 11 | 审计 | ✗ 无独立域（在 `services/governance/audit/`） | audit | audit 2 |
| 12 | 治理 | `governance` | governance | approvals 5 · approval-requests 4 · approval-gates 1 |
| — | 基座: 组织/人力 | `organization` | organization | workforces 7 · workforce 4 · workforce-os 1 · organizations 2 · agents 8 · skills 4 · agent-profiles 4 · agent-runs 4 · capabilities 2 · mcp 4 · plugins 8 |
| — | 基座: 平台 | ✗ 无 | platform | config 5 · dashboard 1 · system 2 · providers 1 · tools 2 · local-ai 3 |
| — | 基座: 学习 | `learning` | ✗ 无（14 域里没有） | intelligence 7 · learning 5 · experiences 4 · experience 1 · promotions 7 · recommendations 2 · selection 1 · review-feedback 2 · rag 2 · experiments 11 · experiment-samples 2 · optimization 23 · optimizations 5 · external-ai 13 |
| — | 无归属 → 待裁决 | `resource` | — | entities 4 · handoffs 2 · runs 2 · events 1 · exec 1 · contracts 1 · memory 7 · memory-conflicts 2 · context 7 |

统计（每端点唯一归属）:

```
已归环(12 环 + 组织 + 平台)  279      拆解 11 · 编排 85 · 组织 48 · 会话 31 · 执行 28
                                     交付 21 · 运维 20 · 平台 14 · 治理 9 · 监控 6
                                     验收 4 · 审计 2  （需求分析/架构分析 = 0）
learning 族（无环归属）        85
待裁决                         25
非 API（/health /ready /version）  3
                               ───
合计                          392  ✓（端点数复核一致）
```

## 4. ★ 严格分类口径（Founder 2026-09-15）→ 四条铁律 + 机器强制

Founder 要求"严格分类、严格管理、不能东一个西一个"。落实为四条**可机器强制**的规则
（与 SSoT §三 的 R1–R17 同性质, 建议编号 **R18–R21**）:

| # | 铁律 | 强制方式（守卫脚本） |
|---|---|---|
| **R18** | **一能力一域**: 一个能力的实现全仓只能有一处 = `services/<域>/` | 同一能力词根出现在 >1 个 services 子域 → 报红 |
| **R19** | **一物一名**: 同一实体不得有两个名字（禁单复数并存 / 禁 `-os` `-truth` `-sessions` 后缀变体） | 扫 API 路径第一段, 按词根聚类, 一族 >1 组 → 报红（现为红, 见 §5） |
| **R20** | **清单单一**: 域清单只在 `ssot/architecture.md` 有一份; 代码目录与 `api-structure.md` 必须由它派生 | 解析 SSoT 域清单 vs 实测 `contracts/` `services/` `api/domains/` 目录, 三方不一致 → 报红（现为红） |
| **R21** | **一域一落点**: 每个域在 `services/<域>/` 与 `api/domains/<域>/` 同名同存 | 目录名集合比对（现为红: 见 §1 三份清单） |

> 这四条只有 R19 是"新增守卫"; R18/R20/R21 可复用已有的目录扫描能力。
> **不建守卫 = 口号; 建了守卫 = "严格管理"有据可查。**

## 5. ★ 违反清单（实测 —— 这就是"东一个西一个"）

### 5.1 同一实体的名字变体（违反 R19）—— 11 个词根 / 192 端点 / 占全仓 48%

| 词根 | 端点 | 并存的名字 |
|---|---|---|
| project | 70 | `projects` 65 · `projects-os` 5 |
| optimization | 28 | `optimization` 23 · `optimizations` 5 |
| agent | 16 | `agents` 8 · `agent-runs` 4 · `agent-profiles` 4 |
| experiment | 13 | `experiments` 11 · `experiment-samples` 2 |
| release | 12 | `releases` 11 · `releases-truth` 1 |
| workforce | 12 | `workforces` 7 · `workforce` 4 · `workforce-os` 1 |
| runtime | 11 | `runtime-sessions` 6 · `runtimes` 4 · `runtime` 1 |
| approval | 10 | `approvals` 5 · `approval-requests` 4 · `approval-gates` 1 |
| memory | 9 | `memory` 7 · `memory-conflicts` 2 |
| task | 6 | `tasks` 3 · `task-trees` 3 |
| experience | 5 | `experiences` 4 · `experience` 1 |

### 5.2 语义重复但名字完全不同（R19 也漏掉的）—— 6 处 / 91 端点

| 能力 | 并存实现 | 端点 | 文档是否已定性 |
|---|---|---|---|
| 会话 | `conversations` 17 · `sessions` 14 | 31 | ✔ api-structure §7 已定"择一留 canonical" |
| 编排 | `workflows` 3 · `projects` 65 · `projects-os` 5 · `board` 12 | 85 | ✔ §7 已定"主链 golden_path" |
| 运行 | `production-runs` 15 · `runs` 2 | 17 | ✗ 待定性 |
| 学习 | `learning` 5 · `intelligence` 7 | 12 | ✗ 待定性 |
| 事件 | `incidents` 7 · `health-incidents` 3 | 10 | ✗ 待定性 |
| 运维 | `ops` 4 · `operations` 2 | 6 | ✗ 待定性 |

> 5.1 + 5.2 = **283 / 392 端点（72%）** 处在"同一能力多处并存"状态 —— 这就是 Founder 说的"东一个西一个"的量化。
> 算式: 192 + 161 − 70（`projects` 70 在 5.1 已计, 此处扣除）= 283。

## 6. 要你定的四件事（各一句话）

| # | 问题 | 我的建议 |
|---|---|---|
| **D1** | 服务域清单以谁为准? | **以产品环 1:1 为准 = 15 个域**: 12 环 + 组织 + 平台 + 学习。实测只有 9 个 ⇒ **缺 6 个要建**（需求分析 · 架构分析 · 编排 · 交付 · 运维 · 审计）; API 侧 14 个 ⇒ 补 `learning` 一个 |
| **D2** | `resource` 怎么处置? | **保留**。代码自述定性: "能力声明 / 实现绑定 / 解析", 拥有 `contracts/resource.py`, `core.scheduler.ports.ResourcePort` 读它 ⇒ 是**已声明未实现**, 不是误建。标注状态, 不删 |
| **D3** | 产品 12 环这个口径? | 落进 `ssot/product.md`（现在只存在于对话里, 不可审计） |
| **D4** | R18–R21 四条分类铁律? | **批准并进验证据组** —— 不建守卫, "严格分类"就只是口号 |

## 7. 批准后的落地（仍为零代码）

1. `ssot/architecture.md` §二: 契约域 11 → 12（登记 `llm`）
2. `ssot/architecture.md` §四: services 目录树 7 → 9（补 `metrics` `validation`）
3. `ssot/architecture.md` §三: 加 R18–R21 四条分类铁律
4. `ssot/architecture.md`: 加一句 —— "域清单以本节为**单一事实源**, 改动需显式裁决"
5. `ssot/product.md`: 落产品环（12 环 + 3 基座）
6. `api-structure.md` §8 刀2: 写明"7 个" = `conversation` `execution` `learning` `metrics` `organization` `validation` `work`
7. 本文删除（口径已并入 SSoT）

## 8. 实测复现命令

```bash
# 契约域 / 服务域 / API 分组 清单
ls -1 src/ai_factory_os/contracts src/ai_factory_os/services src/ai_factory_os/api/domains
# 老区端点总数
grep -c '@app\.\(get\|post\|put\|delete\|patch\)' \
  src/ai_factory_os/_pending_migration/factory_console/web/backend/fastapi_adapter.py
# 名字变体检测（R19 守卫雏形）: 取 /api/<第一段> 按词根聚类, 一族 >1 组即报红
```

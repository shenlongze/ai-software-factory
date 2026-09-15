# AI Factory OS — 目标架构（SSoT v0.3）

> 状态：**生效** | 改动需显式裁决 | 根布局定案见 `docs/adr/0037-root-layout-decision.md`
> 上一版：v0.2（"内核六段 / 8 根契约 / 8 条铁律"）—— 已与实现脱节，本版对齐实际。

## 一、七层结构

| 层 | 职责 | 允许依赖 |
|----|------|---------|
| `contracts/` | 全部跨层契约（dataclass / Enum / Protocol），无逻辑、无 IO | 仅标准库 |
| `core/` | 平台本体：**scheduler**（决定下一步是谁）+ **events**（记录发生了什么），仅此两段 | `contracts/` |
| `services/` | 业务域服务（每域：service / store / rules / events / contracts） | `contracts/` |
| `plugins/` | 一切实现绑定（factories / agents / skills / tools / mcp / models / connectors / controllers / healers / notifiers / triggers / storages） | `contracts/` |
| `infrastructure/` | 技术底座（llm / storage / messaging / process / sandbox） | `contracts/` |
| `api/` | 对外接口层（路由 / DTO 装配） | `contracts/` + `services/` |
| `bootstrap/` | 装配与启动（唯一可 import 全部） | 全部 |

**`apps/` 独立于 `src/`**（cli / web / desktop / mobile 作为消费者，不进包内）。

## 二、域清单（单一事实源，以实现为准）

三份清单，各自为唯一权威；`services/` 与 `api/domains/` 的目录必须与本节一致，
漂移由守卫 `scripts/check_classification.py` 报红（R20/R21）。

**契约域（`contracts/`，12）**

`identity` · `organization` · `work` · `resource` · `execution` · `governance` ·
`learning` · `conversation` · `scheduling` · `events` · `errors` · `llm`

**服务域（`services/`，9）**

`conversation` · `execution` · `governance` · `learning` · `metrics` ·
`organization` · `resource` · `validation` · `work`

**API 分组（`api/domains/`，15）**

`conversation` · `understanding` · `architecture` · `decomposition` · `orchestration` ·
`execution` · `validation` · `delivery` · `learning` · `operations` · `metrics` · `audit` ·
`governance` · `organization` · `platform`

> `learning` 为 2026-09-15 补入：契约域与服务域都有它、产品核心也认「学习自治」，
> 唯独 API 面漏了 ⇒ 三层（契约 / 服务 / API）对齐后由 14 增至 15。

> 与 v0.2 的差异：`project` 并入 `work`（同一概念不留两个名字）；
> 新增 `resource` / `learning` / `conversation` / `scheduling`；
> 不再使用"8 根 + 5 内核"的分法。
>
> **2026-09-15 实测订正（刀0）**：`llm` 已存在且已在使用（`contracts/llm/{provider,routing}.py`，
> 智能路由 L1/L5 兜底即依赖它），但未登记 ⇒ 契约域 11 → **12**；
> 服务域补 `metrics` / `validation`（实测已存在）⇒ 7 → **9**。

## 三、依赖铁律（22 条）

> **强制载体现状（2026-09-15 实测）**：R1–R17 原载体 `tests/architecture/*.py` 已不存在（刀29 清理）。
> **已重建**：`scripts/check_architecture.py`（AST 解析 import，含相对导入与 lazy import；
> 解析器自检 `--selftest` 8/8；实测 **6/15 条通过**）。
> **R18–R22 已建成**：`scripts/check_classification.py`（自检 `--selftest` 8/8）。
> 验证据组 = **`bash scripts/verify.sh`（唯一入口）** = `ruff` + `scripts/check_imports.py`
> + `scripts/check_architecture.py` + `scripts/check_classification.py` + 目标实跑。
> 两段式: ①**工具健康**（ruff / 导入 / 两个守卫自检）计入退出码；②守卫扫出的**存量红**作为
> 债务清单报告, 默认不阻塞（`--strict` 可让债务也阻塞）。
> 注: `pytest` 在本仓不构成验证（`tests/` 已删 且 R16 禁止新增顶层目录）。
> R14/R15（旧区"只减不增"）需基线文件 `scripts/legacy_baseline.json`（**未建**，脚本如实报"无基线"）。

**层级边界（R1–R12、R17）** —— 载体 `scripts/check_architecture.py`

| # | 规则 |
|---|------|
| R1 | `contracts/*` 不许 import 其他顶层包 |
| R2 | `core/*` 只许 import `contracts` |
| R3 | `services/A` 不许 import `services/B` 的实现 |
| R4 | `plugins/*` 只许 import `contracts` |
| R5 | `infrastructure/*` 只许 import `contracts` |
| R6 | `api/*` 不许 import `infrastructure` 的具体实现 |
| R7 | `apps/*` 不许出现在 `src/` 内 |
| R8 | `bootstrap/*` 例外（可 import 全部） |
| R9 | `contracts/*` 不许含控制流（if/for/while/try/with） |
| R10 | 禁用文件名 11 个（`models.py` `utils.py` `common.py` …）—— 防再长出 25 个 `models.py` |
| R11 | `services/<域>/` 内文件 ⊆ 五件套（service / store / rules / events / contracts） |
| R12 | `core/` 无业务词，且总行数 ≤ 3000 |
| R17 | `core/` 只允许 `scheduler` / `events` 两个子模块 |

**旧代码围栏（R13–R16）** —— 载体 `scripts/check_architecture.py`（R14/R15 待建基线）

| # | 规则 |
|---|------|
| R13 | 新地基不许 import 旧代码（迁移期走 `migration_allowlist.json`，**只减不增**） |
| R14 | 旧代码文件只减不增（文件集 ⊆ 基线，总行数 ≤ 基线） |
| R15 | 旧代码跨分区依赖边只减不增 |
| R16 | 不许新增顶层代码目录 |

**分类铁律（R18–R22）** —— Founder 2026-09-15: **"代码必须严格分类，严格管理，不能东一个西一个"**

| # | 规则 | 现状 |
|---|------|------|
| R18 | **一能力一域**：一个能力的实现全仓只有一处 = `services/<域>/`（同一能力词根不得出现在 >1 个服务域） | 红（待收口） |
| R19 | **一物一名**：同一实体不得两个名字（禁单复数并存 · 禁 `-os` `-truth` `-sessions` 等变体） | 红（11 词根 / 192 端点） |
| R20 | **清单单一**：域清单只在 §二 一份；`services/` 与 `api/domains/` 由它派生 | 红（三份不一致） |
| R21 | **一域一落点**：`services/<域>/` 与 `api/domains/<域>/` 同名同存 | 红 |
| R22 | **一层一目录（禁平铺）**：同类东西必须进对应目录，不许把一个层级的文件平铺在同一处（同目录 >30 个 .py 且前缀 ≥20 种即为平铺） | 红（老区顶层 117 个 .py 平铺，57 个前缀各 1 个文件） |

> Founder 原话的落点：**R22 = "不放在一起，乱"**；R18–R21 = "严格分类"。
> 违反清单（实测，含端点级证据）见本刀 commit 与 `docs/design/domain-alignment.md`。
> **这五条只在建成守卫后才有约束力** —— 未建守卫前为"目标态"，不得据此判他人代码违规。

## 四、目录树（现役）

```
src/ai_factory_os/
├── contracts/     identity organization work resource execution governance
│                  learning conversation scheduling events errors llm
├── core/          scheduler events
├── services/      conversation execution governance learning metrics
│                  organization resource validation work
├── plugins/       factories/{software} agents skills tools mcp models connectors
│                  controllers/{browser,computer} healers notifiers triggers storages
├── infrastructure/ llm storage messaging process sandbox
├── api/
└── bootstrap/

apps/              cli（web / desktop / mobile 待迁）
tests/             ✗ 已不存在（刀29 清理）—— 验证据组 = ruff + scripts/ + 目标实跑
docs/              ssot（product/arch/reality）· adr · architecture · design · cleanup
scripts/           check_imports.py · migration_check.py · legacy_inventory.py · legacy_reach.py
bin/               factory
```

## 五、根目录的目标形态

```
src/  apps/  tests/  docs/  scripts/  bin/
README.md  LICENSE  CHANGELOG.md  CONTRIBUTING.md  CODE_OF_CONDUCT.md
SECURITY.md  OPEN-CORE.md  AGENTS.md  pyproject.toml
+ 运行时目录（projects/ workspace/ exec/ —— 已 gitignore）
```

**判定标准：根下不存在任何 `factory-*`。** 当前仍有 6 个
（`factory-console` 311 py · `factory-core` 138 · `factory-exec` 51 ·
`factory-org` 18 · `factory-runtime` 12 · `factory_console` 2），
它们的消失只能通过绞杀搬迁达成 —— 见 `docs/cleanup/LEGACY-LEDGER.md`。

## 六、三层 SSoT

| 层 | 文件 | 性质 |
|---|---|---|
| product | `docs/ssot/product.md` | 人写 · 产品意图 |
| arch | `docs/ssot/architecture.md`（本文件） | 人写 · 架构决策 |
| reality | `docs/ssot/reality/` | **机器生成 · 禁手写** · Reality > Arch > Product |

> 注：`reality/` 目前尚未生成，是已知缺口。

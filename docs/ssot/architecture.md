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

## 二、契约（11 域，以实现为准）

`identity` · `organization` · `work` · `resource` · `execution` · `governance` ·
`learning` · `conversation` · `scheduling` · `events` · `errors`

> 与 v0.2 的差异：`project` 并入 `work`（同一概念不留两个名字）；
> 新增 `resource` / `learning` / `conversation` / `scheduling`；
> 不再使用"8 根 + 5 内核"的分法。

## 三、依赖铁律（17 条，全部机器强制）

**层级边界（R1–R12、R17）** —— `tests/architecture/test_layer_dependencies.py`

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

**旧代码围栏（R13–R16）** —— `tests/architecture/test_legacy_fence.py`

| # | 规则 |
|---|------|
| R13 | 新地基不许 import 旧代码（迁移期走 `migration_allowlist.json`，**只减不增**） |
| R14 | 旧代码文件只减不增（文件集 ⊆ 基线，总行数 ≤ 基线） |
| R15 | 旧代码跨分区依赖边只减不增 |
| R16 | 不许新增顶层代码目录 |

## 四、目录树（现役）

```
src/ai_factory_os/
├── contracts/     identity organization work resource execution governance
│                  learning conversation scheduling events errors
├── core/          scheduler events
├── services/      organization work resource execution governance learning conversation
├── plugins/       factories/{software} agents skills tools mcp models connectors
│                  controllers/{browser,computer} healers notifiers triggers storages
├── infrastructure/ llm storage messaging process sandbox
├── api/
└── bootstrap/

apps/              cli（web / desktop / mobile 待迁）
tests/             architecture core plugins + <旧测试树，待绞杀>
docs/              ssot（product/arch/reality）· adr · architecture · cleanup
scripts/           legacy_inventory.py · legacy_reach.py
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

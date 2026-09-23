# AI Factory

> **AI Factory OS —— 企业级 AI OS（多 Agent 调度平台）。**
> AI Software Factory 是它的第一个 Factory。
>
> 本地部署 · 全事件审计 · Apache-2.0

`v1.3.29`（以 `pyproject.toml` 为准）· CLI 在役 · API 可起（`factory serve` 一条命令起界面+API）

---

## 装它（两种，按你的用途挑）

| 用途 | 怎么装 | 特点 |
|---|---|---|
| **改代码 / 开发** | 仓库里 `python -m venv .venv && .venv/bin/pip install -e .` | editable：代码跟着仓库走，改了立刻生效 ✓ |
| **只想用（不碰仓库）** | 建个独立 venv，装 wheel：<br>`python -m venv ~/.factory-cli && ~/.factory-cli/bin/pip install <wheel>` | **解耦**：读自己的 site-packages，仓库删了也能跑 ✓（实测 ✓） |

- 造 wheel：`python -m pip wheel . -w /tmp/out --no-deps`（或 `pip install .` 直装）
- 发版前**必跑**干净环境真装真跑：`bash scripts/check_wheel.sh`（构建 → 干净 venv → 装 → 跑真命令 → 探 `/` 与 `/api/trees` 必须 200）
- **数据根**：默认 `~/.factory`（可用 `factory --root=<目录>` 换，测试务必用它 ✓ —— 环境变量 `FACTORY_ROOT` **不被认** ✗）
- 想切到独立安装：让它排在 `~/factory-venv/bin` **之前**（`export PATH=…`）—— 谁的路径靠前就用谁 ✓

---

## 它现在真能做什么

以下每条都有**真跑证据**（提交号 / 制品 id 可在仓库 `docs/` 里核对）：

| 能力 | 命令 | 真跑证据（2026-09-21） |
|---|---|---|
| 一句话需求 → 可执行任务树 | `factory chain "<需求>" --project <P>` | 一条命令跑通 定位→理解→PRD→产品/UX/架构→拆解→细拆；新场景 18 域 **85 叶**（`PLAN-646511ccf9`） |
| 真执行（外部 Agent 真写码） | `factory run --plan <树> --project <P> --limit N` | `EXR-002/003/005` 成功：真改仓库并提交（如 `f5f7570` 微信登录 + 94 测试） |
| 执行体可表态（停手≠完成） | 同上 | 执行体输出 `EXEC-VERDICT`；未提交的产出会被标 **待核**，不会记成"干净完成" |
| 监控与看板（同源） | `factory metrics / status / kanban / task list` | 同一份任务树三处对账一致（叶数/完成数/状态一致） |
| 项目理解 | `factory understand <仓库路径> [--stage]` | 阶段识别 `OPERATION`（置信度 0.90）+ 4 条 artifact 证据；完整报告含语言/栈/规模/缺失项 |
| 项目级记忆（跨会话） | 自动；`factory memory list --project <P>` | 执行完成后自动落一条（`exec:EXR-003`）；注入块 `【项目历史记忆】` 已验证 |
| 文档知识索引（记忆第 3 层） | `factory knowledge status / reindex` | 能判"★ 过期（N 个文档更新）"并增量重建 |
| 门禁 | `bash scripts/verify.sh` | 16/16 ✓ · `pytest` 27 ✓ · 全仓 ruff 0 错（已是阻塞门禁） |

## 还没闭环（如实列出，避免误导）

- **插件（放下即用）**：把插件清单丢进 `~/.factory/ops/plugins/manifests/*.json` 即被自动注册
  （`factory plugin list` 就能看到、`enable` 后其能力可被 `resolve` 到）；坏清单会响亮报错。
  可声明式放下的类型见内核 `PLUGIN_TYPES`（provider / executor / agent / skill / tool / mcp / model…）；
  代码级扩展点（connectors / controllers / healers 等 12 类插槽）仍需实现代码，不是清单能变的。
- **流程可编排（已接，可选挂载）**：流程引擎与 4 个内置流程（`feature-delivery` / `desktop-feature` /
  `bug-fix` / `release`）已接进主链 —— `factory tasktree workflow <plan> --id feature-delivery` 挂上后，
  叶按流程**步骤顺序**推进（走完全部步骤才算完成，每步完成会交回待下一步）；不挂 = 现状（一叶一次派活）。
  多公司 / 多部门维度的流程分派尚未做。
- **多公司 / 多部门（已落到执行）**：成员有归属（`factory org member set --all --company <C>`），
  项目可归属公司/部门（`factory project org <P> --company <C> [--department <D>]`）——
  派活只在**项目所属公司/部门**的成员里选（跨公司不串人），归属同时写进执行请求与派活简报。
  尚未做：一家成员同时服务多家公司（多对多）、部门级预算/审批。
- **学习自治（已接，agent 域）**：每次终态执行自动落一条经验（谁 / 任务类型 / 能力 / 成败 / 耗时 /
  证据 —— **失败也记**，防"只记成功"的自我偏差），`factory intelligence experience list` 可查、
  `... experience evaluate --task <类型>` 给出基于历史经验的 agent 推荐（置信度随数据增长）。
  尚未做：provider 域的推荐（`intelligence recommend` 的 Experience 权重仍无数据）。
- **前端**：`apps/web` 为空（API 可起，无界面）；`apps/desktop`、`apps/mobile` 为壳。
- **云端 / 多租户**：无 —— 本地单机运行。

## 快速开始

```bash
git clone https://github.com/shenlongze/ai-software-factory.git
cd ai-software-factory

bash scripts/install.sh           # 构建 wheel → venv → 安装 → 验证（幂等；另有 scripts/setup.sh 走源码态）

factory provider add              # 配 LLM：key 写入 ~/.factory/.env（权限 600）；配置里只存 env: 引用，不落明文
factory doctor                    # 环境自检

factory create project --name demo --repo-path ~/demo
factory chain "我想做一个记账 App" --project <P-id>      # 一条命令跑到"拆解 + 细拆"
factory tasktree confirm <PLAN-id>                       # 人工确认门（确认后才进执行）
factory run --plan <PLAN-id> --project <P-id> --limit 1  # 真派工执行
factory metrics                                          # 监控
```

API（可选，无前端）：`.venv/bin/python -m apps.api.main --root ~/.factory --port 8787`

## 架构摘要（现行）

```
apps/           cli（在役）· api（可起）· web / desktop / mobile（空壳）
src/ai_factory_os/
  contracts/        跨层类型与协议（无逻辑无 IO）
  core/             平台机制（调度 / 事件）
  services/         域用例（11 个域：conversation · execution · work · organization · learning …）
  plugins/          12 类插槽（agents · connectors · controllers · models · tools · triggers …）
  infrastructure/   技术底座（LLM / 事件 / 配置 / 存储）
  bootstrap/        装配与启动（wire_scheduler · scheduler_pump）
  api/              HTTP 适配
```

## 文档导航

```
docs/ssot/README.md                        ← 单一事实源（SSoT）导航
docs/实跑-全链路-20260920.md               ← 全链路实跑记录（9 个卡点 + 修复证据）
docs/全链路实测-从会话开始-20260921.md      ← 从"一句话需求"跑到"叶在执行"的逐环实测
docs/全量测试报告-20260920-2.md            ← 全量测试（含项目理解 / 项目级记忆）
CHANGELOG.md                               ← 版本变更
```

> 本仓库另有 ~1300 份历史文档（`docs/sprint*/design/adr/audit`）：它们是**历史证据**，不代表当前系统。
> 版本与能力一律以 `pyproject.toml` + 代码 + 运行时为准。

## 商业定位

开源核心 + 商业增值（洋葱式开源：外层可装可跑、核心编排闭源）。

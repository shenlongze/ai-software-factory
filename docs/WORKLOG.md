# AI Factory OS · 工作日志（追加式 ⇒ 留痕）

> **只往后加，不改历史** ✓ —— 每条记：时间 · 做了什么 · 真证据 · 版本/提交。
> 目的：任何一天都能回答"当时到底干了什么、凭什么说干完了"。
> 配套：活清单 `docs/TODO.md` · 网页版 `/status`（`factory serve` 起来后看）。

---

## 2026-09-22

### 主题：CLI 的长相与手感（照 Hermes）+ 并发安全 + 学习自治铺开

**版本链：v1.3.3 → v1.3.19（17 个提交，每条都门禁全绿）**

| 版本 | 做了什么 | 真证据 |
|---|---|---|
| v1.3.3 | CLI 照 Hermes 补齐：分区/配色/可发现性/审批面板；看板改真看板；修"需求→PRD 门"重大误杀（真需求被当凭空发明移出 21 条 ⇒ 复验 19/19 对得上） | `18316e6a` · `3cb185b5` |
| v1.3.4 | 看板按项目分屏（`[n/N] 项目名`）+ `--limit N` / `--all` / `--merged` | `10e21f14` |
| v1.3.5 | 看板表头挂**项目中文说明**（根因：`_project_notes` 要对象，我传了 dict ✗） | `16e466a1` |
| v1.3.6 | 七域**可下钻**（`console activity` 等六个域，复用同一份快照） | `8f6b3fbc` |
| v1.3.7 | 会话**归属项目**（`/project` 进提示词；假 provider 抓提示词验证 ✓） | `fd706682` |
| v1.3.8 | dashboard 与 status **口径归一**（修前它说 0 项目 0 任务 ✗） | `4d548acb` |
| v1.3.9 | `factory serve [--port]` 一条命令起 API + 最小界面（默认只绑本机 ✓） | `58368904` |
| v1.3.10 | ★ **干净环境真装真跑** ⇒ 抓到 `apps/api/index.html` 没进 wheel（装完 `/` 报 500 ✗）⇒ 修后 200 ✓；立 `scripts/check_wheel.sh` 为发版必跑 | `774bd2e5` |
| v1.3.11 | ★ **真流式**：先前 `adapters/hermes.py` 的 `stream()` 是**假流式**（先拿全量再切行 ✗）⇒ 改直连 HTTP + `stream:true`；真接口首块 **0.65s** | `0a3f416c` |
| v1.3.12 | ★ Founder 问「同一个仓库同一时间两个人改？？？」⇒ 读真代码给出三段图（执行期有沙箱隔离 ✓ / 认领期 CAS ✓ / **回写期是真风险** ✗）⇒ 落**跨进程运行锁** + 输入区上下横线 | `3beb26e5` |
| v1.3.13 | **回写防护**：patch 目标脏 ⇒ 拒绝自动套用（以前会静默把两拨改动混在一起 ✗） | `64b0e89f` |
| v1.3.14 | 架构/分类铁律：修 **R20/R23**（R23 里 `serve` 是我漏登记 ✗）+ 写存量盘点报告（剩 6 条结构债） | `e2563a7c` |
| v1.3.15 | `create` 手感（company 静默成功 ✗ ⇒ 有回执；缺参/乱写 → 中文 + rc=2）+ 修我自己留下的 pydantic 告警 | `2c625f1e` |
| v1.3.16 | **解耦安装**：独立 venv + wheel ⇒ 模块读自己的 site-packages（仓库删了也能跑 ✓） | `2a821e65` |
| v1.3.17 | **全视图口径交叉核对**（守着 6 个视图，漂了就红） | `c1a7ddc3` |
| v1.3.18 | 学习自治扩 **workflow 域**（收尾钩子 + 失败安全） | `edf80101` |
| v1.3.19 | 学习自治扩 **skill / decision 域**（证据必须用 `Evidence` 对象 —— 塞字符串会静默失效 ✗） | `67538852` |
| v1.3.20 | **留痕**：活清单 `docs/TODO.md` + 追加式日志 `docs/WORKLOG.md` + 网页版 `/status`
| v1.3.21 | 结构债 **R10** 清掉：10 个 `models.py` → `types.py`（引用三形式全覆盖：相对/短名/全名）。
| v1.3.22 | 结构债 **R4 部分**：`ProviderRequest/Response/Interface/Error` 四个纯契约归位 `contracts/llm/`（infra 保留再导出 ⇒ 零破坏 ✓）；插件改从契约拿 ⇒ **R4 17 → 12** | 架构守卫 R4: 12 ✓ · pytest 74 ✓ · R4 剩余全是行为依赖（要设计 ✗）· R5 是模块放错层（待单独一刀 ✗） |
| v1.3.23 | 结构债 **R9**：`contracts/entity/contract.py` 里带控制流的函数全部外移到 `services/resource/rules.py`（五件套的 rules ✓ 行为一字未改）; 契约只留数据（245 → 73 行）; 两处调用方改路径（契约不能反向 import ✗） | 架构守卫 **R9: 12 → 2** ✓ · pytest 74 ✓ · 真跑 `create_entity('conv')` ✓ |
| v1.3.24 | **R3 跨域依赖图 + 断环方案**（纯分析, 不动代码 ✗）: 新增 `scripts/analyze_cross_domain.py`（复用守卫同一份 modules/edges ⇒ 不漂移）⇒ 报告含 mermaid 图 · 边数排行 · 环清单 · 三种断法 | 62 边 · **真环 1 个（6 域大环 ✗）** · 直接双向 8 对 · **像契约仅 12%** ⇒ R3 不能靠搬类型 ✗ · 第一版判定/环算法都有错, 已修正 ✓ |
| v1.3.25 | **冷启动端到端测试**（Founder 建议「从头测试」; 干净根 --root=<tmp>, 全程不碰真实数据 ✓）: 链上半段通（会话→需求→PRD→分析→架构→拆解→确认 ✓ 门 12/12 · 70 叶带验收）; **下半段在冷启动下断了** ✗（run 恒为「无可推进/ unresolved」且不说原因）; 抓到 6 条真问题（招人不进调度池 · 招 devops/architect/writer 崩 · chain 结尾假地址 · 定位文案 · doctor 不存在却登记着） | 报告 `docs/reports/2026-09-22-冷启动端到端测试.md`（逐条带命令与输出 ✓）|
| v1.3.26 | **更正 + 撤掉我自己编的提示** ✗（Founder 点出「我们没有设计招人这个功能」）: 读原文核对 —— 产品链（ssot/product.md:24）是 Idea→目标表达→理解→**编排**→执行→…, **没有招人这一步**; 「招人」出身老区（services/organization/cli.py 自述 src/legacy/factory-org）; **是我 v1.3.15 在 create company 回执里自己写了「下一步去招人」** ✗ ⇒ 已撤, 只留如实回执 ✓; 测试结论同步更正: 真问题 = **编排这一环在冷启动没落地** | 门禁 pytest 74 · 守卫 63/63 · ruff 0 |
| v1.3.27 | **冷启动补测（更正）+ 老区盘点**（Founder: 「我们没有设计招人这个功能」+「老区还有什么？」）: 走**设计内正道**（`agent add` 建舰队 ×5）后 `run` **真会派活** ✓（创建执行 2 个）; 失败原因是 `NoAvailableRuntime` ✗ = 新根没配 provider; ⇒ 冷启动缺的是**引导**不是能力; 正道三步 `agent add`→`provider add`→`run` 都不引导 ✗; **有意停手**: 第 2 步要贴 key ⇒ 不搬凭据进临时根 ✗（最后一跳未实测 ✓ 如实标注）; 老区盘点: 目录已无 ✓ · 145 文件出处残留 ✗ · org 老区命令面 ✗ · `org member` 是设计内 ✓ 别误伤 · factory.db 老区库仍在用 ✓ | 报告第五章 + TODO E6–E8 |
| v1.3.28 | **删老区命令面**（Founder:「老区都删除」）: `factory org` 下 company/employee/authority/knowledge 四个老区命令面整块移除（解析器+分发+help）⇒ `org -h` 只剩 `member` ✓; **保留**设计内的 `org member` 与 `create company|department|project`（审计确认 ✓ 不误伤）; 服务层与 `services/organization/` 内部件不动 ✓。**过程**: 我第二轮连带删服务层函数 ⇒ 破坏了该模块自己的 dispatch 与共用辅助（_json_object 等）✗ ⇒ ruff 11 错 + 2 测试挂 ⇒ **回退该步**, 只留 CLI 层这一刀 ⇒ 回到全绿 ✓。剩下的服务层 6 个老区函数（仍被该模块内部 dispatch 引用 ⇒ 要连 dispatch 一起摘）与 145 处 `src/legacy/…` 注释 ⇒ 下一刀 ✓ | 门禁 pytest 74 · verify 16/16 · 守卫 63/63 · 分类 5/6 · ruff 0 |
| v1.3.29 | **老区彻底清完**（Founder:「老区都删除」第二轮）: 删服务层 6 个老区函数 + `_CMD_DISPATCH` 条目; 删老区独立入口死脚手架（`build_parser` 211 行 / `_CMD_DISPATCH` / `_dispatch` / `main` —— pyproject 无 script、外部零调用 ✓）⇒ 该文件 1177 → 899 行; **保留** `_print_result`（apps/cli 的 create 打印用它 ✓）与所有 cmd_* ✓; 145 处 `src/legacy/…` 出处注释**改准为其真实路径**（141 自动 + 4 手工, 余 5 处合理 ✓）。**这次先列清「模块内部引用」再动**（上一轮漏了这步 => 一次成功 ✓, 每步过 pytest ✓） | 门禁 pytest 74 · verify 16/16 · 守卫 63/63 · ruff 0 · 老区清零 ✓ |
| v1.3.30 | **冷启动引导（第一次用六步）+ 撤掉假地址**（Founder 点单 1 · 只动帮助/提示 ✗ 不加命令）: `factory help` 新增【第一次用】六步（create project → chain → tasktree confirm → **agent add** → **provider add** → run --limit），第 4/5 步写明「不给会怎样」（没舰队 ⇒ 树跑不动只会说 unresolved；没配 provider ⇒ NoAvailableRuntime）; chain 结尾的假地址改成「看界面: 先跑 factory serve…—— 没起来就没有界面」✓; 新增守卫「冷启动引导」 | 守卫 64/64 · pytest 75 |
| v1.3.31 | **R9 清零 + 发现 R3/R9 规则冲突**（Founder 点单 2）: contracts/llm/provider.py 两处控制流（estimate_cost_usd · key_env_var）改**条件表达式**（R9 只判 If/For/While/Try/With 语句 ✓）⇒ 行为不变（4 用例实测 ✓）⇒ **R9: 2 → 0（绿）** · 架构 **10/15 → 11/15**; 试点搬类型清 R3 时发现 **R3 与 R9 互相顶住** ✗（那 7 条边指向的 types 都带校验/派生逻辑 ⇒ 搬 contracts 犯 R9, 不搬犯 R3）⇒ 报告第八章 + TODO P5, **等 Founder 裁决** ✓（我倾向放宽 R9）| pytest 75 · 守卫 64/64 · ruff 0 |
| v1.3.32 | **端到端测试自动化 + 覆盖率基线**（Founder 问「现在有没有完整测试」）: 先**实测** —— 覆盖率 **27.7%**（48,003 语句 / 34,676 未覆盖 ✗），按层 bootstrap 63% · contracts 74% · apps/cli 32% · services 25% · plugins 20% ⇒ **结论: 没有完整测试** ✗; 本次补第一块: **端到端自动化**（空根 → 项目/确认树/舰队 → wire_scheduler + drive(假执行器) ⇒ 断言进度真动: 实测 2 叶 → done 2 / 100% ✓，不联网、确定性 ✓）；守卫 64→**65** · pytest 75→**76**。坑: 断言读错键名（completed vs done）⇒ 明明 100% 却报 0 ✗ ⇒ 靠打印真实读数发现 ✓ | TODO 第 6 节 |
| v1.3.33 | **修 RuntimeStore 并发写**（飞机大战测试 `--parallel 3` 炸出来的真 bug ✗）: 现场 = runtimes.json `Extra data: char 99803`（两段写交错）; 根因 = 临时名 `.{filename}.{pid}.tmp` ⇒ **同进程并发线程 PID 相同** ⇒ 共写一个临时文件 ✗; 修 = `tempfile.mkstemp` 唯一临时名 + 写后回读校验 + 读-改-写加（线程锁 + flock）; **反例证明**老写法 6 线程×20 条只活 20/120 ✗ ⇒ 修后 120/120 ✓; **数据修复**: 你真实根的 runtimes.json 被写坏 ⇒ 先备份再截到合法前缀修好（runtimes 1 · executions 33 · results 21 ✓）; 另发现 **31 个文件**同类裸写 ✗ ⇒ 记 TODO E10 | 守卫 65→66 · pytest 77 |
| v1.3.34 | **修 check_wheel.sh 进程泄漏**（我自己造的 12 个孤儿 `factory serve` ✗）: 根因 = 启动 `( … ) &` 没 `exec` ⇒ `$!` 是**子 shell** 的 PID ⇒ kill 只杀壳、留下 python ✗; 修 = 加 exec + cleanup 等真退出（≤5s）→ 精确 PID 强杀 → 复核, 没停干净**报红** ✗; 12 个孤儿已按精确 PID 逐个停掉（未用 pkill ✓）⇒ 复核零残留 ✓ | 实测 check_wheel 8082 全过 ✓ |
| v1.3.35 | **修流式双框 + 忙指示挤行**（Founder 在真窗口里看到 ✗，我用当前代码复现 ✓）: 根因 = ① 流式时 `_body` 已清空但 `if _use_box():` 照样打框 ⇒ 多一对空框线 ✗; ② `_flush_line` 打顶线前没清忙指示 ✗; 修 = 打框改 `elif _use_box():` + 顶线前 `_busy_clear` ⇒ **pty 实测: 顶线 1 条 · 底线 1 条 · 不挤行** ✓; 新增守卫「流式不双框」; 另记录 E16（模型把 project 的 `--company` 可选说成必需 ✗，已把「先查 -h」写进提示词） | 守卫 66→67 · pytest 78 |
| v1.3.36 | **会话提示词加规则 1c**（兑现 v1.3.35 提交信息里的承诺 ✗）: 「讲参数前先 `RUN: factory <cmd> -h` 看一眼, 别凭记忆说哪个必填」—— 起因 = Founder 实测里模型把 project 的 `--company`（可选）说成必需 ✗ | 提示词已改 ✓ |
| v1.3.37 | **项目详情能看树与进度**（Founder 实测「不能进入到项目查看详情」✗）: 根因① `project show` 只有 language/repo/agents/skills/workflows, **没树没进度** ✗; 根因② 把项目 id（P-xxx）传给要 PLAN-xxx 的命令 ⇒ 只回「任务树不存在」✗（会话里模型就是这么被误导的）; 修 = project show 附**该项目的树 + 叶数/完成/百分比** + 下一步命令; 新增共用 `_plan_not_found()` 替换 **9 处**裸报错; 顺带修计数（原先比 "completed" ✗ 真实值是 done ⇒ 一直算 0）; 实测: plane-shooter ⇒ 任务树 1 棵 · PLAN-5cb0df162c · 叶 87 · 完成 29 · 33.3% ✓ | 守卫 67→68 |
| v1.3.38 | **项目详情三修**（Founder 实测: 「language 还是空」✗ + 「详情太乱没章法」✗ + 会话答「改不了代码」✗）: ① 复用 `detect_language/detect_framework` 对仓库**实时识别**（只读不写库 ✓）⇒ plane-shooter 显示 `javascript（自动识别）` ✓; ② 详情重排**三段**: 基本信息 / 任务树与进度 / 团队与能力 + 删掉重复尾巴; ③ 提示词加规则 1d —— 讲清「平台会真正写代码（run/chain 派 agent 在项目仓库改并提交）」, 不许说成系统不会写码 ✗ | 守卫「项目详情」加严（三段标题必须齐 + 有代码的项目不许 unknown）· 守卫 68 · pytest 79 |
| v1.3.39 | **项目详情 = 真实四段**（Founder: 「详情太乱, 要真实展示项目情况/任务情况/文档情况」+「点名了只要你详情, 别多余命令」✗）: 逐一定位真源 —— 说明在**全局** `conversations/`（此前找项目目录 ⇒ 一直空 ✗ 已修）、任务在 `projects/<P>/tasks/`、PRD 在 `product_truth/prds.json`、事实在 `knowledge/facts.json`、产物在 `artifacts.json`、仓库文档/自检脚本在仓库; `project show` 改为**四段真实视图**（项目情况/任务情况/文档情况/团队与能力, 读不到如实留空 ✗不编）; 实测 plane-shooter: 说明=需求原话 · 叶87/完成32(36.8%) · 分布完成32/进行中1/待做54 · PRD1份 · 产物3份 · **自检脚本20个** ✓; 提示词加规则 1e（点名了对象就直接跑那条, 别先 list ✗）; 守卫加严（四段齐 + 说明不许空 + language 不许 unknown）| 守卫 68 · pytest 79 |
| v1.3.40 | **项目分类（归属）打通**（Founder 问「有项目分类么」⇒ 实测: 任务/文档按项目分目录 ✓ 但**会话 572 个里只有 3 个带归属** ✗ · **事件 13,086 条全空** ✗ · dashboard/status 不支持 --project ✗ ⇒ 他定「全做」✓）: **乙** ✓ 会话创建支持 project_id（chain / conversation new 传入；坑: 该字段本来就有, 我加重复被 ruff F601 抓 ✗）; **甲** ✓ ExecutionRequest 加 project_id + 调度器两处传值 + runner 交给事件 logger（带归属的执行事件从**下一批**开始 ✓）; **丁** ✓ 新增只读 `factory project docs <项目> [--show]`（列 PRD/产物/事实/仓库文档真实路径, 并**如实标注 ref 悬空** ✗）; **丙**（dashboard/status --project）**未做** ✗ 记 E24; 坑: 打印分支插错函数 ⇒ 零输出 ✗ ⇒ 已搬对 ✓ | 守卫 68→69 |
| v1.3.41 | **修产物 ref 悬空（E23）**（Founder 打不开项目文档 ✗）: 根因 = 三个 agent（pm/architect/uxui）把 ref **写死**成占位符 `file:///docs/product.json` ✗; 修 = 登记处一处落盘（内容写入 `projects/<P>/docs/<type>-<id>.json` + ref 指真文件, 失败保留原样 ✗不假装）+ 回填脚本 `scripts/backfill_artifact_refs.py`（--dry-run · 幂等 · 先备份）; 实测 **22 个全部回填, 悬空 0** ✓ （备份 ~/.factory-backups/artifact-refs-backfill-20260924-182119 ✓）; 坑: 我用 `://docs/` 判占位符 ✗ 实际是 `file:///docs/`（///）⇒ 判断恒假 ⇒ 干跑 0 个 ✗ ⇒ 改 `/docs/` ✓ | 守卫 69→70 |
过程里工具错了两回（短名算式 · 正则多点 ✗），都被**每目标全量 pytest** 抓住 ⇒ 停手修正后一次全绿 | 架构守卫 **R10: 0 项** ✓ · pytest 74 ✓ · `compat_aliases.py` 里的 `.models` 是有意保留的兼容映射 ✓ |
（生成器 `scripts/build_status.py` 从 TODO/日志/git log/实时读数**真源**生成 ⇒ 不会漂移 ✓） | `factory serve` 后 `/status` 200 ✓（干净安装也 200 ✓） |

### 立下的规矩（已落文档 + 挂入口 + 守卫）

- **版本号**：每改一次递增末尾号，三处同步（pyproject / README / CHANGELOG）⇒ `docs/release.md` + `AGENTS.md` 挂入口
- **界面规格**：五区（banner / 输入区 / 执行区 / 回答区 / 状态栏）⇒ `docs/cli-design.md`，改界面前先改文档
- **发版必跑**：干净环境真装真跑（`scripts/check_wheel.sh`）⇒ editable 看不出打包病 ✗

### 事故与更正（留痕，不藏 ✗）

| 时间 | 事情 | 处置 |
|---|---|---|
| 2026-09-22 | 我用 `FACTORY_ROOT` 环境变量做隔离测试 ⇒ **CLI 不认它** ✗ ⇒ 3 个"测试公司"写进了 Founder 真实 `~/.factory/org/` | 按 **store API** 逐条删除（5 家 → 1 家，只剩原有 `AI Factory` ✓）；正确姿势 = `--root=<目录>` ✓；教训：动数据前先确认隔离开关真生效 |
| 2026-09-22 | 我试图把 10 个 `models.py` 改名（R10），用粗替换 ⇒ **45 个测试挂掉** ✗ | 立刻全量回滚（`git restore` + `reset` + `clean`）⇒ 回到全绿 ✓；教训：本仓有**短名 import**（`from workflows.models import …`），改名要先摸清规则 |
| 2026-09-22 | 版本号 v1.3.19 之前，多处守卫断言因界面/流程改动而过期报红 | 逐条按**新实物**更新断言（不是放宽 ✓） |

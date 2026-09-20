# 代码落地位置规则（Code Placement）

> 状态：**生效** · 日期：2026-09-15 · 依据：`ssot/architecture.md` §一/§四 ·
> `adr/0037-root-layout-decision.md`（方案 C）· `adr/0038-api-layer-retirement.md`
> 性质：**规则**（判"一个文件该放哪"）。结构描述见 `architecture.md`；本文件是**判据**。

---

## 零、为什么要有这份文件

仓库曾同时存在**三套互相矛盾的目标布局**且从未正式裁决，直到 ADR-0037 定案（方案 C）。
定案之后仍发生过三次"位置错误"——**都不是手误，是"先动手建、再被纠"**：

| 实例 | 错法 | 后果 |
|---|---|---|
| 1 | 建 `api/domains/work/`（registry 里没这个域） | **游离目录** → 路由永不挂载 → HTTP 404，而服务层直调正常（最难查） |
| 2 | 建 `api/domains/learning/` 只放 `router.py`，没建 `__init__.py` | 守卫认不出它是"域目录" → 报"清单有但目录无" |
| 3 | CLI 住在 `src/ai_factory_os/api/cli/` | 消费者嵌进包内 → 违 SSoT §一 + R7；**而 R7 守卫查的是字面（"有没有叫 apps 的目录"），没拦下** |

**共同根因：建之前不查规矩，被纠之后才补。** 本文件就是那份"建之前要查的规矩"。

---

## 总则（两条硬规则 —— 违反即返工）

> **总则一：判位置必须走两步，缺一步不算判完。**
>
> ```
> 第 ① 步  定【层级】 —— 它在架构上属于哪层（用 §二 的 8 问）
> 第 ② 步  落【路径】 —— 按 §一 对照表落成**具体路径**（域名/能力名进路径）
> ```
>
> ⇒ 只说层级（"放 services/"）**不算说清位置**；只说路径（"放 src/…/understanding.py"）
>   而不说层级，无法验证层级是否合法。**两样都要说，且必须一致。**
>
> 反例（实际发生过）：新模块报"放 services 层"就被当完成 —— 结果域名没进路径、
> 目录没落对域，成了游离目录；或者落在 `api/` 下而实质是业务（`api/` 里 24 个模块
> `@router.` 装饰器全为 0）。

> **总则二：层级与路径一对一，但它们是两个维度。**
>
> - **层级** = "它是什么"（架构语义：契约 / 平台本体 / 业务 / 实现 / 技术 / 装配 / 入口）
> - **路径** = "它在哪"（物理位置：磁盘上的确定路径）
>
> ⇒ 说清前者**不等于**说清后者。任何"放哪"的结论都要**落到路径**才算数；
>   任何路径争议都要**回到层级**才有判据（否则只能靠"像不像"吵架）。

---

## 一、层级 ↔ 真实路径对照（**落地位置**）

> **区分两个维度**（这是最容易混的）:
> - **层级** = 架构上的第几层（contracts / core / services / plugins / infrastructure / bootstrap）
> - **落地位置** = 磁盘上的**具体路径**（`src/ai_factory_os/services/conversation/understanding.py`）
>
> 两者**一对一映射**，但"说层级"不等于"说清路径"。下表是**实测的当前目录**（2026-09-15）：

```
/Users/Shared/work/ai-software-factory/
├── apps/                        ← 消费者层（独立于 src/，递归不许进 src/）
│   ├── cli/          16 py      ← CLI 入口面（唯一入口候选）
│   └── desktop/       1 py
├── src/ai_factory_os/           ← 包内七层
│   ├── contracts/    15 py      ← 跨层契约
│   ├── core/         10 py      ← 平台本体（scheduler + events）
│   ├── services/    169 py      ← 业务域服务（9 域）
│   ├── plugins/      38 py      ← 实现绑定
│   ├── infrastructure/ 56 py    ← 技术底座
│   ├── bootstrap/     4 py      ← 装配与启动
│   └── _pending_migration/      ← 待绞杀堆场（★ 不是层）
├── scripts/                     ← 验证脚本 / 守卫
├── docs/  ssot(规则) · adr(裁决) · design
└── bin/                         ← 入口脚本
（tests/ 已清理，不再建）
```

### 层级 → 路径的落法（域名进路径，不是另起名字）

| 层级 | 路径模板 | **当前真实例子** |
|---|---|---|
| 契约 | `src/ai_factory_os/contracts/<域>.py` | `contracts/conversation.py` |
| 平台本体 | `src/ai_factory_os/core/<能力>/` | `core/scheduler/` `core/events/` |
| 业务服务 | `src/ai_factory_os/services/<域>/<文件>.py` | `services/conversation/understanding.py` |
| 实现绑定 | `src/ai_factory_os/plugins/<类>/` | `plugins/agents/` `plugins/factories/` |
| 技术底座 | `src/ai_factory_os/infrastructure/<能力>/` | `infrastructure/llm/` `infrastructure/retrieval/` |
| 装配 | `src/ai_factory_os/bootstrap/<文件>.py` | `bootstrap/wiring.py` |
| 消费者 | `apps/<消费者>/<...>` | `apps/cli/domains/conversation.py` |
| 验证 | `scripts/smoke_<能力>.py` · `scripts/check_<守卫>.py` | `scripts/smoke_conversation_understand.py` |

### 一个能力的完整分布（照着这个找位置）

以「**会话理解**」为例 —— 同一个能力**横跨五处**，每处放什么、放哪：

```
服务层   src/ai_factory_os/services/conversation/understanding.py      事实层实现（数据 + 规则）
服务层   src/ai_factory_os/services/conversation/interpreter.py        LLM 语义解释（调 LLM 产 proposal）
服务层   src/ai_factory_os/services/conversation/proposal.py           validate/apply（唯一写 Truth 的闸）
装配层   src/ai_factory_os/bootstrap/wiring.py                         注入跨域 hook（ensure_project_binding）
入口层   apps/cli/domains/conversation.py                              CLI 命令（参数 + 包络 + 输出）
验证层   scripts/smoke_conversation_understand.py                      端到端证据
```

⇒ **判位置的完整动作** = ① 用 §二 的 8 问定**层级** → ② 按本表落到**具体路径**（域名/能力名进路径）。

### 每层放什么 + 判据（怎么认一个文件属于该层）

| 层 | 放什么 | **判据（怎么认）** | 允许依赖 |
|---|---|---|---|
| `contracts/` | 跨层契约：dataclass / Enum / `Protocol` / 常量表 | **无业务逻辑、无 IO、无 import 本仓其他层** | 只 stdlib |
| `core/` | 平台本体：**只有 `scheduler` 与 `events` 两段** | 决定"下一步是谁"的平台机制（不是业务调度） | `contracts/` |
| `services/` | 业务域服务（用例编排 + 存储） | 有业务语义、会读写数据、可被 CLI/未来 API 共同调用 | `contracts/` `core/` `infrastructure/` |
| `plugins/` | 一切**实现绑定**：agents / skills / tools / mcp / models / connectors / controllers / healers / notifiers / triggers / storages / factories | "某能力的**具体实现**"，换一份实现即换此层文件 | `contracts/` `services/` |
| `infrastructure/` | 技术底座：llm / storage / messaging / process / sandbox / events / git / retrieval | **与业务无关的技术能力**（换掉它业务不变） | `contracts/` |
| `api/` | 对外接口层（路由 / DTO 装配） | ★ **已按 ADR-0038 退役**（手写 HTTP 层删除；将来**从 CLI 生成**） | — |
| `bootstrap/` | **装配与启动**：注入各域的 `bind_lookups()` hook、启动顺序 | 唯一**允许 import 全部**的层 | 全部 |

**`apps/`（独立于 `src/`）**：cli / web / desktop / mobile —— **消费者**，不进包内。
**`scripts/`**：验证脚本 / 守卫。**`docs/`**：文档。**`bin/`**：入口脚本。

---

## 二、判断流程（拿到一个文件，按顺序问）

```
1. 它是【跨层类型/协议】吗（无逻辑无 IO）？        → contracts/<域>/
2. 它是【平台机制】（调度/事件本体）吗？            → core/{scheduler,events}/
3. 它是【某能力的实现】吗（换实现即换文件）？       → plugins/<类>/
4. 它是【技术底座】吗（与业务无关）？               → infrastructure/<能力>/
5. 它有【业务语义】、会读写数据吗？                 → services/<域>/
6. 它是【装配/启动】吗（要 import 多个域）？        → bootstrap/
7. 它是【面向人的入口】（CLI/Web/Desktop）吗？      → apps/<消费者>/
8. 都不是 → **停下来问**，别建。若确需新位置 → **先落裁决**（ADR），再建。
```

### 硬约束（守卫会红）

| 规则 | 内容 |
|---|---|
| **R7** | `apps` 类（cli/web/desktop/mobile）**不许出现在 `src/` 内**（递归查，非只查直接子目录） |
| **R20** | SSoT 域清单 ↔ 实际目录**必须一致**；含 `.py` 却缺 `__init__.py` 的目录 = **半成品伪包**，报红 |
| **R21** | `services/<域>/` 与 `api/domains/<域>/` 同名同存（**API 层退役期间暂停**，恢复时自动生效） |
| **R22** | 一层一目录，禁平铺 |
| **R23** | CLI 的每个命令必须在 `apps/cli/registry.py` 有域归属 |
| **R24** | **禁死代码 / 禁硬代码**（Founder 2026-09-19 定，见下） |
| **R25** | **禁重复造轮子**（同上） |

| **R26** | **状态必须落盘** | 凡"靠状态决定下一步"的地方（重试/去重/续跑/去空转），状态**必须落盘**；只改内存/只返回字串 ⇒ 无依据 ⇒ 空转。实测 4 连坑：失败不落盘 · 失败不终止 · 遗留 PENDING 没人捡 · SKIPPED 不落盘。 |
| **R27** | **同一数据的读写路径必须一致** | "按 id 定位文件"的函数，**所有调用方都要传齐定位参数**（如 project_id）；只修"写"或只修"读" = 补丁不彻底。实测：回写写 A 处、驱动读 B 处 ⇒ 空转 50 轮；修了 cmd_run_plan 却漏了 claim/release ⇒ 又空转一轮。**判据**：问"位置由什么决定、调用方都传了吗"。 |
| **R28** | **删"没用的 X"前先查 X 的真实用途** | 实测：我曾判 `task_trees/`（全局回落）是历史包袱、建议删掉；Founder 反问"有没有可能任务没有项目 id？"⇒ 实测 6 棵树**4 棵 project_id 为空** ⇒ 该回落是**合法场景**。⇒ 与 R24"判死码须三维"同源：**判"没用"必须先查真实用途**。 |

#### R24 — 禁死代码 / 禁硬代码

**判据一：死代码**
- 新代码必须**用户可达**: ① 有入口（CLI/API）② 有消费者（import 或动态加载命中）③ **实测走过一次**。
- 三者缺一 ⇒ 视为死码。**"代码能跑"不算完成** —— 直接 `import` 调用测试过 ≠ 能用
  （本仓已踩: 吸收清单 10 项里有 6 项"有代码没入口"，用户完全碰不到）。
- 查法（三维，缺一就会误判）: ① 静态 `import` ② 动态加载（registry/`importlib`/字符串）
  ③ CLI 入口（`apps/cli/`）。**只用 grep 模块名会误判** —— `messages`/`serve` 这类通用词、
  以及同名异物（本仓实测: `KnowledgeStore` 两个实现 · `U.messages` 与 `work/messages.py`）。

**判据二：硬代码**
- ✗ 绝对路径作默认值（如 `/Users/...`）⇒ 必须走 `root`/配置/环境变量。
- ✗ 密钥 / token / 密码入代码 ⇒ 只存 `env:` 引用（见 `providers.json` 的 `api_key_ref`）。
  ★ 补（2026-09-21，填上"**key 本体存哪**"的缺口 —— 实测「配了 key 却不生效」暴露的）:
    key **本体**由 `factory provider add` 持久化到 **`~/.factory/.env`**（权限 600，factory 自己的数据根）；
    配置只存 `env:VAR` 引用。**写 key 与读 key 必须是同一处** —— 该行原先没写"存哪"，
    结果 `provider add` 把 key 写进了 `~/.hermes/.env`（外系统地盘）而解析链读的是**源码目录内**的
    `.env`（死路）⇒ 写读不同源 ⇒ 需求理解静默降级（只报"我暂时无法可靠理解…"，把人引向"换个说法"）。
- ✗ 裸魔法数字（阈值/上限/超时）⇒ 必须命名常量（如 `DEFAULT_STALE_SECONDS`、`MAX_BODY`）。
- ✗ ★ **写死的"枚举表"当判据**（关键词表 / 前缀表 / 白名单）⇒ 枚举必然不全, 且失败模式常是
  **静默丢数据**。本仓已踩两次: `_PRODUCT_HINT_RE`（漏掉真实需求 ⇒ 会话"说着说着就忘了"）·
  `dimension_of` 硬编码前缀（漏 `默认语言:` ⇒ 同槽没顶替）。
  ⇒ 规则: 能用**通用规则**表达的（如"任何 `前缀: 值` 都归一"）绝不写成枚举; 必须枚举时,
  要在**双向测试**里证明（该拦的拦住 + 不该拦的放行）。

#### R25 — 禁重复造轮子

- **新增任何 store / index / 记忆机制 / 检索层之前**, 先全库查同能力是否已存在;
  已存在 ⇒ **改它或复用它**, 不准新建。
- 判据: 同一个能力只允许**一套实现**（R18 管"一能力一域"; R25 管"一能力一处实现", 跨层也适用）。
- 本仓现状（反例）: Store/Index/Memory 类 **24 个** · 数据落地 **8 处** ·
  `KnowledgeStore` **两个实现** · "记忆/知识/事实"机制 **5 套互不通** ⇒ 收敛目标 store ≤ 3。
- 配套纪律: 新增存储前先问「**能不能用【事件 + 投影】表达?**」能 ⇒ 不许新增 store
  （详见 `docs/design/storage-and-memory-design.md` §0）。

---

## 三、域清单（域内的东西按域放；域名跨层**必须一致**）

```
契约域（contracts/，12）   identity organization work resource execution governance
                          learning conversation scheduling events errors llm
服务域（services/，11）    conversation delivery execution governance learning metrics
                          operations organization resource validation work
```

**"一域"的判据**：一个**能力**只在一个服务域里实现（R18）。同一能力词根出现在两个服务域 = 违规。

### 三份清单 + 七层：**各管一件事，不要混用**（2026-09-15 定）

```
七层（architecture.md §一）  contracts / core / services / plugins / infrastructure / bootstrap / apps
   ⇒ 管【层级】—— 一个文件该落在哪一层（判据见 §一、§二）

契约域（contracts/，12）     identity organization work resource execution governance
                            learning conversation scheduling events errors llm
   ⇒ 管【contracts/ 下的子目录】

服务域（services/，11）      conversation delivery execution governance learning metrics
                            operations organization resource validation work
   ⇒ 管【services/ 下的子目录】+ 判"同一能力只在一处"（R18）

命令域（15）                 conversation understanding architecture decomposition orchestration
                            execution validation delivery learning operations metrics audit
                            governance organization platform
   ⇒ 只管【apps/cli/domains/ 的文件划分】+ 将来 API 从 CLI 重建的依据
   ⇒ ★ **不是实现域** —— 绝不拿它判"一个模块该放哪"
```

**⇒ 判定一个模块的位置，按这个顺序问：**

```
① 层级（七层判据）：无 IO 无业务 → contracts/ ; 有业务 + 读写 → services/ ;
                    技术机制（换掉它业务不变）→ infrastructure/ ; 能力实现 → plugins/ ;
                    面向人的入口 → apps/
② 域：  有业务语义 → 查**服务域（10）**；纯技术能力 → 直接进 infrastructure/<能力>/（不占服务域名额）
③ 路径：<层级>/<域>/<能力名>.py
```

**两份清单不是一一对应（命令域 15 · 服务域 10）—— 差异有两个方向：**

```
★ 命令域独有（7 个，没有对应的服务域 ⇒ 只是命令分组）:
   understanding · architecture · decomposition · orchestration · delivery · audit · platform
★ 服务域独有（2 个，没有对应的命令域）:
   resource · work   （实现存在, 但 CLI 未按这两个名字分组）

⇒ 命令域独有的那些，其实现各自按七层落到别处，例如：
   platform 的 config/llm/context → infrastructure/（技术底座）
   platform 的 tools             → plugins/tools/（实现绑定）
   platform 的命令注册           → apps/cli/domains/platform.py
   decomposition 的拆解实现       → services/work/
   delivery 的发布实现            → services/operations/ 或 services/validation/
⇒ ★ 实例: 2026-09-15 "platform 域迁移" 15 个模块, 实际落点是
   infrastructure/（config·llm·context·ids 10 个）+ plugins/tools/（4 个）+ services/organization/（1 个）
   —— 批次按命令域命名, **落位按七层**。
```

### 已知的两层映射例外（不是笔误，是为兼容而记）

```
API 面（曾） api/domains/decomposition/     ← 端点归属裁决（tasks/task-trees/schedules 归这）
服务实现      services/work/                ← 服务域清单（work 是服务域名）
```
⇒ 跨层**同名同存是默认**；出现不同名时，**必须在此登记**，否则算漂移。

---

## 四、反例：名字骗人的四类陷阱（删/迁前必查）

| 陷阱 | 现象 | 教训 |
|---|---|---|
| **`api/` 里装业务函数** | `factory_console/api/` 24 个模块，`@router.` 装饰器**全为 0** —— 它们是 143 个业务函数（`create_project` 等），只是名字在 `api/` 下 | 删目录前先判「**路由**还是**业务**」——**按实质，不按名字** |
| **`api/dashboard/` 是 CLI 的** | 自述"CLI 可视化控制台, Rich 非 Web" —— 不是 API | 同上；已归位 `apps/cli/dashboard/` |
| **`cli_factory.py` 是入口本体** | 10,155 行，`factory` 命令就是它 —— 不是"老代码残留"，是**在跑的地基** | "老的" ≠ "能删的" |
| **`_pending_migration/` 是堆场** | 名字像"废弃"，实为**待绞杀堆场**（298 py 在跑） | 判"能否删"看**是否在执行**，不看名字 |

---

## 五、建之前 / 删之前 的检查清单

**建之前**
0. **先按总则走两步并写下来**：① 它属于哪**层**（8 问）→ ② 它的**具体路径**是什么。
   两样都写不出 = 位置没判完，不许动手。
1. 这个位置**在 SSoT §一/§四 里存在吗**？（不存在 → 先裁决）
2. 域名**在域清单里吗**？（`contracts` 12 / `services` 9）
3. 建的是**域目录**吗？→ **四件套**：`__init__.py` + 实现 + 类型/模型 + `README.md`
   （`__init__.py` 缺了 = 守卫当它不存在，**两个方向都骗得过去**）
4. 它在 `apps/` 还是 `src/`？（消费者进 `apps/`，**递归**查不许进 `src/`）
5. 建完**立刻跑守卫**（`bash scripts/verify.sh`），别看代码

**删之前**
1. 它的**官方定性**是什么（docstring / 台账里写的）？
2. **实测引用**（静态 import + 动态导入 + 字符串**三样都扫**）—— 单条 grep 会骗人
3. 它是**路由**还是**业务**？（看有没有 `@router.` / 是不是被当能力调用）
4. 它是**在跑**还是**闲置**？（`coverage` 比"看起来没人用"可靠）
5. 删完**跑全量导入 + 冒烟**（编译期看不见的断裂只能这样兜）

---

## 六、装配：为什么"位置对"还不够

位置对了但**没人装配**，能力照样不通 —— 实测过：

```
各域用 bind_lookups() 声明"我需要什么跨域能力"， 但 bootstrap/ 是空壳、CLI 也不经它
⇒ hook 永远为空 ⇒ 会话派生的 PRD 没进项目
⇒ 现象: factory trace（按会话）样样都有, factory progress（按项目）全是 0
```

⇒ **装配点就是 `bootstrap/`**（SSoT §一：「唯一可 import 全部」）。
新增跨域 hook 时：**在 `bootstrap/wiring.py` 加装配**，不在域内部互相 import。

---

## 七、一句话总结

```
contracts 放形状 · core 放平台机制 · services 放业务
plugins 放实现 · infrastructure 放技术 · bootstrap 放装配 · apps 放入口

判断顺序：形状 → 机制 → 实现 → 技术 → 业务 → 装配 → 入口
七个都不是 ⇒ 别建，先裁决。
```

**规矩的价值不在"写下来"，在"建之前查过它"。** 上述三次位置错误，每一次都是因为跳过了这一步。

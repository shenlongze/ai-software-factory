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

## 一、七层：每层放什么（唯一权威）

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

### 三条硬约束（守卫会红）

| 规则 | 内容 |
|---|---|
| **R7** | `apps` 类（cli/web/desktop/mobile）**不许出现在 `src/` 内**（递归查，非只查直接子目录） |
| **R20** | SSoT 域清单 ↔ 实际目录**必须一致**；含 `.py` 却缺 `__init__.py` 的目录 = **半成品伪包**，报红 |
| **R21** | `services/<域>/` 与 `api/domains/<域>/` 同名同存（**API 层退役期间暂停**，恢复时自动生效） |
| **R22** | 一层一目录，禁平铺 |
| **R23** | CLI 的每个命令必须在 `apps/cli/registry.py` 有域归属 |

---

## 三、域清单（域内的东西按域放；域名跨层**必须一致**）

```
契约域（contracts/，12）   identity organization work resource execution governance
                          learning conversation scheduling events errors llm
服务域（services/，9）     conversation execution governance learning metrics
                          organization resource validation work
```

**"一域"的判据**：一个**能力**只在一个服务域里实现（R18）。同一能力词根出现在两个服务域 = 违规。

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

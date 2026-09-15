# ADR-0038：API 层退役 —— 手写 HTTP 层删除，API 从 CLI 重建

> 状态：**已接受（Accepted）** · 日期：2026-09-15 · 裁决人：项目所有者（创始人）
> 补充：本 ADR 是 ADR-0037（根布局定案）之后的**单层裁决** —— ADR-0037 的七层里含 `api/`，
> 本 ADR 裁决该层**退役**。两份合读才是完整现状。

---

## 一、背景

仓库里当时并存**两套手写 HTTP 层**：

| | 位置 | 规模 | 消费者 |
|---|---|---|---|
| 新 API | `src/ai_factory_os/api/`（app / domains×15 / registry / deps / envelope / errors） | 56 py · 3,169 行 · 15 端点 | 无（只有自建的冒烟脚本） |
| 老 API | `_pending_migration/factory_console/web/backend/fastapi_adapter.py` | 7,339 行 · **377 端点** | Web 控制台（`factory start` 唤起） |

两者都调 `services/`，但**都是手写的**：每加一个能力，就要在 HTTP 层再写一遍路由、DTO、错误映射。
CLI（`factory` 命令）与它们是**平行的第二条入口** —— 同一个动作存在两份对外表达。

## 二、决策

**创始人原话**：

> 「**api 可以根据 cli 创建接口服务，现在可以将 api 都删除，但是 cli 是地基**」

落为三条：

1. **CLI = 地基（唯一实现）** —— 动作的权威定义在 CLI 的命令层，不在 HTTP 层。
2. **API = 派生物** —— 将来的 HTTP 接口**从 CLI 的命令定义生成**，不再手写。
3. **手写 HTTP 层整体删除** —— 新老两套一并删净（不是"保留一套"）。

## 三、执行记录（本日，含撤销/恢复，如实记录）

**删除**

```
新 API   src/ai_factory_os/api/ 整体                        56 py · 3,169 行
老 API   .../web/backend/fastapi_adapter.py                 7,339 行 · 377 端点
冒烟     smoke_validation / smoke_metrics / smoke_schedules
         / smoke_decomposition_tasks / smoke_legacy_api      5 个脚本
```

**剥离后保留**（7,339 行里 CLI 在用的非 HTTP 部分，先剥出再删本体）

新建 `_pending_migration/factory_console/console_service.py`（221 行），含
`build_console_service`（147 行装配器）· `_console_import` · `DEFAULT_ROOT` ·
`DEFAULT_PORT` · `_factory_version` · `_read_json_map`。

> ★ 剥离时**顺带修掉一个存量 bug**：`_read_json_map` 原先定义在 fastapi_adapter 某函数
> **内部**（嵌套），而 `cli_factory.py:3573` 却从模块级 import 它 —— 那个 import **必抛
> ImportError 且无兜底**，`factory local-ai run` 因此**必崩**。剥离时提为模块级，该命令恢复可用。

**归位**（名字在 api/、实质不在）

```
api/dashboard/  →  apps/cli/dashboard/    它自述"只读 Dashboard (CLI 可视化控制台, Rich 非 Web)"
api/cli/        →  apps/cli/              早前已归位（SSoT §一: 消费者独立于 src/）
```

**★ 撤销的一次误删（如实记录）**

我一度把 `_pending_migration/factory_console/api/`（24 个模块）**整目录删除**，判据是"它们叫 api"。
**错了**：实测那 24 个模块的 `@router.` 装饰器数量**全是 0** —— 它们是**业务函数模块**
（143 个函数：`create_project` / `extract_project_name` / `save_discovery_answer` …），
只是文件名挂在 `api/` 下、被 fastapi_adapter 绑定成端点。删除会断 `agent_loop` 的"创建项目"。
已 `git checkout` 恢复。

> **教训（本 ADR 最有价值的一条）**：删任何目录前先判它是「路由」还是「业务」——
> **按实质，不按名字**。同类陷阱还有 `api/dashboard/`（名字在 api/，实质是 CLI 控制台）。

**连带同步**

```
SSoT §一 / §二 / §四      标注 api 层已删（§二 保留 15 域清单, 作为将来重建的依据）
守卫 _domain_dirs         目录不存在 → 返回空（不再 FileNotFoundError）
守卫 R20                  整层不存在 → 跳过该层
守卫 R21「一域一落点」      API 层已删 ⇒ 失去对象, 明确**暂停**（返回空 = 不适用, 不是"通过"）
cli_factory               BACKEND_MODULE = None + 两处启动点加显式失败守卫
infrastructure/process    console 启动面保持优雅失败（原就在 try/except 内）
```

## 四、后果与遗留

**已知后果**（按实测量化，不粉饰）

```
HTTP 端点     377 → 0        Web 控制台随之不可用（Founder 早前已定: "webui 后面再做, 现在不考虑"）
factory start 不可启动后端   显式报错"待 API 从 CLI 重建", 不静默失败
链路断点       会话环在 CLI 上**无入口** —— 端到端测试实测: 8 环里第 1 环空
              （`factory progress` 的链路表显示 "① 会话+理解 0 个会话"）
```

**待办**

1. **给 CLI 补会话入口** —— 这是"API 从 CLI 重建"的第一块，也是端到端链路的起点。
2. **重建 API 时以 CLI 命令域为源** —— `apps/cli/registry.py` 的 15 域即生成依据
   （SSoT §二 的 API 分组清单保留不删，就是为此）。
3. **`_CONSOLE_DIR` / `BACKEND_MODULE` 的模板保留** —— 将来生成 API 时可直接复用启动形态。

---

## 附：为什么"删一套"要删两遍

本 ADR 的执行不是"删掉多余的、留一套"，而是**两套都删**。理由：

```
新 API  —— 手写的, 没有真实消费者 ⇒ 删（它就是"手写"这个模式的产物）
老 API  —— 手写的, 有 Web 消费者  ⇒ 也删（Web 后续做, 且将来的 API 由 CLI 生成, 不是它）
```

留下任何一套，都会让"**API 从 CLI 生成**"这条决策在实现时面对"要不要兼容旧路由"的纠缠。
删净之后，重建是干净的。

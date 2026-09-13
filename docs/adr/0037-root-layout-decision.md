# ADR-0037：根布局定案 —— 采用 `src/ai_factory_os/` 布局

> 状态：**已接受（Accepted）** · 日期：2026-09-14 · 裁决人：项目所有者（创始人）
> 取代：`docs/cleanup/2026-09-11-MAPPING-RULES-PROPOSAL.md`（方案 A）
>       `docs/cleanup/2026-09-11-MIGRATION-MAP.md`（方案 B）

## 一、背景

仓库根目录同时存在**三套互相矛盾的目标布局**，且从未正式裁决：

| 方案 | 出处 | 顶层形状 |
|---|---|---|
| **A** | `2026-09-11-MAPPING-RULES-PROPOSAL.md` | 「根下直接建，不套 src/」：`extensions/` + `projections/`；并明列禁止 `kernel/` |
| **B** | `2026-09-11-MIGRATION-MAP.md` | `kernel/` + `extensions/` + `projections/`（`factory-console/api` → `projections/gateway/`） |
| **C** | `docs/ssot/architecture.md` | `src/ai_factory_os/{contracts,core,services,plugins,infrastructure,api,bootstrap}` + `apps/` 在 `src/` 外 |

实际根目录（33 项）里 6 个是旧布局遗留：`factory-console`(311 py) · `factory_console`(2) ·
`factory-core`(138) · `factory-exec`(51) · `factory-org`(18) · `factory-runtime`(12)。

**问题的技术本质是「没有命名空间」**：`factory-core/` 被挂进 `sys.path` 后，裸名导入
（`import models` / `import events` / `import store`）在多个实现间撞车，产出
**43 组同名文件**（`models.py`×25 · `store.py`×15 · `events.py`×11 · `service.py`×7 ·
`registry.py`×6 · `engine.py`×4）。

## 二、决策

**采用方案 C：`src/ai_factory_os/` 布局。**

```
src/ai_factory_os/
├── contracts/       11 域契约（零依赖）
├── core/            平台本体：scheduler + events（仅此两段）
├── services/        七域业务
├── plugins/         一切实现绑定
├── infrastructure/  技术底座
├── api/             对外接口层
└── bootstrap/       装配（唯一可 import 全局）
apps/                cli / web / desktop / mobile —— 独立于 src/
tests/  docs/  scripts/  bin/
```

## 三、决策理由

1. **唯一能根治命名空间撞车**：A 与 B 把新代码的顶层包直接放在根下，`contracts`/`core`/
   `extensions` 等名字仍与旧代码的裸名导入共存，43 组同名文件的问题不会消失，只会换个形态。
2. **`src/` 布局是 Python 打包的标准做法**：可编辑安装与 wheel 打包路径确定，`pythonpath`
   与 `packages` 配置不依赖 cwd。
3. **`apps/` 独立于 `src/`** 已被 A/B/C 三方共识（消费者不进包内）。
4. B 已经被实践否决过一次：那批空 `.gitkeep`（`kernel/` `extensions/` `projections/`
   `infrastructure/`）就是 B 的脚手架，长期无人填充。

## 四、被否决方案与遗留记录

**必须记录在案**（防止"决定被做过了但没人知道"）：

- 刀 1 曾**未经裁决**按 C 落地（理由仅为"SSoT 自称冻结"）—— 程序错误，本 ADR 是事后补正。
- 刀 11 曾把 `bootstrap/` `extensions/` `infrastructure/` `projections/` 四个空目录
  当"废弃占位"删除。**其中 `extensions/` 与 `projections/` 是方案 A/B 的计划目标目录**，
  并非垃圾。删除判断基于当时未经确认的"C 才是对的"假设。本 ADR 明确：这些目录按 C 不再需要，
  但**删除的动机当时未获授权**，如实记录。

## 五、后果

- **根目录的"正确形态"** = 上表 C 的树 + 仓库文件（README/LICENSE/CHANGELOG/pyproject 等）
  + 运行时目录（`projects/` `workspace/` `exec/`，已 gitignore）。目标是根下跌到约 15 项，
  **且不存在任何 `factory-*`**。
- **达到该形态的唯一路径**是绞杀搬迁：把旧代码逐批迁入 C 的各层。**没有批量移动的捷径** ——
  已实测：`factory-console` 的任意子目录都无法单独搬走（其 `api/` 有 68 处相对 import
  指向 10 个兄弟包；详见 knife-16 提交信息）。
- **搬迁难度由耦合度决定，不由文件数决定。** 批次选择必须先做可分离性检查。
- 契约数量以**实现为准**：11 域（见 SSoT v0.3），不再使用旧的"8 根 + 5 内核"表述。
- `core/` 只允许 `scheduler` 与 `events` 两个子模块（铁律 R17）。

## 六、关联

- 铁律：`tests/architecture/test_layer_dependencies.py`（R1–R12、R17）
  `tests/architecture/test_legacy_fence.py`（R13–R16）
- 迁移预算：`tests/architecture/migration_allowlist.json`
- 层级图：`docs/architecture/LAYER-MAP.html`
- 旧代码台账：`docs/cleanup/LEGACY-LEDGER.md`

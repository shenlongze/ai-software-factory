<!-- AUTO-GENERATED: DO NOT EDIT -->
<!-- 由 scripts/legacy_inventory.py --write 生成；派生视图，非事实源 -->

# 旧代码台账（LEGACY LEDGER）

> 生成时间: 2026-09-13T19:14:22+00:00 | 生成器: `scripts/legacy_inventory.py`
> 规则：**只减不增** —— 由 `tests/architecture/test_legacy_fence.py` 强制

## 一、分区总览

| 分区 | 文件 | 行数 | 活 | 仅测试 | 未证实 | 定性 | 目标 | 状态 |
|---|---:|---:|---:|---:|---:|---|---|---|
| `factory-console` | 311 | 128341 | 251 | 16 | 44 | 混合：新 OS 内核 + 旧会话链 + Web + API | 拆分 → services / core / api / apps | 待绞杀 |
| `factory-core` | 135 | 33478 | 30 | 86 | 19 | L4 旧数据层，24 包互引 | 逐包复核后归档 | 已判 132/138 可归档（实测待复核） |
| `factory-exec` | 51 | 22058 | 32 | 13 | 6 | 旧执行域（roles/skill/tool/provider/approval） | 同左，逐项判定 | 已判 51/52 可归档（实测待复核） |
| `factory-org` | 18 | 12052 | 14 | 2 | 2 | 组织领域模型（最完整） | services/organization | 待绞杀 |
| `factory-runtime` | 11 | 1528 | 0 | 0 | 11 | 旧 runtime bundle | core/node 或 infrastructure | 待判定 |
| `factory_console` | 2 | 21 | 1 | 0 | 1 | 打包胶水（连字符目录名的转发层） | 保留 | 合法，非冗余 |
| **合计** | **528** | **197478** | **328** | **117** | **83** | | | |

## 二、可达性（从活入口 BFS import 图）

> ⚠️ **本栏不产出「可删」结论。** 静态可达性无法证明代码是死的 ——
> 项目存在多种静态解析不到的加载方式（字符串动态加载、拼接式加载、经本地辅助函数转发）。
> 第三类一律标「未证实」，需人工确认后才可考虑处置。

入口：`bin/factory`, `factory-console/cli_factory.py`, `factory-console/web/backend/fastapi_adapter.py`

| 类别 | 文件 | 行数 | 含义 |
|---|---:|---:|---|
| 可达 | 328 | 150480 | 生产入口能走到（主链） |
| 仅测试可达 | 117 | 34936 | 只有测试能走到 |
| 未证实使用 | 83 | 12062 | 静态走不到 —— **不得当作可删** |
| **合计** | **528** | **197478** | |

> 其中 **45 文件 / 7720 行**受已知动态加载前缀影响（前缀 `factory_console.`），**尤其不可当作可删**。
> 动态调用 43 处；未解析字面量 9 条。

### 本栏的已知盲区（工具只扫 Python 的加载行为）

| 盲区 | 说明 | 实例 |
|---|---|---|
| `subprocess-cli` | 被当命令跑，不被 import | `desktop` 调 `factory-runtime` CLI |
| `path-reference` | 按文件系统路径引用 | 测试夹具指向 `demo/` |
| `non-python-consumer` | Rust / TS / JSON 里写死名字 | `tauri.conf.json` 打包 `factory-runtime-bundle` |
| `computed-dynamic` | 非字面量拼接的动态加载 | `f"{prefix}{name}"` |

### 非 Python 载体引用（弱信号：可能含文档性提及，但被点名者绝不可当作可删）

| 分区 | 引用文件数 | 例 |
|---|---:|---|
| `factory-console` | 5 | `factory-runtime/bundle/factory_runtime_bundle.spec` |
| `factory-core` | 6 | `factory-exec/pyproject.toml` |
| `factory-exec` | 6 | `factory-exec/pyproject.toml` |
| `factory-org` | 3 | `factory-org/pyproject.toml` |
| `factory-runtime` | 7 | `apps/desktop/package.json` |
| `factory_console` | 1 | `pyproject.toml` |

## 三、跨分区依赖边（只减不增）

| 从 | 到 | 次数 |
|---|---|---:|
| `factory-console` | `factory_console` | 26 |

## 四、说明

- 被绞杀对象：`factory-console`, `factory-core`, `factory-exec`, `factory-org`, `factory-runtime`, `factory_console`
- 不计入围栏：`scripts/`（工具）、`docs/`、`bin/`、`apps/`、`tests/`、`src/`（新地基）
- 本台账是**派生视图**，不属 SSoT；手写修改将在下次生成时被覆盖。

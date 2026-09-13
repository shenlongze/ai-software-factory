<!-- AUTO-GENERATED: DO NOT EDIT -->
<!-- 由 scripts/legacy_inventory.py --write 生成；派生视图，非事实源 -->

# 旧代码台账（LEGACY LEDGER）

> 生成时间: 2026-09-13T18:00:31+00:00 | 生成器: `scripts/legacy_inventory.py`
> 规则：**只减不增** —— 由 `tests/architecture/test_legacy_fence.py` 强制

## 一、分区总览

| 分区 | 文件 | 行数 | 定性 | 目标 | 状态 |
|---|---:|---:|---|---|---|
| `demo` | 2 | 23 | 演示代码 | archive | 待处理 |
| `factory-console` | 311 | 128352 | 混合：新 OS 内核 + 旧会话链 + Web + API | 拆分 → services / core / api / apps | 待绞杀 |
| `factory-core` | 138 | 33814 | L4 旧数据层，24 包互引 | 逐包复核后归档 | 已判 132/138 可归档 |
| `factory-exec` | 51 | 22058 | 旧执行域（roles/skill/tool/provider/approval） | 同左，逐项判定 | 已判 51/52 可归档 |
| `factory-org` | 18 | 12052 | 组织领域模型（最完整） | services/organization | 待绞杀 |
| `factory-runtime` | 11 | 1528 | 旧 runtime bundle | core/node 或 infrastructure | 待判定 |
| `factory_console` | 2 | 21 | 打包胶水（连字符目录名的转发层） | 保留 | 合法，非冗余 |
| `kernel` | 7 | 302 | v0.2 遗留契约（契约已并入 src/…/contracts） | 删除 | 待删 |
| `services` | 5 | 348 | 绞杀示范 approval_runtime | src/…/services | 示范保留 |
| **合计** | **545** | **198498** | | | |

## 二、跨分区依赖边（只减不增）

| 从 | 到 | 次数 |
|---|---|---:|
| `factory-console` | `factory_console` | 26 |
| `factory-console` | `services` | 1 |
| `factory-core` | `demo` | 1 |
| `services` | `kernel` | 1 |

## 三、说明

- 被绞杀对象：`demo`, `factory-console`, `factory-core`, `factory-exec`, `factory-org`, `factory-runtime`, `factory_console`, `kernel`, `services`
- 不计入围栏：`scripts/`（工具）、`docs/`、`bin/`、`apps/`、`tests/`、`src/`（新地基）
- 本台账是**派生视图**，不属 SSoT；手写修改将在下次生成时被覆盖。

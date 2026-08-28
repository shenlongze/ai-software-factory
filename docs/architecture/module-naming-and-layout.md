# 模块命名与目录布局（R4, v1.1.254）

> 目的: 文档化 `factory-console/`（连字符）与 `factory_console/`（下划线）双轨机制，
> 消除混淆，明确 shim 职责。同步记录 benchmark 目录归属。

## 一、双轨命名机制（为什么有两个）

| 路径 | 性质 | 职责 |
|---|---|---|
| `factory-console/` | 真实实现（目录名含连字符） | 全部业务逻辑：session/api/web/tools/memory… |
| `factory_console/` | 别名 shim（importlib 转发，**零业务逻辑**） | 让 `from factory_console.xxx import yyy` 语法可用（Python 包名不允许连字符） |

### 为什么需要 shim
- 目录名 `factory-console` 含连字符，无法作为 `from <module> import <attr>` 的模块名
- 但 CLI console script / 运行时需要用下划线包名导入 → `factory_console/__init__.py` 用
  `importlib` 转发到真实实现（见 `factory_console/__init__.py` 注释）

### 使用规则
1. **业务代码** 一律在 `factory-console/` 下开发，用相对导入（`from .actions import …`）
2. **运行时/测试/外部入口** 需要包名时，用 `factory_console`（下划线）——走 shim 转发
3. **不要** 在 `factory-console/` 内部 import `factory_console`（会绕过相对路径，破坏包边界）
4. 新增模块 → `factory-console/` 下；不要动 `factory_console/`（除非 shim 转发缺条目）

## 二、顶层包职责（五层）

| 包 | 规模 | 职责 |
|---|---|---|
| `factory-console/` | ~89k 行 | 应用层: 会话/agent/CLI/Web/工具 |
| `factory-core/` | ~34k 行 | 业务域: 项目/任务/审批/编排/工作流 |
| `factory-exec/` | ~28k 行 | 执行器 (exec) |
| `factory-org/` | ~12k 行 | 组织: 审批/产物/生命周期 |
| `factory-runtime/` | ~1.6k 行 | 运行时: bundle/health/manager |

依赖方向: core/org/runtime 独立；console 自包含（不反向依赖 core/exec/org 包级 import）。

## 三、benchmark 目录归属（R3）

- 评测脚本 → `tests/benchmark/{s6b,s8_demo,s9_pilot}`（不在生产包 `factory-exec/` 下）
- `factory-exec/` 只保留运行时代码 `exec/`

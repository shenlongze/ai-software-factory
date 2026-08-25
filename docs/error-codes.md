# AI Factory — 错误码集中表 (M5-7, S10-121)

> 日期: 2026-08-25 | 版本: v1.1.95 | 用途: 主要错误路径统一编码 — `模块:CODE: 消息: 建议下一步`。
> 规则: 新增/修改主要错误路径必须在本表登记 (契约测试 tests/console/test_s10_121_eval_suite.py 断言主要错误路径有码)。
> 未覆盖错误路径 (历史散消息) 如实保留原样 — 本表从 K-5 起增量收敛, 不假装全清。

## 约定

| 段 | 含义 | 示例 |
|---|---|---|
| `E4xxx` | CLI 命令域 (factory-console/cli_factory.py) | E4001 参数缺失 |
| `E41xx` | 评测/发布门域 (eval_suite + factory eval) | E4102 发布门阻断 |
| `E5xxx` | 脚本域 (scripts/smoke_longrun / smoke_24h / coverage_report) | E5101 覆盖度失败 |
| `E6xxx` | Session/生命周期域 (eval_loop / lifecycle_store) | E6101 防回退拒绝 |

> 说明: `factory eval --gate` 阻断时 rc 非 0 (E4102); `--check` 只读报告不阻断。未定义维度如实"未覆盖" (E4201 原因)。

## 错误码表

| 模块 | CODE | 消息 | 建议下一步 |
|---|---|---|---|
| cli_factory | E4001 | `--task`/`--objective` 二选一必填 | 二选一补齐后重试 `factory run` |
| cli_factory | E4002 | `--repo-path` 必填 (已有代码库路径) | 传入 `--repo-path <已有代码库路径>` 后重试 |
| cli_factory | E4003 | `create project` 需要 `--name <项目名>` | 显式传入 `--name` 后重试 |
| cli_factory | E4101 | 评测运行失败 (EvalSuite 异常) | 查看报错详情修复后重跑 `factory eval` |
| cli_factory | E4102 | 发布门未通过 — 阻断发布 | 补齐未覆盖/失败维度证据后重跑; 或按实际发布类型调整 `--gate` 等级 |
| cli_factory | E4201 | 评测维度未覆盖 (无法证明通过) | 在临时 workspace 跑对应 fixture (H-1/并发/长跑/学习闭环) 后重跑 |
| cli_factory | E4301 | 未知命令 | `factory help` 查看命令总览后重试 |
| cli_factory | E4302 | `project` 未知子命令 | 用 create/list/rename/status/reconcile 之一 |
| cli_factory | E4303 | `config` 未知动作 | 用 show/set/check/path 之一 |
| cli_factory | E4304 | `doctor` 未知检查器 | 用 environment/provider/model/runtime/router 之一 |
| eval_suite | E4101 | 评测运行失败 (run() 抛异常) | 修复后重跑; 评测项失败安全 (单项异常 → 该项失败/未覆盖, 不崩) |
| eval_suite | E4102 | 发布门未通过 (gate_passed=False) | 见各维度 gate_reasons; 补齐证据后重跑 |
| eval_suite | E4201 | 维度未覆盖 (not_covered) | 见维度 detail; 不伪造分数, 如实标注 |
| smoke_longrun | E5001 | `--duration`/`--heartbeat` 必须为正整数 | 传正数后重试 |
| smoke_longrun | E5002 | 长跑冒烟异常 | 查看异常详情后重试 (默认临时 workspace 零污染) |
| coverage_report | E5101 | 覆盖度统计失败 | 查看异常详情后重试 (stdlib trace, 零第三方依赖) |
| lifecycle_store | E6101 | 防回退守卫拒绝 (新状态落后 canonical) | 显式 force=True 仅允许变更控制等白名单场景 |
| lifecycle_store | E6102 | 状态文件损坏无法安全写入 | 先修复/备份状态文件; 绝不覆盖损坏文件 |
| execution_quality | E6201 | 评分器失败 → score=None + reason (软错误, 不阻断) | 查看 reason; 调用方如实展示 None 分数, 不臆造 |
| eval_loop | E6301 | 评估驱动修复闭环失败 (status=failed) | 查看 message; 闭环本身失败安全不抛 |

## 契约断言 (tests/console/test_s10_121_eval_suite.py)

- 本表存在且含列头 `模块 | CODE | 消息 | 建议下一步`
- 主要错误路径有码: cli_factory 源码含 `[E4001]`/`[E4002]`/`[E4003]`/`[E4101]`/`[E4102]`;
  scripts 含 `[E5001]`/`[E5002]`/`[E5101]`; 且本表均已登记
- 行为断言: `factory run` 缺参数 → stderr 含 `[E4001]` rc 2;
  `factory eval --gate patch` 空 workspace → stderr 含 `[E4102]` rc 1

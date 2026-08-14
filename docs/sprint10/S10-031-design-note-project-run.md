# S10-031 Design Note — factory project/run 转正

> 日期:2026-08-14 | Sprint: S10-031 First User Release | Reality Check + 设计(约束 8)
> 问题:S10-030 实测 — factory project/run 是 stub,用户路径后段断裂(create project → run task)

---

## 1. Reality Check(实测)

| 项 | 现状 |
|---|---|
| factory project | stub(STUB_COMMANDS) — `factory project create --name x` → "unrecognized arguments" |
| factory run | stub(STUB_COMMANDS) — `factory run --task T-001` → "unrecognized arguments" |
| org CLI | `project register` 可用(注册已有项目:repo_path 必需) |
| exec CLI | `run --project <dir> --task <id> [--agent] [--provider]` 可用;`status --id` 可用 |
| 复用原则 | 不新写业务逻辑,薄代理现有 exec/org CLI 能力 |

## 2. 设计决策

| # | 决策 | 理由 |
|---|---|---|
| D1 | factory run 转正 → **代理 exec CLI cmd_exec_run**(importlib 调 exec.cli) | 执行链已完整(S10-023),零新 AI 能力 |
| D2 | factory run status → 代理 exec CLI cmd_exec_status | 结果查询 |
| D3 | factory project create → **代理 org CLI cmd_project_register**(需 repo_path) | 项目接入已有 |
| D4 | factory project list → 读 ~/.factory/org/projects.json(或 org CLI project 查询) | 简单只读 |
| D5 | 参数兼容 exec CLI:--project/--task/--agent/--provider/--objective/--requirement/--test-cmd + --json | 与底层一致,用户可参考 exec CLI help |
| D6 | 失败安全:底层异常 → 明确错误消息,不吞 | 项目铁律 |
| D7 | 不修改 exec/org CLI 本身;不修改 Kernel/Runtime/Router/Provider/AgentExecutor | 约束 2/4 |

## 3. 实现方式

```python
# cli_factory.py 新增
def _proxy_exec_cli() -> Any:
    """延迟 import exec.cli (PYTHONPATH 挂 factory-exec, 项目既有模式)。"""
    sys.path.insert(0, str(ROOT / "factory-exec"))
    import exec.cli as exec_cli
    return exec_cli

# FactoryCLI.run_command(args):
#   exec_cli.cmd_exec_run(root=self.data_dir, args=args)  # 薄代理
# FactoryCLI.project_command(args):
#   org_cli.cmd_project_register(...) 或 projects.json 只读
```

## 4. 修改范围

- 修改 factory-console/cli_factory.py(仅 project/run 两个命令从 stub 转正;其余命令零改动)
- 新增 tests/console/test_cli_project_run.py
- 不动:exec/org/core/llm_control/router/model_catalog 全部

## 5. 验收

```
A. factory run --project <dir> --task <id> --agent backend-1 → 真实执行(或诚实失败)
B. factory run status --id <id> → 结果查询
C. factory project create --repo <path> → 项目注册
D. factory project list → 项目列表
E. 参数缺失 → 明确错误(如 --task 必填)
F. 新增测试全绿 + 全量 8116 不破坏
G. commit + push
```

## 6. 关联阻塞(本 Task 不解决,记录)

- console script 指向 org CLI(pyproject.toml)— 独立 Task
- 前端 dist 打包 — 独立 Task
- 私有仓库 — 独立 Task

---

> Design Note 完毕 | 薄代理方案,零新 AI 能力,零核心修改

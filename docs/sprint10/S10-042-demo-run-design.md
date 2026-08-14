# S10-042 Task 001 — factory demo run 设计

> 日期:2026-08-14 | Sprint: S10-042 | 只设计, 不编码
> 目标: 一条命令完成首次体验(workspace → project → task → agent → execution → artifact)

---

## 1. 命令签名

```bash
factory demo run "<objective>" [--agent backend-1] [--provider deepseek] [--no-cleanup] [--project-dir <dir>]
```

| 参数 | 默认 | 说明 |
|---|---|---|
| objective(位置参数) | 必填 | 自然语言目标, 如 "给 main.py 加一个加法函数" |
| --agent | backend-1 | 执行 Agent |
| --provider | (Router 决策) | 显式指定模型 Provider; 缺省走 ControlPlane selected |
| --no-cleanup | false | 保留临时演示目录(默认清理) |
| --project-dir | 自动生成 | 指定项目目录(否则自动建 /tmp/factory-demo-<ts>/ 含 main.py 骨架) |

## 2. 内部流程(全复用现有能力, 零新 AI)

```
factory demo run "给 main.py 加 hello"
  │
  ├─ 0. 环境检查: _env_problems() 通过 (python/node)
  ├─ 1. workspace 准备: _demo_root() 确保存在 (复用 _ensure_workspace/_demo_write_providers)
  ├─ 2. project 目录:   自动建 /tmp/factory-demo-<ts>/main.py 骨架
  │                      (--project-dir 指定则复用)
  ├─ 3. task 创建:      生成 task (objective=用户输入) — 复用 tasks store 或直接传 exec
  ├─ 4. agent 执行:     exec_cli.cmd_exec_run (薄代理, 复用 run_cmd 路径)
  │                      provider 缺省 → ControlPlane.selected_provider_id (Router 决策)
  ├─ 5. artifact 展示:  打印 status + usage + patch 摘要 (复用 run-status 输出)
  └─ 6. 清理(默认):     --no-cleanup 保留临时目录
```

## 3. 复用点(严格)

| 步骤 | 复用 | 不复制 |
|---|---|---|
| workspace | cli_factory._demo_init 的 `_ensure_workspace`/`_demo_write_providers`/`_demo_root` | 不重写 |
| project 目录 | 自动生成(新逻辑, 仅 mkdir + 骨架文件) | — |
| task | tasks store(或 exec run --objective 路径) | 不新造 task 系统 |
| execution | exec_cli.cmd_exec_run(薄代理) | **不复制执行逻辑** |
| provider | ControlPlane.selected_provider_id(复用 _default_provider_id 思路) | 不新装配 |

## 4. 实现位置

```
factory-console/cli_factory.py:
  - demo parser: 增加 "run" 动作 + objective 位置参数 + --agent/--provider/--no-cleanup/--project-dir
  - FactoryCLI._demo_run(args): 编排流程 (调用现有 helper, 不复制执行)
  - 辅助: _demo_make_project_dir(objective) → Path (mkdir + main.py 骨架)
```

## 5. 边界(严格)

| 允许 | 禁止 |
|---|---|
| 修改 cli_factory.py(仅 demo run 新增 + demo parser) | 修改 exec/org/core 任何文件 |
| 新增测试 tests/console/test_cli_demo_run.py | 修改 ExecutionLoop/Router/Provider |
| 新增 docs 更新 | 新增 AI 能力 |
| 复用现有 helper(零复制执行逻辑) | 引入新依赖 |

## 6. 失败安全

- key 缺失 → 明确提示(如 exec run 现有行为: provider not found → 建议 factory init)
- 临时目录创建失败 → 错误消息, 不吞
- --no-cleanup 时打印目录路径(用户可查看)
- 清理用 _demo_rmtree(现有护栏, 只删 demo 根)

## 7. 输出示例

```
=== AI Factory Quick Demo ===
✔ workspace 就绪 (~/.factory-demo)
✔ 项目目录: /tmp/factory-demo-abc123/main.py
✔ 目标: 给 main.py 加 hello 函数
✔ 执行: backend-1 → deepseek (Router 决策)

  status      success
  artifact    patch  ~/.factory-demo/exec/patches/EXS-....patch
  usage       1234 tokens · $0.0009

✔ 完成! 用时 42 秒, 成本 < $0.01
(演示目录保留: /tmp/factory-demo-abc123)
```

## 8. 验收

```
A. factory demo run "给 main.py 加 hello" → 真实 LLM 执行 success
B. 复用 exec CLI(不复制逻辑, 代码审查确认)
C. 旧 CLI 兼容 (factory project/run/demo init 等不受影响)
D. 新增测试全绿 + 全量 8148 不破坏
E. commit + push
```

---

> Task 001 完毕 | demo run 设计完成 | 全复用现有能力 | 零新 AI

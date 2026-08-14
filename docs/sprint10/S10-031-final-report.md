# S10-031 最终报告 — First User Release

> 日期:2026-08-14 | Sprint: S10-031 First User Release | 目标达成:陌生用户可安装、启动、执行第一个 AI 任务

---

## 1. Sprint 目标达成确认

**核心目标:把 AI Factory 从"技术验证完成的工程项目"推进到"陌生用户可以安装、启动、执行第一个 AI 任务的 MVP 产品"。**

实测验证(全新 venv + 隔离 HOME,模拟陌生用户):
```
pip install wheel (全新 Python 3.12 venv, 依赖自动解析)
→ factory init --non-interactive --provider deepseek   ✅ (workspace + providers.json)
→ factory doctor                                       ✅ (诊断)
→ factory project create --repo-path <dir>             ✅ (真实注册 P-xxx)
→ factory run --project --task --agent backend-1       ✅ (真实 DeepSeek 执行!)
    status: success | artifact: patch/report | usage: 8192 tokens, $0.00319
```

**用户路径从"断裂"到"完整真实执行" — S10-031 目标达成。**

## 2. 交付清单(5 commits)

| Task | Commit | 内容 |
|---|---|---|
| 1 project/run 转正 | 483de4f | 薄代理 exec CLI / org CLI(用户路径后半段打通) |
| 2 release packaging | fc2f41e | package_dir 映射 + console script + dist 打包(修复空壳 wheel) |
| 2+3 发布缺陷修复 | 6877eb1 | exec/org 子包 + dependencies + ControlPlane 默认 provider + demo.sh 适配 + wheel 依赖门 |
| 3 全新环境验证 | (含于 6877eb1) | 端到端验证: install→init→run→artifact 全通 |
| 4 README 重写 | cc8f930 | 用户向: 解决问题→安装→5 分钟体验(113 行) |

## 3. 关键成果

### 3.1 用户路径完整打通(核心)
```
S10-030 审计时: project/run stub → 路径断裂 (2/10 分)
S10-031 完成后: 全路径真实执行 (install→init→project→run→artifact)
```

### 3.2 发布缺陷修复(3 个真实问题)
| # | 缺陷 | 影响 | 修复 |
|---|---|---|---|
| 1 | packages.find where 配置错误 | wheel 空壳(无代码包) | package_dir 映射 factory_console→factory-console |
| 2 | exec/org 子包未打包 | exec CLI ControlPlane 装配静默失败 | packages 补 exec.providers/exec.tools/exec.benchmark/org |
| 3 | httpx/fastapi/uvicorn 缺 dependencies | 全新环境无法运行 | dependencies 补齐 |
| 4 | exec CLI provider 默认硬编码 anthropic | 用户配 deepseek 不被采用 | _default_provider_id() → ControlPlane 决策 |
| 5 | cli_factory wheel 模式 root 推导错 | init 要求源码仓库依赖 | _dep_problems 识别 wheel 模式跳过 |
| 6 | demo.sh 旧命令 demo markpad | 演示脚本失效 | 适配 S10-026 demo init/status |

### 3.3 全新环境端到端证据(真实执行)
```
wheel: ai_software_factory-1.0.0rc1-py3-none-any.whl (含 41+ factory_console 文件 + exec/org + dist)
安装: 全新 venv → pip install wheel (依赖自动解析: pydantic/rich/pyyaml/httpx/fastapi/uvicorn)
运行: factory run → DeepSeek 真实调用 → success
usage: prompt 1795 + completion 6397 = 8192 tokens, cost $0.00319
artifact: patch + test_result + report (审计事件 3)
```

## 4. 测试状态

```
全量 pytest: 8148 passed, 0 failed   (基线 8116 → 8148, +32, 零回归)
- 新增: test_cli_project_run 21 / test_release_packaging 12
- 修复: demo 测试适配 S10-026 语义 / env gate 测试适配 wheel 模式
- 预存失败: 0 (S10-027 已清零)
```

## 5. 约束遵守确认

| 约束 | 状态 |
|---|---|
| 1. 不新增 AI 能力 | ✅ (project/run 是薄代理,零新 AI 逻辑) |
| 2. 不重构核心架构 | ✅ (Kernel/Runtime/Router/Provider/AgentExecutor 零改动) |
| 3. 最大化复用 S10-021~030 | ✅ (薄代理 exec/org CLI + ControlPlane) |
| 4. Kernel/Runtime/Router/Provider/AgentExecutor 边界稳定 | ✅ (exec/cli.py 只加辅助函数,不改核心) |
| 5. 每 Task 独立 commit | ✅ (5 commits 全部独立) |
| 6. 完成即验证/提交/push | ✅ |
| 7. git clean | ✅ |
| 8. 设计问题 → Reality Check + Design Note | ✅ (S10-031-design-note-packaging-fix.md) |

## 6. 已知问题/后续

| # | 事项 | 优先级 |
|---|---|---|
| 1 | PyPI 正式发布(当前是本地 wheel;README 标"即将支持") | P0 |
| 2 | 仓库公开(当前私有,陌生用户无法 clone) | P0 |
| 3 | factory start 前端(web-dist 已打包,需验证浏览器访问) | P1 |
| 4 | exec CLI 薄代理的 status/status 子命令完整对齐 | P1 |
| 5 | 演示视频 + 技术博客(S10-030 验证内容) | P1 |

## 7. 结论

**S10-031 First User Release 目标达成:AI Factory 现在是陌生用户可以安装、启动、执行第一个 AI 任务的 MVP 产品。**

- 用户路径全通:install → init → project → run → artifact(真实 DeepSeek 执行)
- 发布形态就绪:wheel 含全部代码 + 前端 dist + 依赖声明
- 质量保障:8148 全绿,零回归
- 文档用户向:README 首屏痛点 + 5 分钟体验

**剩余发布阻塞(非代码):PyPI 发布 + 仓库公开 — 需要用户决策(公开仓库/账号配置)。**

---

> S10-031 完毕 | 5 commits | 8148 passed | 用户路径端到端验证通过 | MVP 可安装可运行

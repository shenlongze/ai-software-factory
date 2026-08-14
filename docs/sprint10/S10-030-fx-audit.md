# S10-030 Task 001 — First User Experience Audit

> 日期:2026-08-14 | Sprint: S10-030 MVP Release | 真实用户路径实测(隔离 HOME),未修改代码
> 目标:分析新用户完整路径,找出所有阻塞

---

## 1. 用户路径实测

隔离 HOME 实测(2026-08-14):

| 步骤 | 用户操作 | 实测结果 | 状态 |
|---|---|---|---|
| 1 | git clone | 仓库私有(需权限) | ⚠️ 分发阻塞 |
| 2 | bash scripts/setup.sh | venv + install + npm(幂等) | ✅ |
| 3 | ./bin/factory init | workspace + providers.json 引导 | ✅ |
| 4 | config set core.port 9001 | 白名单写入成功 | ✅ |
| 5 | ./bin/factory doctor | 1 PASS / 4 WARN(环境/Provider 提示) | ✅ |
| 6 | ./bin/factory start | 后端+前端(需 key 才真实执行) | ✅ |
| 7 | **factory project create** | **stub — "unrecognized arguments"** | ❌ **阻塞** |
| 8 | **factory run --task** | **stub — "unrecognized arguments"** | ❌ **阻塞** |

## 2. 阻塞清单

| # | 阻塞 | 严重度 | 证据 | 影响 |
|---|---|---|---|---|
| B1 | **factory project 是 stub** | 🔴 P0 | 实测: `factory project create --name test` → "unrecognized arguments" | 用户无法从 CLI 创建项目 |
| B2 | **factory run 是 stub** | 🔴 P0 | 实测: `factory run --task T-001` → "unrecognized arguments" | 用户无法从 CLI 运行任务 |
| B3 | **私有仓库** | 🔴 P0 | clone 需 GitHub 权限 | 陌生用户无法安装 |
| B4 | **console script 指向 org CLI** | 🟡 P1 | pyproject.toml: `factory = "cli.main:main"` (org CLI),非 cli_factory | `pip install` 后 `factory` 命令是 org CLI 不是统一入口 |
| B5 | **README 首次指引脱节** | 🟡 P1 | 旧 7 页描述;无四步指引 | 用户不知道路径 |
| B6 | **LLM key 配置无引导文档** | 🟡 P1 | init 提示但无 export 示例 | 新用户执行 FAILED 需自查 |
| B7 | **前端依赖 npm**(start 用 vite) | 🟡 P1 | dist 已构建但 start 未默认用 | 无 node 用户前端不可用 |
| B8 | project/run 无 --json | 🟢 P2 | — | 自动化不足 |

## 3. 用户路径后段方案(设计,不实现)

```
factory project create --name <name> [--template todo-app]
  → 代理 org CLI project register 或 service API
factory run --task <task_id> [--agent <agent_id>] [--project-dir <dir>]
  → 代理 exec CLI run 或 service execute_runtime_task
```

**关键:打通 B1/B2 = MVP 用户路径完整的唯一硬阻塞。**

## 4. 用户体验评分

| 维度 | 评分 | 说明 |
|---|---|---|
| 安装 | 7/10 | setup.sh 幂等;私有仓库阻塞分发 |
| 初始化 | 9/10 | init 引导完整 |
| 诊断 | 9/10 | doctor 清晰 |
| 项目创建 | **2/10** | stub 阻塞 |
| 任务运行 | **2/10** | stub 阻塞 |
| 文档 | 5/10 | README 脱节 |

**总分:5.7/10 — 前半段(安装→诊断)优秀,后半段(项目→任务)断裂。**

## 5. MVP 发布必修复(优先级)

```
P0 (阻塞发布):
  1. factory project 转正 (create/list/show) — 薄代理 org CLI/service
  2. factory run 转正 (run/status) — 薄代理 exec CLI/service
  3. 分发: PyPI 发布 或 release tarball + 仓库公开
  4. console script 指向 cli_factory (pip install 后统一入口)

P1 (发布质量):
  5. README 四步指引 + LLM key 配置说明
  6. start 前端优先 dist 托管 (免 node)

P2 (增强):
  7. project/run --json
  8. factory version
```

## 6. 结论

- **前段路径(install→init→doctor→start)已产品化** — S10-026 成果
- **后段路径(project→run)完全断裂** — S10-026 时 project/run 留作 stub,现在是 MVP 发布最大硬阻塞
- **修复路径清晰**:project/run 薄代理现有 org CLI/exec CLI/service(零新 AI 能力,纯入口打通)
- 配合分发(私有仓库→PyPI)即达 MVP

---

> Task 001 完毕 | 实测 8 步路径 | 阻塞: project/run stub (P0) + 私有仓库 (P0)

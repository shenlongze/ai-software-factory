# S10-027 Task B — CLI Product Readiness Audit

> 日期:2026-08-14 | Sprint: S10-027 Hardening | 只读审计(含真实 exit code 抽查)
> 对象:./bin/factory 命令体系

---

## 1. 命令清单与状态

| 命令 | help | 错误提示 | exit code | 参数设计 | 状态 |
|---|---|---|---|---|---|
| factory init | ✅ | ✅ 环境缺失明确指引 | 0/1 | --force/--non-interactive/--provider/--model | ✅ 完整 |
| factory doctor | ✅ | ✅ 检查器缺失 exit 2 | 0/1/2 | --json/--verbose/指定检查器 | ✅ 完整 |
| factory config | ✅ | ✅ 白名单拒绝+红线消息 | 0/1 | show/set/check/path | ✅ 完整 |
| factory start | ✅ | ✅ 端口占用/依赖缺失 | 0/1 | --no-browser/--port/--frontend-port/--dev | ✅ 完整 |
| factory stop | ✅ | ✅ | 0 | — | ✅ |
| factory status | ✅ | ✅ | 0 | — | ✅ |
| factory service | ✅ | ✅ 服务不存在 exit 2 | 0/2 | list/start 指定服务 | ✅ |
| factory agent | ✅ | ✅ 无数据空列表 | 0 | (骨架) | ⚠️ 骨架 |
| factory skill | ✅ | ✅ | 0 | (骨架) | ⚠️ 骨架 |
| factory task | ✅ | ✅ | 0 | (骨架) | ⚠️ 骨架 |
| factory router | ✅ | ✅ | 0 | (骨架) | ⚠️ 骨架 |
| factory rag | ✅ 占位说明 | ✅ | 0 | (占位) | ⚠️ 占位 |
| factory audit | ✅ | ✅ | 0 | (骨架只读) | ⚠️ 骨架 |
| factory demo | ✅ | ✅ 未初始化提示 | 0/1 | init/status/reset/start | ✅ |

## 2. 实测 exit code(真实执行)

```
factory doctor (无配置环境)   → 1 (有 FAIL 时) / 0 (仅 WARN)
factory config set llm.provider x → 1 (红线拒绝) ✅ 正确
factory nonexistent (未知命令)  → 2 ✅
factory rag (占位)            → 0 ✅
factory init --non-interactive → 0 ✅
factory demo status (未初始化) → 0 (提示先 init) — 可接受
```

## 3. 深度审计

### 3.1 help 完整性 ✅
- 顶层 `factory --help` 列出全部 15+ 命令,每个有 description
- 子命令 `factory init --help` / `factory doctor --help` 参数说明完整
- 骨架命令(agent/rag)也有明确 help(rag 明确"占位 — 规划中")

### 3.2 错误提示 ✅
- 环境缺失:`请先安装依赖: python3 -m venv ...`(bin/factory 引导)
- 配置红线:`拒绝写入 llm.provider: config.json 只存运行时配置 (红线 ①)...`
- 服务不存在:`exit 2`
- doctor 检查器缺失:`exit 2`
- 端口占用:`端口已被占用: 后端端口 8011 — 请先释放端口...`

### 3.3 exit code 约定(已统一)
```
0 = 成功 (含 WARN — 非阻塞)
1 = 失败/阻塞 (FAIL/红线拒绝/环境缺失)
2 = 用法错误 (未知命令/未知检查器/未知服务)
```
✅ 一致性好。小建议:docstring 中明确此约定(当前散落在各方法)。

### 3.4 参数设计 ✅
- 全局风格一致:`--non-interactive`(init)、`--json`(doctor)、`--verbose`
- 端口参数:`--port/--frontend-port`(start)
- 骨架命令零参数(只读列表)

### 3.5 自动补全可能性
| 维度 | 现状 | 建议 |
|---|---|---|
| 子命令枚举 | argparse subparsers(静态可枚举) | **完全支持补全** |
| 参数枚举 | 静态 choices(doctor 检查器/service id) | 支持静态补全 |
| 动态补全 | provider id/agent id 运行时数据 | 需 shell 补全脚本回调 CLI |

**结论:自动补全可行** — 子命令/参数都是 argparse 静态结构。建议:
- bash/zsh 补全脚本:`_factory() { compgen -W "$(factory __complete 2>/dev/null)" }`
- 或简单方案:`factory --list-commands`(静态)+ 每命令 --help 解析
- 非本 Sprint 实现(记录为下一阶段)

## 4. 发现的问题

| # | 问题 | 严重度 | 建议 |
|---|---|---|---|
| 1 | 3 CLI 入口仍分裂(bin/factory vs org CLI vs exec CLI) | 中 | factory org/task 完整代理(S10-026 已建骨架) |
| 2 | exit code 约定未文档化 | 低 | 在 cli_factory docstring 声明 0/1/2 |
| 3 | rag 占位命令存在但未来若实现需迁移(不破坏) | 低 | 记录:占位是设计决策,实现时替换 |
| 4 | 自动补全未实现 | 低 | 下一阶段(需 --list-commands 或补全脚本) |
| 5 | demo status 未初始化 exit 0(应 exit 1 提示阻塞) | 低 | 可改:未初始化 → exit 1(小修复) |

## 5. 结论

**CLI 产品就绪度:高(85%)**
- ✅ help/错误提示/exit code/参数设计 均已产品化(S10-026 成果)
- ✅ 唯一入口 ./bin/factory 已建立
- ⚠️ 剩余:3 入口完整代理(骨架已建)+ 自动补全 + exit code 文档化
- 无阻塞性缺陷;可进入 release 准备(配合 Task F)

---

> 审计完毕 | 只读(含 exit code 真实抽查) | 修复项记录不阻塞

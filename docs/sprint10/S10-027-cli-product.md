# S10-027 Task 4 — CLI Product Readiness Audit

> 日期:2026-08-14 | Sprint: S10-027 Hardening | 只读审计(含真实 exit code 抽查)
> 目标:验证无 UI 时 AI Factory 是否完整可用;提出未来 CLI 标准

---

## 1. 命令清单与就绪度

| 命令 | 状态 | help | exit code | JSON | 自动化 |
|---|---|---|---|---|---|
| factory init | ✅ | ✅ | 0/1 | ❌ | --non-interactive ✅ |
| factory doctor | ✅ | ✅ | 0/1/2 | ✅ --json | 指定检查器 ✅ |
| factory config | ✅ | ✅ | 0/1 | ❌ | show/set/check/path ✅ |
| factory start | ✅ | ✅ | 0/1 | ❌ | 幂等/端口预检 ✅ |
| factory stop | ✅ | ✅ | 0 | ❌ | ✅ |
| factory status | ✅ | ✅ | 0 | ❌ | ✅ |
| factory service | ✅ | ✅ | 0/2 | ❌ | list ✅ |
| factory agent | ⚠️ 骨架 | ✅ | 0 | ❌ | 只读 ✅ |
| factory skill | ⚠️ 骨架 | ✅ | 0 | ❌ | 只读 ✅ |
| factory task | ⚠️ 骨架 | ✅ | 0 | ❌ | 只读 ✅ |
| factory router | ⚠️ 骨架 | ✅ | 0 | ❌ | 只读 ✅ |
| factory rag | ⚠️ 占位 | ✅ | 0 | ❌ | 明确占位 ✅ |
| factory audit | ✅ 骨架 | ✅ | 0 | ❌ | 只读查询 ✅ |
| **factory logs** | ❌ **不存在** | — | — | — | **缺口**(S10-026 只有 audit,无 logs) |
| factory demo | ✅ | ✅ | 0/1 | ❌ | init/status/reset ✅ |

## 2. 实测检查(S10-026 后状态)

```
exit code 约定: 0=成功(含WARN) / 1=失败阻塞 / 2=用法错误(未知命令/检查器/服务)
实测: doctor 无配置 → 1(FAIL 时);config set llm → 1(红线);unknown cmd → 2;rag → 0 ✅
help: 顶层 + 每子命令完整 ✅
```

## 3. JSON 输出能力(现状缺口)

| 命令 | 现状 | 未来标准建议 |
|---|---|---|
| doctor | ✅ --json | 已是标准 |
| status | ❌ | **factory status --json** → {backend, frontend, runtime, llm: {provider, model, configured}} |
| service list | ❌ | **factory service list --json** → [{id, state, pid, url}] |
| config show | ❌ | **factory config show --json** → {core: {...}, llm: {provider, model, configured}} |
| agent/task/audit | ❌ | --json 列表输出 |
| audit | ❌ | **factory audit --json** → {events: [...], counts: {...}} |

## 4. 未来 CLI 标准(设计)

### 4.1 全局 JSON 约定
```bash
factory status --json        # → {"backend": "running", "frontend": "stopped", ...}
factory doctor --json        # → {"checks": [...], "summary": {"pass": 5, "warn": 2, "fail": 0}}
factory config show --json   # → {"core": {...}, "llm": {"provider": "deepseek", "configured": false}}
```

### 4.2 用途(CI / 企业部署 / 自动化管理)
```
CI: factory doctor --json | jq '.summary.fail == 0'   # 健康门禁
部署: factory config set core.port 9000 && factory start
监控: factory status --json (轮询)
```

### 4.3 缺失命令建议
```
factory logs          # 查看后端/前端日志 (audit 是事件审计, logs 是运行日志 — 互补)
factory version       # 版本号 (配合 v1.0.0-rc1 tag)
factory llm list      # LLM 状态列表 (provider/model/key 状态) — 用户路径验收提到过
```

## 5. 无 UI 完整性评估

**核心结论:AI Factory 无 UI 时完整可用。**
- ✅ 全生命周期可 CLI 驱动:init → doctor → config → start → demo → agent/skill/task → audit
- ✅ 真实执行链路可 CLI 触发(exec CLI run / API;UI 只是控制面之一)
- ✅ 诊断/配置/服务管理全部 CLI 化
- ⚠️ 缺口:logs 命令缺失(运行日志查看需手动 tail /tmp/factory-*.log);JSON 输出仅 doctor 有

## 6. CLI 产品就绪评分

| 维度 | 评分 | 说明 |
|---|---|---|
| 命令覆盖 | 9/10 | 全生命周期覆盖;logs 缺失 |
| help/参数 | 9/10 | 完整 |
| 错误提示 | 9/10 | 红线/端口/环境清晰 |
| exit code | 9/10 | 0/1/2 统一 |
| JSON 输出 | 5/10 | 仅 doctor;其余待补 |
| 自动化能力 | 7/10 | --non-interactive 已有;JSON 补齐后 CI-ready |

**总分:8.0/10 — 无 UI 完整可用;JSON 标准化是 CI/企业部署前置。**

## 7. 建议(记录,不实现)

1. P1: factory logs(运行日志查看)+ factory version
2. P1: 全命令 --json 标准化(至少 status/service list/config show)
3. P2: 自动补全(bash/zsh 脚本 + --list-commands)
4. P2: exit code 约定文档化(cli_factory docstring)

---

> 审计完毕 | 只读 | CLI 无 UI 完整可用 8.0/10;JSON 标准化为下一阶段

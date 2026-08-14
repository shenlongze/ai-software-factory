# S10-027 Task 0 — Quality Baseline Freeze

> 日期:2026-08-14 | Sprint: S10-027 Hardening | 只读,未修改代码
> 目的:冻结 AI Factory v0.1 架构基线(能力建设阶段 → 平台化阶段的转折点)

---

## 1. 版本基线

- Git HEAD: 44626b2(S10-027 hardening audit)
- Git tag: **v1.0.0-rc1**(已存在)
- 里程碑:S10-021~024(LLM 基础设施)+ S10-026(产品入口)+ S10-027(hardening)

## 2. 测试状态(冻结基线)

```
pytest:  8116 passed, 0 failed    (181.70s, 2026-08-14 实测)
- 预存失败已清零(S10-027-E 修复 test_period_field_reflected 时间依赖 fixture)
- 全量全绿 = 测试体系可信
```

## 3. 核心模块健康状态

| 模块 | 状态 | 证据 |
|---|---|---|
| Provider (LLMControlPlane) | 🟢 GREEN | providers.json 持久化/api_key_ref/生命周期;S10-021 ✅ |
| Model Catalog | 🟢 GREEN | models.json/ModelChoice/suggest;S10-022 ✅ |
| LLM Execution | 🟢 GREEN | 真实 DeepSeek 调用闭环($0.000278);S10-023 ✅ |
| Router | 🟢 GREEN | 五层决策链;S10-024 ✅ |
| CLI | 🟢 GREEN | 15+ 命令/唯一入口/doctor/config/service/demo;S10-026 ✅ |
| Runtime | 🟢 GREEN | ServiceDef 注册表/start 兼容;S10-026-B ✅ |

**全部 6 模块 GREEN — 无红灯阻塞。**

## 4. 已完成能力清单

### LLM 基础设施
- Control Plane:providers.json / api_key_ref(env 引用,禁明文)/ 启停 / 配置校验
- Model Catalog:Provider→Model 两级 / capabilities / context_window / cost / enabled
- Real Execution:Task→Planner→Runtime→Provider→Artifact→Audit→Usage 真实闭环
- Router v1.1:User > Agent/Skill > Project > System > Fallback 五层链;ModelChoice 输出;router.decided 审计

### 产品入口(S10-026)
- CLI 唯一入口 ./bin/factory(15+ 命令)
- init(引导)/ doctor(诊断)/ config(运行时配置)/ start(Runtime Manager)/ service / demo(隔离 workspace)
- 命令组骨架:agent / skill / task / router / rag / audit
- DoctorCheck / ServiceDef 可扩展协议

## 5. 技术债清单(冻结时点)

### P0(发布阻塞)
| # | 债 | 说明 |
|---|---|---|
| 1 | **release packaging** | 私有仓库;无 tarball/pipx;外部用户无法安装 |
| 2 | **installation experience** | setup.sh 依赖 Node;npm 无重试;README 首次指引脱节 |
| 3 | **CLI 完整度** | 3 入口未完全统一;project/run 未转正;自动补全未实现 |

### P1(演进必需)
| # | 债 | 说明 |
|---|---|---|
| 1 | **time abstraction** | 测试曾暴露时间依赖(已修 fixture);业务代码时间口径待统一 |
| 2 | **plugin architecture** | 模块耦合点已识别(见 S10-027-module-boundary.md);插件化待设计 |
| 3 | **event/audit 统一** | exec usage 与 factory-core UsageStore 双轨;org.execution 与 session 事件未合并 |

### P2(远期)
| # | 债 | 说明 |
|---|---|---|
| 1 | UI 产品化 | 17 页面可用但执行触发/配置 UI 未接 |
| 2 | marketplace | Skill/Plugin 市场(远期) |

## 6. 冻结声明

本基线为 **AI Factory v0.1**(tag v1.0.0-rc1 对应代码)。
后续任何演进(S10-028+)必须:
1. 不破坏 8116 全绿基线(每 Task 全量回归门)
2. 不修改已冻结的 AgentRuntime/Router 决策算法/Provider 核心
3. 架构变更先过 Design Review(本 Sprint 的边界/插件/配置文档为参考)

---

> 基线冻结完成 | 只读 | v1.0.0-rc1 / 8116 passed / 6 模块 GREEN

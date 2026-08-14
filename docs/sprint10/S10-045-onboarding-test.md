# S10-045 Task 002 — Real User Onboarding Simulation

> 日期:2026-08-14 | Sprint: S10-045 | 模拟 GitHub 首访用户视角(结合 S10-043 真实模拟)
> 目标: 记录每一步的疑问/价值感/放弃点

---

## 1. 模拟流程

```
README → install → init → doctor → demo run → run objective → artifact
```

## 2. 逐步记录

### README(0-2 分钟)

| 项 | 用户视角 | 价值感/疑问 |
|---|---|---|
| 首屏定位 | "AI Workforce Operating System" + 痛点表格 | ✅ 价值感(不可控/无审计/成本失控是真实痛点) |
| 核心能力 | 7 项能力表 | ✅ 清晰 |
| Roadmap 诚实区分 | Implemented/Future | ✅ 信任感 |
| 疑问 | "它和 Cursor 比怎样?" | ⚠️ 差异化在 5-minute-demo 里不够突出 |

### install(2-3 分钟)

| 项 | 用户视角 | 价值感/疑问 |
|---|---|---|
| git clone + setup.sh | 一键脚本 | ✅ 顺畅 |
| 疑问 | "为什么不是 pip install?" | ⚠️ PyPI 未发布(README 标"即将支持") |

### init + doctor(3-5 分钟)

| 项 | 用户视角 | 价值感/疑问 |
|---|---|---|
| init --provider deepseek | 3 ✓ 引导 | ✅ 清晰 |
| export key | 环境变量 | ⚠️ 非技术用户疑问(文档有解释) |
| doctor | PASS/WARN | ✅ 诊断专业感 |

### demo run(5-7 分钟)— 核心

| 项 | 用户视角 | 价值感/疑问 |
|---|---|---|
| 一条命令 | "就这么简单?" | ✅ **高价值感(首次冲击)** |
| 真实执行 41s | 看到 usage/cost | ✅ **价值感峰值(真实+成本可见)** |
| result-id + 下一步 | 知道结果在哪 | ✅ 闭环 |

### run objective(7-9 分钟)

| 项 | 用户视角 | 价值感/疑问 |
|---|---|---|
| --objective 自然语言 | "不用记 task ID" | ✅ 顺畅 |
| 疑问 | "agent backend-1 是什么?" | ⚠️ 需 factory agent 查(文档有) |

### artifact(9-10 分钟)

| 项 | 用户视角 | 价值感/疑问 |
|---|---|---|
| patch/报告/成本 | 完整产物 | ✅ 价值感延续 |
| 疑问 | "diff 展示在哪?" | ⚠️ 当前无代码 diff 预览(纯路径) |

## 3. 每步评分

| 步骤 | 疑问 | 价值感 | 放弃风险 |
|---|---|---|---|
| README | 低 | 高 | 低 |
| install | 中(PyPI 缺失) | 中 | 中(嫌麻烦者弃) |
| init/doctor | 低 | 中 | 低 |
| **demo run** | **低** | **高(峰值)** | **低** |
| run objective | 中(agent 概念) | 高 | 低 |
| artifact | 中(无 diff) | 中 | 低 |

## 4. 关键发现

### 价值感峰值(保留)
- **demo run 一条命令 + 真实执行 + 成本可见** = 最强价值瞬间(41 秒)

### 放弃点(需优化)
| # | 放弃点 | 严重度 |
|---|---|---|
| D1 | 非 pip 安装(PyPI 未发布)→ 怕麻烦的用户放弃 | 中 |
| D2 | "和 Cursor 什么区别" 未在首屏直接回答 | 中 |
| D3 | artifact 无 diff 预览(看不到 AI 改了什么) | 中 |
| D4 | agent/provider 概念需查文档 | 低 |

## 5. 结论

**Onboarding 模拟: 价值感曲线健康(README→demo run 峰值→artifact 延续), 放弃风险集中在安装方式(PyPI)与差异化澄清。**

- 核心体验(demo run)已验证能产生价值感
- 3 个优化点: PyPI 发布 / 首屏差异化对比 / diff 预览

---

> Task 002 完毕 | 价值感峰值: demo run | 放弃点: PyPI 缺失 + 差异化澄清 + diff 预览

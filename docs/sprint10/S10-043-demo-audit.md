# S10-043 Task 003 — Demo Experience Audit

> 日期:2026-08-14 | Sprint: S10-043 | 基于真实 demo run 执行

---

## 1. 当前流程

```
用户输入一句话 (factory demo run "给 main.py 加 hello")
  ↓
AI 执行 (workspace → 项目 → Router → LLM → patch)
  ↓
Artifact (status/usage/patch/report)
```

## 2. Wow moment 分析

| 环节 | 当前表现 | 是否形成冲击 |
|---|---|---|
| 一句话输入 | ✅ 简单 | 无冲击(用户不知会发生什么) |
| AI 执行 | ✅ 41.8s 真实执行 | 弱(等待中无过程展示) |
| 结果展示 | ⚠️ status + usage | **中(看到 success + tokens 有冲击, 但缺代码 diff)** |
| Artifact | ⚠️ patch 路径(但目录被清理) | 弱(用户看不到实际代码改动) |

**Wow moment 现状: 部分成立(执行成功 + 成本可见), 但缺"看到 AI 改的代码"环节。**

## 3. 缺口

| # | 缺口 | 影响 |
|---|---|---|
| W1 | 等待中无过程反馈(41.8s 黑盒) | 用户焦虑, 以为卡住 |
| W2 | 结果无代码 diff 展示 | 错过核心冲击("AI 真的改了代码!") |
| W3 | 临时目录清理 → 无法查看实际产物 | 冲击减半 |
| W4 | 失败无原因(无 key 时) | 负面体验 > 无体验 |

## 4. v0.2 Demo 改进建议

### A. 过程可见(消除 W1)

```
demo run 执行中打印阶段:
  [1/5] workspace 就绪
  [2/5] 项目创建
  [3/5] Router 决策: deepseek (reason: 能力匹配)
  [4/5] LLM 执行中...
  [5/5] 验证 + 产物生成
```

### B. 代码 diff 展示(消除 W2, 核心 Wow)

```
执行完成后打印 patch 摘要 (前 20 行 diff):
  --- main.py (before)
  +++ main.py (after)
  + def hello():
  +     print("Hello, world!")
```

### C. 产物保留 + 一键查看(消除 W3)

```
--no-cleanup 默认开? 或:
  成功时提示: "查看改动: factory demo show --id EXS-xxx"
  保留 artifact 目录 (~/.factory-demo/exec/ 已在, 只是临时项目目录被清)
```

### D. 失败原因可见(消除 W4)

```
demo run 失败时:
  ✗ 执行失败: provider error — anthropic api key missing
  提示: export DEEPSEEK_API_KEY=... 后重试
```

### E. 增强叙事(可选)

```
完成时:
  "✔ 完成! AI 员工 backend-1 用 41 秒写好了代码, 成本 $0.0015。
   你在管理一支 AI 团队 — 这就是 AI Workforce Operating System。"
```

## 5. 结论

**Wow moment 已部分形成(真实执行 + 成本可见), 但"看到 AI 改的代码"是缺失的核心冲击。**

v0.2 优先级:
1. **代码 diff 展示**(W2)— 核心 Wow
2. **失败原因可见**(W4)— 防流失
3. **过程阶段反馈**(W1)— 消除焦虑
4. **产物一键查看**(W3)— 闭环

---

> Task 003 完毕 | Wow moment 部分成立 | v0.2 建议: diff 展示 + 失败原因 + 过程反馈

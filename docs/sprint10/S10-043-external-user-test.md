# S10-043 Task 001 — External User Simulation

> 日期:2026-08-14 | Sprint: S10-043 User Validation | 真实陌生用户模拟(全新 venv + 全新 HOME)
> 目标: 记录陌生用户从安装到第一次任务的真实体验问题

---

## 1. 模拟环境

```
全新 venv: python3.12 -m venv (无任何预装包)
全新 HOME: /tmp/s10043-user (无 .factory 历史)
安装: pip install -e . (源码, 模拟陌生用户)
无上下文: 无历史 session/配置
```

## 2. 执行记录

| 步骤 | 命令 | 结果 | 用户视角 |
|---|---|---|---|
| 1. 安装 | pip install -e . | ✅ | 顺畅 |
| 2. 首命令 | factory --help | ⚠️ 描述过时 | 看到 "S10-007 阶段二 CLI MVP"(技术味) |
| 3. init | factory init --non-interactive --provider deepseek | ✅ | 3 ✓ + key 警告, 清晰 |
| 4. doctor | factory doctor | ✅ 1 PASS / 4 WARN | WARN 有提示 |
| 5. demo run(无 key) | factory demo run "做一个 todo 应用" | ⚠️ **status failed 无原因** | 用户不知为何失败! |
| 6. 配置 key | export DEEPSEEK_API_KEY | ✅ | 需要用户知道环境变量 |
| 7. demo run(有 key) | factory demo run "给 main.py 加 hello" | ✅ success 41.8s | Wow moment |
| 8. 找回结果 | factory run-status --id | ⚠️ 需 ID | demo run 清理了目录, 不知结果存哪 |

## 3. 用户遇到的疑惑/障碍

| # | 问题 | 类型 | 严重度 |
|---|---|---|---|
| P1 | **--help 描述过时**("S10-007 阶段二 CLI MVP") | 文档缺口 | 低 |
| P2 | **demo run 失败时不显示原因**(无 key 时 status failed, 无错误消息) | UX 缺口 | **中** |
| P3 | **demo run 成功后临时目录被清理**, 用户不知 artifact 在哪 | UX 缺口 | **中** |
| P4 | key 配置依赖用户懂"环境变量"概念 | 概念障碍 | 低 |
| P5 | run-status 需手动复制 result-id | 体验摩擦 | 低 |

## 4. 概念障碍

| 概念 | 用户困惑 |
|---|---|
| provider | init --provider deepseek 需知道服务商名(文档有列) |
| agent | run --agent backend-1 需知道有哪些 agent(agent 命令可查) |
| env key | "export DEEPSEEK_API_KEY" 非技术用户不懂 |
| task/objective | S10-042 已解决(--objective) |

## 5. 文档缺口

| 缺口 | 建议 |
|---|---|
| --help 定位过时 | 更新为 "AI Workforce Operating System" |
| 失败原因不显示 | demo run 失败时打印底层错误 |
| 结果去向不提示 | demo run 成功提示 "查看: factory run-status --id <ID>" 且保留 ID |
| 无 key 引导 | init 后补 "下一步: export key + demo run" |

## 6. 结论

**陌生用户可完成首次任务(约 2 分钟), 但 3 个 UX 缺口:**
1. demo run 失败无原因(P2, 中)— 用户会卡在"为什么失败"
2. demo run 成功但结果去向不明(P3, 中)— 用户看不到"我得到了什么"
3. --help 描述过时(P1, 低)

**核心成功路径已验证: 安装 → init → key → demo run → success(41.8s)。**

---

> Task 001 完毕 | 真实模拟 | 成功路径通 | 3 个 UX 缺口(2 中 1 低)

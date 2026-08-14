# Use Cases Validation — AI Factory as Entry Point

> 位置: docs/product/use-cases-validation.md | Sprint: S10-045 | 5 个真实开发场景验证

---

## 场景 1: 修改已有项目代码

| 项 | 内容 |
|---|---|
| 用户 | Developer |
| 动作 | `factory run --project ~/my-app --objective "给 main.py 加一个乘法函数"` |
| 当前支持 | ✅ 真实执行 + patch 产物 |
| 价值 | 中高(改小需求快; 大需求需多次迭代) |
| 缺口 | diff 预览、迭代对话(改→看→再改) |
| **作为入口** | ✅ 适合(日常小改动) |

## 场景 2: 生成测试

| 项 | 内容 |
|---|---|
| 用户 | Developer / QA |
| 动作 | `factory run --objective "为 main.py 生成单元测试" --test-cmd pytest` |
| 当前支持 | ✅ 执行链含 test_result 产物 + 验证门 |
| 价值 | 高(测试是 AI 擅长+可验证) |
| 缺口 | 测试运行集成(--test-cmd 需手动传) |
| **作为入口** | ⭐ **最适合**(产出可验证, AI Factory 验证门价值凸显) |

## 场景 3: 代码分析

| 项 | 内容 |
|---|---|
| 用户 | Developer / AI Engineer |
| 动作 | `factory run --objective "分析 main.py 的复杂度与问题"` |
| 当前支持 | ✅ 可执行(LLM 分析 + 报告产物) |
| 价值 | 中(报告型任务, 一次性) |
| 缺口 | 项目级 RAG(需理解全仓库)— v0.3 |
| **作为入口** | ⚠️ 一般(单文件可; 全仓分析需 RAG) |

## 场景 4: 项目维护

| 项 | 内容 |
|---|---|
| 用户 | Developer / Startup |
| 动作 | `factory run --objective "升级依赖并修复兼容问题"` |
| 当前支持 | ⚠️ 可执行但依赖环境/沙箱完整性 |
| 价值 | 中(维护任务复杂, 需上下文) |
| 缺口 | 项目上下文(Memory/Experience)— v0.3 |
| **作为入口** | ⚠️ 中等(简单维护可; 复杂需上下文) |

## 场景 5: 自动化任务

| 项 | 内容 |
|---|---|
| 用户 | Startup / AI Engineer |
| 动作 | CLI 脚本化: `factory run --objective "..." --json` + cron |
| 当前支持 | ✅ CLI 可脚本化 + JSON 输出(doctor) |
| 价值 | 高(平台化价值: 定时 AI 任务) |
| 缺口 | run --json 输出、定时调度(远期) |
| **作为入口** | ⭐ **高潜力**(平台自动化) |

## 汇总矩阵

| 场景 | 当前支持 | 价值 | 入口适合度 | 依赖 |
|---|---|---|---|---|
| 1 修改代码 | ✅ | 中高 | ✅ | diff/迭代 |
| 2 生成测试 | ✅ | 高 | ⭐ | test-cmd 集成 |
| 3 代码分析 | ✅ | 中 | ⚠️ | RAG (v0.3) |
| 4 项目维护 | ⚠️ | 中 | ⚠️ | Memory (v0.3) |
| 5 自动化任务 | ✅ | 高 | ⭐ | run --json |

## 结论

**AI Factory 作为入口最适合: ① 生成测试(可验证) ② 自动化任务(可脚本化) ③ 修改代码(日常)。**

- 短任务(测试/小改)价值最高 — 立即验证
- 长任务(分析/维护)需 RAG/Memory — v0.3
- 种子用户首推场景: **生成测试 + 修改代码**

---

> Task 003 完毕 | 5 场景验证 | 最佳入口: 生成测试 + 自动化 + 小改 | RAG/Memory 是长任务关键

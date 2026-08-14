# S10-035 Task 003 — CLI Product Review

> 日期:2026-08-14 | Sprint: S10-035 | 真实执行审查(未修改代码)
> 目标: 检查 CLI 的 help/错误/exit code/JSON 能力

---

## 1. 命令存在性(实测 exit code)

| 命令 | --help exit | 状态 |
|---|---|---|
| factory --help | 0 | ✅ |
| factory doctor | 0 | ✅ |
| factory init | 0 | ✅ |
| factory config | 0 | ✅ |
| factory project | 0 | ✅ |
| factory run | 0 | ✅ |
| factory agent | 0 | ✅ |
| factory skill | 0 | ✅ |
| factory router | 0 | ✅ |
| factory rag | 0 | ✅ |
| factory audit | 0 | ✅ |
| factory demo | 0 | ✅ |

## 2. exit code 约定(实测)

| 场景 | exit code | 正确性 |
|---|---|---|
| 成功(含 WARN) | 0 | ✅ |
| 失败/阻塞 | 1 | ✅ |
| 用法错误(未知命令/缺参数) | 2 | ✅ |
| 未知命令 nonexistent | 2 | ✅ |

## 3. 错误提示(实测)

| 场景 | 提示 | 质量 |
|---|---|---|
| run 缺 --task | `错误: --task 必填 (任务 ID)` | ✅ 明确 |
| config set llm.provider | `拒绝写入 llm.provider: config.json 只存运行时配置 (红线 ①)...` | ✅ 清晰+指引 |
| doctor 无 provider | `WARN: enabled provider 缺少 API key: deepseek — 请配置 api_key_ref` | ✅ 可操作 |

## 4. JSON 输出能力

| 命令 | JSON | 状态 |
|---|---|---|
| doctor --json | ✅ 结构化 {checks, summary} | ✅ |
| 其他命令 | ❌ 无 --json | ⚠️ 待增强(非阻塞) |

## 5. help 完整性

- 顶层 --help: 全部命令 + description ✅
- 子命令 --help: 参数说明完整 ✅
- rag 明确占位("RAG 未实现 — 规划中") ✅

## 6. 发现的问题

| # | 问题 | 严重度 | 建议 |
|---|---|---|---|
| 1 | 仅 doctor 支持 --json | 低 | status/service list 等加 --json(CI 友好, 后续) |
| 2 | 命令数 17+(含骨架) | 低 | 骨架命令(agent/skill 等)是只读, 合理 |
| 3 | 无 factory logs 命令 | 低 | audit 已有; logs 可后续 |

**无阻塞问题。**

## 7. 结论

**CLI 产品就绪: 高。** 全部命令可用、exit code 规范(0/1/2)、错误提示清晰、doctor --json 支持。
唯一增强项(JSON 扩展)非阻塞。

---

> Task 003 完毕 | CLI 审查通过 | 无阻塞 | JSON 扩展为可选增强

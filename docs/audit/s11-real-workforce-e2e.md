# S11 Real Workforce E2E — 真实 LLM + Codex + pytest 全链证据

> 日期: 2026-08-29 | 执行: run_real_workforce_e2e (真实外部依赖)

## 结果
**REAL E2E: PASS** — Idea → PM → PRD → Architect → Architecture → Developer → Code → QA → pytest 全链真实 COMPLETED。

```
state: COMPLETED | engines: {pm: real-llm, architect: real-llm, developer: real-codex, qa: real-llm+pytest}
handoffs: 3 | final_artifacts: 1
```

## Environment
| 项 | 值 |
|----|-----|
| LLM Provider | deepseek (deepseek-v4-pro) |
| LLM API | https://api.deepseek.com/v1/chat/completions (key 经 env 注入) |
| Codex | codex-cli 0.147.0 |
| Python | 3.12.13 |
| pytest | 项目 venv (sys.executable 修正) |
| Git | HEAD 提交 (S11) |

## Execution (逐 Agent)
| Agent | 引擎 | Artifact | Verification | 状态 |
|-------|------|----------|--------------|------|
| product_manager | REAL LLM | PRD (## Problem/Target Users/Goals/... 中文输出) | 专业验收 (宽松中英匹配) | COMPLETED |
| software_architect | REAL LLM | Architecture (SPA/本地存储) | 专业验收 | COMPLETED |
| software_developer | REAL Codex | calculator 代码 (add/subtract + CLI main) | 语法验证 (2 次尝试) | COMPLETED |
| qa_engineer | REAL LLM 测试 + REAL pytest | test_app.py (`from app import add, subtract`) | pytest exit_code=0 | COMPLETED |

## 关键修复 (S11)
1. verify_pytest 用 sys.executable (factory-venv 无 pytest)
2. Node verification result 兼容 pytest 的 status 字段
3. QA prompt 显式模块名 (app) — 防 LLM 写 `your_module` 占位符
4. 专业验收宽松匹配 (中英文标题) — 防 LLM 格式漂移
5. Codex 输出提取: markdown 围栏 + 无围栏裁剪 + 2 次尝试

## 诚实状态
| 能力 | 状态 |
|------|------|
| PM 真实 LLM | REAL |
| Architect 真实 LLM | REAL |
| Developer 真实 Codex | REAL |
| QA 真实 pytest | REAL |
| 真实全链一次跑通 | PASS (第 3 次尝试, 前 2 次分别卡 Architect 格式/codex 杂质) |
| QA 真实 pytest 失败→Repair→PASS 全自动 | SEMI (Repair 机制已测, 真实全链未触发 repair) |

# FACT DISCOVERY STEP 2 — 最终覆盖率 (2026-09-02)

## Repository Coverage

| 区域 | 状态 |
|------|------|
| factory-console | PARTIALLY_SCANNED (API 371 全量/LLM/入口/存储; 268 py 未逐文件) |
| factory-org | SCANNED (69 import 点确认; management/projects 前几轮深度) |
| factory-core | PARTIALLY_SCANNED (清单+CLI+零 console import; 内部逐模块未读) |
| factory-exec | SCANNED (52 模块 docstring 全清单 + console 集成点 6 处) |
| factory-runtime | PARTIALLY_SCANNED (清单; 内部未读) |
| tests | SCANNED (34 分组; 未逐测试) |
| docs | NOT_SCANNED (仅目录) |
| WebUI | NOT_SCANNED |
| desktop | NOT_SCANNED |
| examples/projects/workspace/exec | NOT_SCANNED |

## STEP 1 → STEP 2 验证结果

| FACT | STEP 1 | STEP 2 最终 |
|------|--------|-------------|
| F-1 runtime loads console+org | 假设 | CONFIRMED (create_app + org 69 import) |
| F-2 371 endpoints | 提取 | CONFIRMED (静态); 运行时行为 UNKNOWN |
| F-3 zero import | 声称 | **PARTIALLY REFUTED** (console→exec 6 延迟导入) |
| F-4 154 direct LLM | 声称 | **REFUTED (方法缺陷)** — llm_fn 是统一注入入口; LLMRouter 消费=0 |
| F-5 console imports org | 假设 | CONFIRMED (69 处) |
| F-6 three execution systems | 假设 | CONFIRMED (会话链/M3/exec) |
| F-7 Requirement no persistence | 声称 | **PARTIALLY REFUTED** — requirements.json 存在 (agent_loop:795); 分析报告不落盘 |
| F-8 dual CLI | 假设 | CONFIRMED (实际 4 条: console/core/exec/runtime) |

## 本阶段新发现事实

| 事实 | 证据 |
|------|------|
| console→exec 延迟集成 (Removal Isolation) | service.py:376-445 |
| LLMRouter 生产消费 = 0 | grep LLMRouter(/.route 0 处 (非定义文件) |
| llm_fn 全注入 (统一入口) | console_sessions.py:104 + 抽样 3 文件全 llm_fn |
| factory-exec = 完整 AI 员工系统 (7 类 Agent) | exec/developer.py+pm.py+architect.py+tester.py+release.py+uxui.py |
| requirements.json 落盘实体 | agent_loop.py:795-803 + fastapi:1501-1504 |
| exec 包名 ≠ factory_exec (STEP 1 扫描缺陷根因) | service.py:412 `from exec import` |

## 未验证事实 (UNKNOWN)

| 事实 | 原因 |
|------|------|
| factory-core 内部行为 | 未逐模块读 |
| factory-exec 与 gateway/production_run 是否重复 | 未逐调用链 |
| LLMRouter 是否死代码 | 无消费方, 未验证运行时引用 |
| PRD 结构化实体 | 未定位 |
| Release/Learning 持久化 | 未定位 |
| WebUI 状态 | 未扫描 |
| 371 端点运行时行为 | 未逐端点 |

## 覆盖率总结

SCANNED: org, exec(模块级), API(静态), LLM(分类)
PARTIALLY_SCANNED: console, core, runtime, tests, package 依赖
NOT_SCANNED: docs 全文, WebUI, desktop, examples, 数据目录
UNKNOWN: 大量运行时行为

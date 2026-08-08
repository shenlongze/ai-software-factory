# S7-004 — Tester Agent（Completion Report）

> 日期: 2026-08-08 | 状态: 完成 | pytest 5988 (5919 + 69)
> 目标: Tester 角色可执行 + 接入 Workflow Runner (Dev↔Tester Loop)

## 实现概述

```
Tester 从 planning → executable:
  确定性测试执行 (复用验证循环, 不靠 LLM 猜)
  + LLM 失败分析 (v4-pro) → bug_report → repair task → 回 Developer
  Dev↔Tester Loop ≤2 轮 (计数保护, 禁无限)
```

## 新增文件

```
factory-exec/exec/tester.py          (BugReport/TestRunResult/TesterAgent + workflow 适配器)
tests/exec/test_exec_tester.py       (36 测试)
tests/s7/test_s7_tester_role.py      (20 测试)
tests/s7/test_s7_devtest_loop.py     (16 测试)
docs/sprint7/implementation/S7-004-report.md (本报告)
```

## 修改文件

```
factory-exec/exec/roles.py           (Tester execution_kind: planning→executable + prompt 模板)
factory-org/org/projects.py          (ArtifactType.BUG_REPORT 枚举)
factory-org/org/artifact.py          (CONTRACTS bug_report 6 字段 + required_keys 规则)
factory-org/org/workflow.py          (build_dev_test_workflow + DevTestLoopRunner ≤2 轮)
tests 既有 4 文件                    (对齐真实契约)
```

## 执行链

```
Developer Artifact → TesterAgent:
  test (沙箱内确定性执行) → 失败 → LLM 失败分析 (v4-pro, mock 测试)
  → bug_report artifact (location/repro/expected/actual/root_cause/severity)
  → repair task 回传 → Developer 修 → 重测
  ≤2 轮; 3 轮停止 FAILED; 通过 → 下一阶段 (release 前置)
```

## Tester Prompt（要点）

```
运行测试 → 分类失败 (逻辑/边界/接口/缺失) → 结构化 bug report
→ 生成 repair task (附上下文) — 确定性执行 + LLM 分析分工
```

## 测试结果

```
pytest 全量: 5988 passed, 0 failed
S7-004 相关 7 文件: 145 passed
修复记录: __pycache__ 陈旧字节码 (rmtree 清缓存) + 断言/夹具对齐 + 枚举计数对齐
Core/Runtime/Desktop/Console diff = 0 (events 未动)
```

## 下一步 (S7-005)

```
Workflow 全链演示: PM→Arch→Dev→Test (Tester 已就绪) → Release
真实小项目: 全链自动执行 + 产物 + 证据
```

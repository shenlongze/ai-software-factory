# K2 真实 LLM E2E 证据

> 日期: 2026-08-29 | HEAD: 1ca28bc3 (v1.1.354)

## 1. 全链真实执行 (非 mock)
```
Conversation「我想做一个计算器工具」→「目标用户是个人用户」
→ Requirement (req_ 实体)
→ Task Tree 分解 (5 子任务, 串行依赖)
→ 真实 executor (build_real_executor_factory)
    - software_developer: codex 真实生成 Python 代码
    - 内置 pytest 真实运行 (BUILTIN_CALC_TESTS)
→ 5/5 子任务 COMPLETED
→ Control Tower: {'COMPLETED': 5} (真实投影)
```

## 2. 真实 LLM 调用证据
- codex 生成代码含 add/subtract/multiply/divide + 除零 ValueError
- 真实 pytest 输出: `..FFF`(修复前)→ 全过(修复后)
- 产物 calculator.py 真实写入(验证后清理)

## 3. 真实 E2E 发现的缺口 (已修)
| 缺口 | 根因 | 修复 |
|------|------|------|
| role 提取错误 | split("-")[-2] 取错段 | →[-1] (node_id 'dev-software_developer' 正确路由) |
| prompt 与测试不一致 | prompt 只要求 add/subtract, 测试要 4 函数 | → 4 函数 + 除零要求 |
| task_tree node 无 role 段 | 真实 factory 无法路由 | → 默认 node_id 带 role |

## 4. 诚实结论
- **K2 Conversation→Workforce→Task Tree→Execution→Verification→Result 真实闭环 PASS**
- 通用任务泛化 (非计算器) = 遗留 GAP (prompt 仍硬编码计算器, 记录不膨胀)

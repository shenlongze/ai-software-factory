# Debug 全链路审计

> 代码事实扫描 (2026-08-17)

## 一、Debug 闭环逐环节检查

```
失败 → 错误理解 → 分类 → Root Cause → Retrieval → 历史经验 → 策略选择
→ Patch → 真实执行 → 测试 → 失败? → 策略调整 → 再次修复 → 成功
→ Learning → Audit
```

| 环节 | 状态 | 证据 |
|---|---|---|
| 失败捕获 | ✅ | DebugSession.start / debug_analyze 最近失败 |
| 错误理解 | ✅ | ErrorAnalyzer (9 类分类) |
| Root Cause | ✅ | RootCauseAnalyzer (9 类根因 + evidence + confidence) |
| Retrieval | ✅ | DebugExperienceRetriever (Top-K + 排序) |
| 历史经验 | ✅ | Memory DEBUG/FAILURE/SUCCESS 经验 |
| 策略选择 | ✅ | DebugStrategySelector (7 规则) |
| Patch 生成 | ⚠️ | 策略生成, 无真实代码 patch |
| 真实执行 | ❌ | execute_fn 默认确定性桩 (RepairManager 桥存在, 默认不用) |
| 真实测试 | ❌ | 无 subprocess pytest (validator 注入) |
| 策略调整 | ✅ | StrategyAdapter (strategy_history 排除已失败) |
| 再次修复 | ✅ | Pipeline.run 循环 (max_attempts) |
| 成功判定 | ⚠️ | 注入 result="success" (非真实 pytest PASS) |
| Learning | ✅ | feedback → SUCCESS/FAILURE_PATTERN |
| Audit | ✅ | DEBUG_STARTED 自动 emit (5 事件之一) |
| Governance | ✅ | RepairSafety (AUTO/SAFE_AUTO/REVIEW/BLOCKED) |

## 二、特别检查回答

| 检查项 | 答案 | 证据 |
|---|---|---|
| execute_fn 是否只是测试注入? | **是 (P0-1)** | 默认确定性桩, 真实 RepairManager 桥需显式传 |
| validation 是否真实运行 pytest/build? | **否 (P0-2)** | 无 subprocess; validator 注入 |
| patch 是否真实写入工作区? | **否** | 无文件写入逻辑 |
| 是否读取真实 traceback? | ⚠️ 部分 | error_message 传入, 无 stack_trace 解析 |
| 是否读取真实代码上下文? | **否** | 无代码读取 |
| 是否能定位文件/函数? | **否** | 无文件定位 |
| 是否支持多轮修复? | ✅ | Pipeline.run (max_attempts=3) |
| 是否有最大修复次数? | ✅ | max_attempts + RepairSafety |
| 是否受 Budget 控制? | ✅ | RepairSafety (BudgetEnforcer) |
| 是否受 Governance 控制? | ✅ | LoopGuard/Policy/ReviewGate |
| 是否 Audit? | ⚠️ 部分 | DEBUG_STARTED 自动; REPAIR_* 未全 |
| 是否 Memory? | ✅ | feedback → ExperienceStore |
| 是否能学习失败策略? | ✅ | strategy_history → 全败 REQUEST_REVIEW |

## 三、结论

Debug **分析层完整且真实** (分类/根因/经验/策略/适应/治理);
**执行层为桩** (修复/验证) — P0-1/P0-2 是最大缺口, 决定"自主修复"真实性。

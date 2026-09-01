# P0 Execution Truth Claim Gap — Audit

> 日期: 2026-09-01 | 状态: P0 OPEN (等 FIX 指令)

## 1. 事实复现 (REAL PROJECT E2E 真实数据)

```
用户: "请把计划拆解成具体的开发任务...并创建到任务列表"
AI:   "我已经把开发计划拆解成 6 个具体任务并创建到任务列表里了"
事实: backlog/task.json 只有 1 个任务 (TASK-f5fa66ab 计划任务本身)
      声称的 6 个任务实际 0 个
      tool_calls = 0, 消息 meta 空
      project lifecycle = idea (execute_plan 未发生)
```

## 2. Root Cause (代码级)

### 2.1 为什么 validator 没拦

`execution_truth.py:29-58 CLAIM_PATTERNS["task"]` 覆盖不足:

```python
"task": [
    r"(任务|开发|功能|工作)已(完成|全部完成)",
    r"已(完成|交付)(开发|任务|功能)",
    r"全部完成",
],
```

消息 "我已经把开发计划**拆解成 6 个具体任务并创建到任务列表里了**":
- file 模式要求 "(已|已经)(创建|建立|生成)(了)?" 前缀 — 文本是 "**并创建到**任务列表", 无 "已" 前缀 → 不匹配
- task 模式要求 "任务已完成" — 文本是 "拆解成 6 个具体任务并创建" → 不匹配
- **claims = [] → validate_execution_claims 直接 ALLOW (line 118-120)**

### 2.2 深层问题 (不只 regex)

即使模式匹配, validator 也只检查 "有没有工具调用" (zero_tool_call → BLOCK),
**不校验数量声称**:
- 声称 "创建 6 个" → 实际创建 3 个 → validator 会放行 (有 tool_call)
- 用户要求: claimed_count 必须与 actual_count 比对 (不变量 1/4)

### 2.3 出口矩阵 (validator 覆盖)

| 出口 | 路径 | Validator |
| --- | --- | --- |
| SSE streaming | run_agent_native (7011) | ✅ 1967/2163 |
| company sync 兜底 | run_agent_native (7742) | ✅ 同 agent_loop |
| project sync | run_agent v1 + sanitize | ✅ _strip_fake_tool_calls |
| conversation_os | _co.send_message (6113) | ❌ 旧组件独立 |

本次请求走 company 兜底 → run_agent_native → validator 集成存在,
但 **CLAIM_PATTERNS 漏配 → claims=[] → ALLOW**。

## 3. 为什么 tool_calls=0

run_agent_native 第一轮 LLM 直接返回自然语言 (无工具调用意图),
intent 路由未把 "拆解成任务" 路由到 execute_plan/plan_development,
LLM 自由声称完成 → validator 因模式漏配放行 → 落库。

## 4. Contract 缺口

- CLAIM_PATTERNS 未覆盖 "拆解成 N 个任务并创建" 类完成态声称
- 无数量型声称事实校验 (claimed N vs actual M)
- Validator 是 "声称+调用存在性" 检查, 非 "声称 ↔ Domain Fact" 比对

## 5. 最小修复方案 (等 FIX 指令)

1. **CLAIM_PATTERNS["task"] 扩展**: 覆盖 "创建/拆解/生成 N 个任务/任务列表" 完成态
   (含无 "已" 前缀的 "并创建到任务列表里了")
2. **数量型事实校验**: validate_execution_claims 增加 actual_count 参数
   (来自真实 backlog 查询); claimed N vs actual M:
   - N == M → SUCCESS
   - 0 < M < N → PARTIAL (降级表述)
   - M == 0 → NOT_EXECUTED (BLOCK)
3. **agent_loop 集成**: 1967/2163 调用时传入 backlog 实际任务计数
   (service 可查 — 事实来自 Domain Store, 非 LLM 自报)
4. **保留**: zero_tool_call → BLOCK 已有逻辑 (模式匹配后生效)

## 6. 影响

用户被系统性误导 (UI 显示成功创建, 实际 0)。P0-001 核心场景 (LLM 声称执行 ≠ 实际执行) 在真实链上复现, 因模式漏配绕过。

## 7. 测试计划

- P0-01: 声称创建 6 + 实际 0 → BLOCK/NOT_EXECUTED
- P0-02: 声称 6 + 实际 3 → PARTIAL 降级
- P0-03: 声称 6 + 实际 6 → SUCCESS
- P0-04: 无声称普通回答 → ALLOW
- P0-05~12: 出口矩阵回归 (sync/SSE/fallback/stop/部分失败)

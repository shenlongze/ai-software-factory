# S10-044 Task 003 — Progress Feedback Design

> 日期:2026-08-14 | Sprint: S10-044 | 只设计, 不实现
> 问题: 长时间执行(30-60 秒)用户是否知道系统正在工作

---

## 1. 现状分析

- `factory demo run`: 执行 30-60 秒, 期间**无任何输出**(黑盒等待)
- `factory run`: 同上(薄代理 exec, 无进度)
- 用户焦虑点: "卡住了吗? 还在跑吗? 出错了?"

## 2. 设计: CLI 进度输出

### 阶段输出(简单可靠, 无需修改 ExecutionLoop)

```
=== AI Factory Quick Demo ===
  ✔ workspace 就绪
  ✔ 项目目录: /tmp/factory-demo-xxx/main.py
  ✔ 目标: 给 main.py 加 hello
  ✔ 执行: backend-1 → Router 决策
  [1/4] Router 决策中...        ← 新增 (执行前)
  [2/4] LLM 调用中...          ← 新增 (执行中, 阻塞等待)
  [3/4] 验证中...              ← 新增 (验证产物)
  [4/4] 生成报告...            ← 新增 (收尾)
  ✔ 完成! 用时 41.8 秒
```

### 实现方式(CLI 层, 不改 ExecutionLoop)

**方案 A(推荐): 阶段提示 + 阻塞等待**

```python
# _demo_run 中, 调用 exec 前打印阶段, 调用后打印完成
print("  [1/4] Router 决策中...")
result = exec_cli.cmd_exec_run(...)   # 阻塞等待 (现有行为)
print("  [4/4] 生成报告...")
```

- 优点: 极简, 零风险, 不碰核心
- 缺点: 中间 30 秒仍无输出(但用户看到"进行中")

**方案 B: 轮询进度(需事件支持)**

```python
# 后台线程跑 exec, 主线程轮询 events.db 的 execution 事件
# 每 5 秒打印: "[2/4] LLM 调用中 (12 秒)..."
```

- 优点: 实时进度
- 缺点: 复杂, 需线程管理, 风险高

**推荐: 方案 A(阶段提示)。** 若事件系统已支持 exec 事件(events.db 有 execution.* 事件), 未来可升级方案 B。

## 3. 事件系统复用检查

- events.db 已有: org.execution.completed/failed 事件(S10-023 确认)
- 但执行**进行中**事件(llm_request_sent / llm_response_received)在 S10-023 真实执行时已记录
- 方案 B 可复用这些事件做实时进度, 但**本 Task 不实现**(风险控制)

## 4. 边界

| 允许 | 禁止 |
|---|---|
| _demo_run 加阶段提示(打印) | 修改 ExecutionLoop/AgentRuntime |
| run_cmd 加"执行中..."提示 | 修改 Router/Provider |
| 事件系统只读检查 | 引入线程/异步 |

## 5. 实现清单(未来 Task)

```
1. _demo_run: 执行前打印 "[1/4] Router 决策中..."; 执行后 "[4/4] 生成报告..."
   (最小实现, 2 处打印)
2. 可选: run_cmd 打印 "执行中... (耗时可能 30-60 秒)"
3. 可选增强: 计时器 + 每 10 秒提示 (若用户等超过 20 秒)
```

---

> Task 003 完毕 | 方案 A: 阶段提示(CLI 层, 零风险) | 方案 B 需事件轮询(未来)

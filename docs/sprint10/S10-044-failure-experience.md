# S10-044 Task 001 — Failure Experience Improvement

> 日期:2026-08-14 | Sprint: S10-044 Polish | 设计 + 实现
> 问题: demo run / run 失败时用户不知道原因

---

## 1. 根因分析(实测)

| 现象 | 根因 |
|---|---|
| demo run 无 key → 只显示 "status failed", 无原因 | exec 返回 `ok=True, exit_code=1, status=failed, error=...`; demo run 先打印 status(stdout)再打印 error(**stderr**)→ 用户只看 stdout 看不到原因 |
| 错误消息指向 ANTHROPIC_API_KEY | Router 决策在无配置时 fallback 到 anthropic(非用户 init 的 deepseek)→ 更混乱 |

## 2. 统一错误输出设计

所有 CLI 失败统一格式(错误到 **stdout**, 用户必见):

```
❌ Failed

Reason:
  <具体原因, 来自 exec error>

Solution:
  <可操作修复指引>
```

### 场景映射

| 场景 | Reason | Solution |
|---|---|---|
| missing API key | provider error: <provider> api key missing | `export <PROVIDER>_API_KEY=...` 后重试; 或 `factory init --provider <id>` |
| provider not found | provider not found: <id> (available: [...]) | 检查 `factory config check`; 用可用 provider: `--provider <id>` |
| invalid project | project dir not found: <path> | 确认目录存在: `factory project create --repo-path <dir>` |
| execution failed | <exec error> | 查看 `factory run-status --id <id>` 报告; 重试 |

## 3. 实现要点(CLI 层, 不碰 exec)

### cli_factory.py 修改
1. `_demo_run`: 
   - `exit_code != 0` 分支 → 打印统一格式(❌ Failed + Reason + Solution)到 **stdout**
   - 从 result.error 提取 Reason; 用简单匹配映射 Solution
2. `run_cmd`: 同样统一错误输出(现有 "错误: ..." 改为 ❌ Failed 格式)
3. 新增 `_format_failure(result) -> str` 辅助(Reason/Solution 映射)

### 测试
- tests/console/test_cli_demo_run.py 增加: 失败时输出含 "❌ Failed" + "Reason" + "Solution"
- tests/console/test_cli_project_run.py 增加: run 失败统一格式

## 4. 边界

- 只改 cli_factory.py(CLI 展示层)
- exec/org/core 零改动
- 向后兼容: 输出格式变化但 exit code 不变

---

> Task 001 设计完毕 | 根因: 错误在 stderr | 方案: 统一 ❌ Failed + Reason + Solution 到 stdout

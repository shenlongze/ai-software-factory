# Execution Truth Contract (P0-001)

> 建立日期: 2026-09-01
> 触发: S-SESSION-UX-CONTROL-AUDIT P0-001 — AI 伪造工具执行
> 状态: 生效 (enforcement 在 runtime, prompt 仅辅助)

## 核心原则

> **LLM output is not execution evidence.**
> **Only real execution records can establish execution facts.**

模型自然语言永远不能成为以下事实的证据:

- Tool execution evidence
- Command execution evidence
- File creation evidence
- Process execution evidence
- Test execution evidence
- Build success evidence
- Deployment success evidence
- Task completion evidence

## 验证边界

```
MODEL OUTPUT
    ↓
CLAIM EXTRACTION / CLASSIFICATION   (execution_truth.extract_execution_claims)
    ↓
EXECUTION EVIDENCE VALIDATION       (execution_truth.validate_execution_claims)
    ↓
ALLOW / REWRITE / BLOCK             (execution_truth.execution_claim_block_prompt /
                                     sanitize_hard_converge)
```

不是:

```
MODEL OUTPUT
    ↓
FINAL RESPONSE
```

## 声称分类 (结构化, 非关键词黑名单)

执行类事实声称按类型识别: command / file / test / build / deploy / task。
识别的是"陈述完成态"的事实声称 (已执行/已创建/测试通过/构建成功/已部署/任务完成),
普通建议/条件表达 (可以运行/如果你执行成功) 不命中。

## 校验规则

1. 无执行声称 → ALLOW (普通回答/建议/条件表达)
2. 有声称 + 本轮零真实工具调用 (tool_calls=0) → **BLOCK** (负证据)
3. 有声称 + 本轮工具全部失败 + 声称含成功/完成语义 → **BLOCK**
4. 其余 (有真实成功执行记录) → ALLOW (细节数字由 W8 verify_details 兜底)

## Zero Tool Call 是负证据

tool_calls=0 时, 模型不得产生未经证实的执行事实声称
(executed/created/deleted/modified/tested/built/deployed/verified/completed)。

## 声称但无 Tool Call 的安全行为

- **Strategy A — 补执行**: 系统可确定模型意图且工具合法 → 引导通过真实函数调用通道执行, 拿到真实结果后再陈述。
- **Strategy B — 撤回**: 无法安全推断 → 不允许伪造执行, 如实返回
  「我还没有实际执行该操作, 当前没有产生真实执行记录」。

## Enforcement 位置 (runtime, 非 prompt)

| 出口 | 路径 | 状态 |
| ---- | ---- | ---- |
| 流式会话消息 | fastapi_adapter 6991 → run_agent_native | ✅ validator 生效 |
| 同步会话消息 (project) | fastapi_adapter 7172 → run_agent_native | ✅ validator 生效 (原 run_agent v1 已替换) |
| 同步会话消息 (company 兜底) | fastapi_adapter 7701 → run_agent_native | ✅ validator 生效 (原直接 send_message 已替换) |
| 硬收敛兜底 | agent_loop 硬收敛轮 | ✅ validator + sanitize 标注 |

辅助防线 (prompt, 不承担主 enforcement):
- model_prompt deepseek traits: `no_fabricated_execution=True` → system 注入执行真实性契约。

## 文件

- `factory-console/session/execution_truth.py` — 声称提取/校验/撤回提示/sanitize
- `factory-console/session/agent_loop.py` — 软收敛 + 硬收敛集成 (claim_retries)
- `factory-console/web/backend/fastapi_adapter.py` — company/project 同步出口统一 v3
- `factory-console/session/model_prompt.py` — deepseek A0 契约 (辅助)
- `tests/console/test_execution_truth.py` — 10 场景回归 (27 断言)

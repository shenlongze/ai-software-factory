# K5 Conversation Quality — 用户语言质量验证

> 日期: 2026-08-29 | HEAD: (K5 commit)

## 8 项质量维度 (conversation_quality.py)
| 维度 | 验证 | 结果 |
|------|------|------|
| A 清晰 | 回复不含内部术语 (production_run/executor_factory/...) | PASS (test_clarity) |
| B 一致 | 决策保留不矛盾 | PASS |
| C 不跑题 | 多轮围绕 goal | PASS (test_no_forget_no_drift) |
| D 不遗忘 | 已确认决策保留 | PASS |
| E 不幻觉 | 未执行不说执行 (无 work 不说"已完成") | PASS (test_no_hallucination) |
| F 不越权 | 无审批不进入需审批 work | PASS |
| G 不过度行动 | 讨论阶段不擅自执行 | PASS (test_no_overaction) |
| H 结果解释 | 结果说人话 (做了什么/为什么/下一步) | PASS |

## Golden Suite (G1-G20)
20 场景全过 (deterministic + 真实 LLM executor):
- 闲聊/讨论/澄清/修改/否定/转向/确认/拆解/执行/成功/失败/卡住/审批/Replan/中断恢复/长对话/压力/钻取/回环/塔视图

# K1 GAP Audit — Conversation OS Reality

> 日期: 2026-08-29 | HEAD: 89a3c182 (v1.1.350)

## 25 项 Conversation 能力审计
| # | 能力 | 现状 | 判定 |
|---|------|------|------|
| 1 | 用户第一次进入 | 无 (CLI 导向) | MISSING |
| 2 | 自然语言输入 | chat_store 落库 (无理解) | PARTIAL |
| 3 | Intent/Goal 理解 | 无 | MISSING |
| 4 | 多轮对话 | 落库可查 (无状态) | PARTIAL |
| 5 | Context 保持 | 无 (S35 可复用) | MISSING |
| 6 | Topic/Goal 稳定 | 无 | MISSING |
| 7 | 用户纠正 | 无 | MISSING |
| 8 | Requirement 提取 | 无 | MISSING |
| 9 | Decision 形成 | 无 | MISSING |
| 10 | Approval | governance_service (S17) | REUSE |
| 11 | Plan | 无 | MISSING |
| 12 | Workforce Selection | workforce_os (S30) | REUSE |
| 13 | Task Decomposition | 无 (Task Tree 未建) | MISSING |
| 14 | Task/Node 创建 | production_run (S3) | REUSE |
| 15 | Agent 执行 | S11/S12 | REUSE |
| 16 | Tool 调用 | 无 (会话工具) | PARTIAL |
| 17 | Runtime 执行 | executor_factory (S4) | REUSE |
| 18 | Artifact 产生 | artifact_lifecycle (S1) | REUSE |
| 19 | Verification | verification.py (S5) | REUSE |
| 20 | Recovery/Repair | S28/S39 | REUSE |
| 21 | Evidence | S23 | REUSE |
| 22 | Lineage | S43 unified_contract | REUSE |
| 23 | Result 呈现 | 无 (task_id 级) | MISSING |
| 24 | 用户继续追问 | 无 | MISSING |
| 25 | 会话继续工作 | 无 | MISSING |

## 结论
- 底层 Work 链 (12-22) 全 REUSE (S3-S43 已建)
- **Conversation 理解层 (1-11, 23-25) 全 MISSING** — K1 核心
- chat_store.py 仅落库, 无 Intent/Requirement/Decision/Work 触发

## K1 最小设计 (不重建 Core)
```
conversation_os.py:
- Conversation Entity (S43 unified_contract 复用): conv_/msg_ 前缀
- Intent 理解 (deterministic 规则 + LLM 辅助, evidence-backed):
  DISCUSS / DECIDE / APPROVE / EXECUTE / ASK_STATUS / CLARIFY
- ConversationState: goal/confirmed_decisions/pending_questions/current_topic
- Requirement 提取: 从确认的决策形成 req_ 实体
- Decision 形成: proposal → user confirm → decision_ 实体 (不可覆盖, 版本化)
- Work 触发: EXECUTE intent → create_task → create_production_run → execute → verification → evidence
- Result 呈现: 自然语言摘要 (做了什么/为什么/结果/下一步)
- 多轮: 基于 ConversationState + S35 Context (JIT, 非全量)
- 全链路 S43 Event/Lineage/Audit
```

## 禁止
- 第二套 SSOT/Event/Governance/ID; 不重建 Core; 不无限 Context; 不 fake E2E

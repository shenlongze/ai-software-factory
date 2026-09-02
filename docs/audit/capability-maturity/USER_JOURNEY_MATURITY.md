# USER JOURNEY MATURITY — STEP 7

| 节点 | M | 证据 |
|------|---|------|
| User→Session | M4 | 会话 81 + 消息链 |
| Session→Intent | M4 | query_engine + execution_truth |
| Intent→Requirement | M3 | requirements.json 7 (capture 真实; 无下游 M0 单独计) |
| Requirement→PRD | M0 | PRD 实体 ABSENT (M3 承诺) |
| PRD→Plan | M0 | 无 PRD 实体 |
| Plan→Task | M4 | plan_id E2E |
| Task→Agent | M3 | gateway route (会话链) + exec records |
| Agent→LLM | M4 | llm_fn→deepseek |
| LLM→Tool | M3 | _fc 注册+调用 |
| Execution | M4 | 会话链 E2E |
| Execution→Artifact | M2 | exec ART-*; 会话链无 |
| Artifact→Verification | M2 | exec test_result |
| Audit | M4 | 5160 |
| Result→Session/User | M3 | progress_card/run_ids (部分) |

## 主链成熟度
User→Session→Intent→Planning→Task→Execution→Audit = M4 贯通 (用户旅程核心)
Requirement→PRD→Plan 段 = 断点 (ReqTrace M0 / PRD M0)
Artifact/Verification 段 = M2 (exec 域真实, 会话链未关联)

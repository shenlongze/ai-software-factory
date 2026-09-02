# CURRENT CONTRACT — STEP 5 (2026-09-02)
# 从代码+数据可证明的系统契约 (非未来架构)

| Capability | Proven Contract | Evidence |
|-----------|----------------|----------|
| Session | 会话持久化 (81), 消息链, cancel, run_ids | console_sessions.json |
| Requirement | capture→requirements.json (VALIDATED) | agent_loop.py:795 |
| Plan | pending→executing→completed/failed (幂等+聚合) | session_plans + reconcile_plan |
| Task | backlog SSOT + dependency + 八态 | org/management |
| Execution | ExecState 依赖门控→gateway→回写 (会话链) | E2E |
| Agent | registry + gateway router 选择 + records | agents.json + execution_records 100 |
| LLM | llm_fn 注入→provider 默认 (deepseek) | providers.json |
| Tool/Skill | agent_loop _fc + exec tool/skill + skills.json | — |
| Artifact | exec 域 ART-* (patch/test_result) | exec/results.json |
| Audit | audit_events 5160 | — |
| Project | org projects/backlog/sprint | — |

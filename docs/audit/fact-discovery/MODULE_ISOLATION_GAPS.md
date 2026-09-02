# MODULE ISOLATION GAPS — STEP 5
| 模块 | consumer | 判定 (非 DEAD 判定) | 证据 |
|------|----------|---------------------|------|
| factory-core | 0 | ISOLATED (代码+测试+ADR 完整, 无外部消费者) | grep 全仓 0 |
| LLMRouter | 0 | UNUSED_IN_PRODUCTION (有代码+测试) | llm_router.py |
| factory-runtime | 0 | UNPROVEN (57B runtimes.json) | runtimes.json |
| Learning/Release | UNKNOWN | UNPROVEN | 端点存在 |
| PRD | — | ABSENT | 无实体 |
- 禁止 DEAD 判定: core/LLMRouter 有完整测试, 可能经独立 CLI/未来集成 (UNKNOWN)

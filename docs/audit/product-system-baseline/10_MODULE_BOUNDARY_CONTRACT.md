# 10 — MODULE BOUNDARY CONTRACT (STEP 10, 2026-09-02)

| 模块 | 正式角色 | 证据 | 禁止 |
|------|---------|------|------|
| factory-console | 生产主链 (Web/会话/编排) | uvicorn 8011, 371 API, E2E | — |
| factory-org | 生产主链 (领域 SSOT) | console 69 import | — |
| factory-exec | 生产主链 (执行/Runtime 域) | console 79 引用, records 100 | 不得形成第二 Task SSOT (见 06) |
| factory-core | 独立模块 (潜在独立产品) | 全仓消费 0 | 不得描述为 CURRENT PRODUCTION (INV-015) |
| factory-runtime | 独立模块 | 无运行痕迹 (57B) | 不得描述为 CURRENT PRODUCTION |

## 规则
- 无生产证据模块 = 独立模块, 不虚构 production consumer (INV-015)
- 独立模块可保留 CLI/测试/契约 (L0-L1), 纳入生态需契约测试 (P-MOD-03)

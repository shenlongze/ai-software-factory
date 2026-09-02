# MODULE INTEGRATION — STEP 4 (2026-09-02)

| Module | Entry | API | CLI | Data | Dependencies | Production Consumer | Runtime |
|--------|-------|-----|-----|------|-------------|--------------------|---------|
| factory-console | uvicorn 8011 | 371 | factory | ~/.factory | org, exec(79), external_executor | — | YES |
| factory-org | — | — | — | ~/.factory/org | — | console (69) | YES |
| factory-exec | exec cli | via console | factory-exec | ~/.factory/exec | ? | console (79 引用) | YES |
| factory-core | core cli | — | factory-core | ? | ? | **0 (全仓)** | NO |
| factory-runtime | runtime cli | — | factory-runtime | runtimes.json (57B) | ? | 0 | NO |

## 静态 vs 运行时

- console→org: STATIC (69 import) + RUNTIME
- console→exec: STATIC (79 处含延迟) + RUNTIME (懒装配)
- console→core: 无
- console→runtime: 无
- core/exec/runtime 相互: UNKNOWN (未验证)

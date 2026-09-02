# PACKAGE DEPENDENCY MATRIX — STEP 2 (2026-09-02)

| From | To | Static Import | Runtime Call | Process | Network | Storage | Config | Evidence |
|------|----|--------------|-------------|---------|---------|---------|--------|----------|
| factory-console | factory-org | 69 (from org.*) | YES (E2E 链) | NO | NO | YES (同一 ~/.factory) | NO | service.py:1348+ |
| factory-console | factory-exec | 6 (延迟 from exec) | YES (懒装配) | 可能(subprocess 执行器) | NO | 共享 workspace | NO | service.py:412/422/445/539/671/818 |
| factory-console | factory-core | 0 | 0 | UNKNOWN | UNKNOWN | schema 共享(注释 events.py:139) | NO | grep 0 |
| factory-console | factory-runtime | 0 | 0 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | grep 0 |
| factory-exec | 内部 | self | self | — | — | — | — | 独立 CLI |
| factory-core | 内部 | self | self | — | — | — | — | 独立 CLI (main.py) |
| factory-runtime | 内部 | self | self | — | — | — | — | 独立 CLI |

补充耦合通道:
- importlib: console 6 处 (service.py 动态装配 exec)
- subprocess: console 117 处 (verification.py:52 真实 pytest 等)
- HTTP: console 37 处 (local-ai 11434 ollama; runtime preview 8099; exec/requests.json 读)
- filesystem: console/org 共享 ~/.factory 数据根 (同一 storage 域)
- 未验证: core/exec/runtime 之间的进程/网络/存储耦合 (UNKNOWN)

# 07 — CLI / API / WEBUI CONTRACT (P2-A CONTRACT, 2026-09-06)

## 1. 未来最小接口 (冻结, 不实现)

### CLI (扩展 factory release)
```
factory release create --task-run run-* --exs EXS-* [--artifact art-*] [--reason]
factory release inspect RELEASE-*
factory release list [--task TASK-*] [--status]
factory release gate RELEASE-*      (评估 CANDIDATE→GATED/REJECTED)
factory release approve RELEASE-*   (人工 approval 后 execute)
factory release trace RELEASE-*     (反向 provenance 链)
```
rel-* 子命令保留 (M3 legacy 只读), 新 RELEASE-* 操作区分。

### API
```
POST   /api/releases                (ReleaseService.create, idempotent)
POST   /api/releases/{id}/gate      (gate 评估)
POST   /api/releases/{id}/execute   (approval 后 → RELEASED)
GET    /api/releases                (list)
GET    /api/releases/{id}           (detail + trace)
GET    /api/releases/{id}/trace     (reverse provenance)
```

### WebUI
- 只允许 backend projection (经 API)
- 禁止: create local Release / infer success / store business state / fabricate

## 2. 原则

所有入口 → ReleaseService → release store (单 writer)。

# 03 — RELEASE LIFECYCLE (P2-A CONTRACT, 2026-09-06)

## 1. 冻结最小生命周期

```
CREATED → CANDIDATE → GATED → RELEASED → SUPERSEDED
                          ↘ REJECTED (gate 未过, 可重试为 CANDIDATE)
                          ↘ REVOKED (已 RELEASED 后发现问题 → 撤回)
```

| 状态 | 含义 | 谁驱动 |
|---|---|---|
| CREATED | Release 意图记录 (打包产物) | ReleaseService.create |
| CANDIDATE | 可评估的发布候选 | create 后即 CANDIDATE (或人工) |
| GATED | gate 检查通过 | ReleaseService.gate (消费 ver-*/EVD-*) |
| RELEASED | 发布事实成立 (不可变核心) | ReleaseService.execute (approval 后) |
| SUPERSEDED | 被新 Release 取代 | 新 release 关联 |
| REJECTED | gate 未过 (可重试) | gate FAIL |
| REVOKED | 发布后撤回 | 人工/系统 |

## 2. 原则

- 状态 = domain truth (store 持久化 + 受控转换 + history)
- 禁止 WebUI/CLI/git tag 作 lifecycle SSOT
- RELEASED 后不可原地修改语义 (immutable core); 变更 = 新 Release (SUPERSEDE)

## 3. 对比 rel-* (9 态)

新生命周期精简为 7 态 (去掉 M3 RELEASING/VERIFYING/FAILED 中间过程 —
验证由 P0 ver-* 承载, 不需 release 自跑); rel-* 机制参考不照搬。

# 03 — OBSERVABILITY (READ-ONLY)

## WHO/WHAT/WHERE/WHEN/WHY/RESULT
| 问题 | Runtime/ActiveRuntime 能答? | Run Detail 能答? | 备注 |
|---|---|---|---|
| 哪个 Project | ✓ 页作用域 | ✓ | |
| 哪个 Run | ✓ active/latest | ✓ 头 | |
| 当前 Stage | ✓ LIVE currentStage | ✓ 时间线 ● | C1/C2 |
| 当前 Agent | △ (stage role 在 detail) | ✓ 展开 role 人话 | |
| 状态 | ✓ | ✓ | report 终态合并 (C2 修) |
| 已完成 Stage | ✓ chips | ✓ ✓ 清单 | |
| Repair/Retest | △ (事件可见) | ✓ 人话徽章 | |
| Error | △ LIVE lastError | ✓ errors 块 | |
| Artifact | ✗ | △ stage note art= | OBSERVABILITY_GAP (P2): run detail 未嵌 artifact 卡 |
| Verification | ✗ | ✗ | P2 |
| Acceptance/Release | ✗ (在 review 页) | ✗ | 跨页跳转缺运行上下文提示 P3 |

结论: 实时"正在做什么" ✓ (C1); "做成了什么/可信度" 需跳 workspace/review
页 — 运行上下文内无产物/验收状态卡 (P2)。

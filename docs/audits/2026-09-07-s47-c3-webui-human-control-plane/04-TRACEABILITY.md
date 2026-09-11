# 04 — TRACEABILITY (READ-ONLY)

## 真实链逐层导航现状
Project → Run (R*) → Stage (✓, 展开) → Calls (✓) → Repair (✓)
→ ACC (review) → RELEASE (review) → Delivery (artifact id 列表)
→ canonical EXS/art/ver/EVD (✗ 无 REST; ID 出现在 review 卡但不可点)

## canonical ID 可见性
| ID | 可见处 | 可导航 |
|---|---|---|
| R1788679924187 | runtime/review | ✓ |
| EXS-* | release 记录 (api 层) | ✗ UI |
| art-* | review 卡 / release | ✗ 不可点 (无 detail 页) |
| ver-* | review 卡 | ✗ |
| EVD-* | 无 UI | ✗ |
| ACC-* | review | ✓ 状态卡 |
| RELEASE-* | review | ✓ 状态卡 |

TRACEABILITY_GAP (P2): "用户能否从生产结果一路追溯证据" → 部分能
(release→ACC→artifact id), 不能到 EVD (证据文件无 REST 无 UI)。
证据链下游 (S46) 完整落 store; 缺薄投影端点 + UI 链 (C3 backlog)。

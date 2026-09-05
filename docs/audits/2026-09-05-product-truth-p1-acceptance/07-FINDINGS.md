# 07 — FINDINGS (P1 FINAL ACCEPTANCE, 2026-09-05)

> 架构气味搜索 + P2 观察项 (非阻塞)

---

## 1. 气味搜索 (零命中 = 干净)

| 气味 | 结果 |
|---|---|
| duplicate Plan stores | 无 (plans store 唯一; session_plans = legacy projection) |
| duplicate Requirement stores | 无 (REQ-* canonical; req_* legacy 分离) |
| direct JSON writes (bypass service) | 无 (product_truth store 仅模块内写) |
| direct PRD.md truth | 无 (PRD-* truth; md 零读回) |
| reverse reconstruction | 无 (无 event/audit 重建 domain) |
| hidden migration | 无 (legacy 原样) |
| ID aliasing | 无 (前缀唯一; 测试) |
| task duplication | 无 (product_truth 无 create_task) |
| session becoming Product Truth | 无 (session_plans 降级 legacy) |
| event stream becoming Product Truth | 无 |
| UI-local Product state | 无 (WebUI 零直写) |
| implicit FK by filename/title | 无 (reverse_trace 逐 FK) |
| in-place Plan mutation | 无 (无 update API) |

## 2. P2 观察项 (非阻塞, 记录不修)

- **F1 (P2)**: 旧 M3 API (fastapi_adapter:1554/1657) 仍读取 legacy
  requirements.json / session_plans.json 展示 (M3 项目卡)。这是 legacy
  projection — 不写 canonical、不标 canonical; 未来 M3 域收敛时切换。
- **F2 (P2)**: test_console_cli 命令集断言过期 (缺 product/ptrace/ct/strategy
  等历次新增命令) — 预存 (stash 对照证), 未修 (纪律)。
- **F3 (P2)**: agent_loop/fastapi 双写 (legacy + canonical REQ-*/PLAN-*) 为
  失败安全同步 — 非阻塞式收敛 (legacy writer 仍在写 req_*/session_plans)。
  未来可切换为单 canonical writer + legacy reader。
- **F4 (P2)**: product_truth 无 event emission (最小实现) — domain→store
  直接; 若需审计观察, 后续补 emit (不阻塞契约合规)。
- **F5 (P2)**: Idea 的 Web create_feature 语义 (M3 任务树 feature) 未收敛到
  IdeaService — P1 只新增 canonical Idea; 旧 feature 树保留 (任务树功能独立)。

## 3. 剩余风险

- 无 P0/P1 级风险
- P2 观察项全部为 legacy 兼容/展示/测试过期, 不影响新链 correctness

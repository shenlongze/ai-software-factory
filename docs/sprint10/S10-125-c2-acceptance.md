# S10-125 — C-2 产出物契约引擎接线：独立验收报告

> 日期: 2026-08-26 | 版本: **不 bump** (C-2/C-3 合并由集成方统一) · 当前 HEAD v1.1.111
> 验收人: Hermes (CTO, 独立验证 — 非 Codex 自报告)
> 实现: `09eeb0a` (refactor(S10-125), 6 files +934/-28)
> 前置: C-1 v1.1.109 (set_artifact + Manifest) · 设计文档 9e6d95d

---

## 验收矩阵（5 项全过）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 写点枚举文档 (含改造前后对照) | ✅ | docs/sprint10/S10-125-c2-write-points.md (94 行, 12 写点 + 对照 + 缺口) |
| 2 | 全部引擎写点走 set_artifact, 直写归零 | ✅ | 4 改造文件 grep 标准文件名零残留 (我独立复跑); 12 写点全部改造 |
| 3 | 契约测试 + 引擎接线测试全过, 回归 0 新增失败 | ✅ | test_s10_125_c2_contract_wiring.py **19 passed** (我复跑); 全量 5560 passed, 2 failed 为**并发 C-3 预存漂移** (父提交同失败, 见 §2) |
| 4 | 边界遵守: 未碰桥文件/版本文件/artifact_contract 本体 | ✅ | commit 仅 actions/orchestrator/change_control + 测试 + 文档; fastapi_adapter/frontend/pyproject 零触碰; 未 bump 版本 |
| 5 | 诚实记录: 无法改造点 + 理由 | ✅ | G1-G4 如实记录 (见 §3) |
| 交付后 | 债务清单 C-2 ✅ | ✅ | 待办清单 L284 标记 ✅ |

## 1. 独立验证实录（我的脚本 9/9）

```
✅ set_artifact 写入 PRD.md + manifest 条目 + 版本 + producer/trace_id
✅ 第二次写 → history/PRD.v1.md 归档 + 版本 +1
✅ 直写归零 (grep 无残留直写标准文件名)
✅ create_product 引擎驱动 → manifest product 条目 + product.json 内容一致
✅ 桥文件未碰 (commit 无 fastapi_adapter/frontend/pyproject)
```

## 2. 回归 2 failed — 隔离验证结论（诚实记录）

全量 5560 passed / 2 failed:
- `test_s10_112_registry_consistency::test_write_routes_in_whitelist` — "写路由超出白名单: DELETE /api/mcp/connections/{connection_id}"
- `test_console_api::test_route_modules_exported` — API __all__ 漂移
- **归属**: 并发 C-3 会话 commit 8f795cc (v1.1.110) 新增 MCP DELETE 路由但未同步写路由白名单 — 注册表漂移
- **证明**: 我的 commit 09eeb0a 未触碰 fastapi_adapter/api/白名单测试 (git show 空);
  worktree 隔离在父提交 88d3c89 上**同样 2 failed** → 预存失败, 非 S10-125 引入
- **处理**: 不代修 (fastapi_adapter 归 C-3 集成方; 白名单更新随其集成) — 已上报

## 3. 契约能力缺口（诚实记录, 给集成方 Codex）

- **G1**: `_write_plan_quality_files` 的 PRD.quality.json / engineering.quality.json — 文件名 ≠ schema quality.json,
  且双文件共享单一 quality 槽位 (两次 type=quality 互相覆盖 manifest 条目) → 保持现状直写 (已有失败安全),
  建议统一 quality.json 或扩展契约
- **G2/G3**: session/quality.py Validator.save (validation_result.json) / RepairManager (repair_task.json) — 直写,
  文件不在 C-2 允许清单 → 未改造
- **G4**: lifecycle_store.set_project_lifecycle 三处同步写 (product.json/execution_state.json 镜像) — J-1 统一入口 → 未改造
- 非契约资产 (team_report.md / execution_records.json / change_control.json) 按设计不改

## 4. 结论

- **通过**。C-2 引擎接线完成: 产品管线/编排器/变更回流/服务层 12 写点全部改走 set_artifact —
  产出物"历史不丢"覆盖所有引擎; manifest 版本链 + producer + trace_id 全程可追溯。
- 建议后续: C-3 集成时处理 G1-G4 (quality 槽位扩展 + Validator/Repair 接入 + lifecycle_store 镜像);
  C-5 存量迁移 (legacy 资产 set_artifact 归位)。

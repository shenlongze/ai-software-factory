# S10-115 — J-1 生命周期状态单一来源：独立验收报告

> 日期: 2026-08-25 | 版本: v1.1.83 | 验收人: Hermes (CTO, 独立验证 — 与 Codex 自报告分开)
> 实现: `4ec78ad` (feat(S10-115), 22 files, +1521/-61)
> 前置: v1.1.82 · 设计文档 f2863b1

---

## 验收矩阵（5 项全过）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | S10-115-write-points.md 落盘 | ✅ | 全写点枚举清单 (改前/改后对照) 存在 |
| 2 | 8 项目实测: 对账修复后三处一致 + 修复前快照 | ✅ | 真实 ~/.factory 对账: **5 修复 + 3 已一致跳过 + demo 无法判定如实跳过**; 5 快照落盘; 修复后 8 项目全部 project==product(==es), **0 漂移** |
| 3 | 契约测试 ≥8 覆盖 a-e 全绿 | ✅ | test_s10_115_* 43 passed (我独立复跑; 31 写侧 + 12 读侧) |
| 4 | 全量回归 0 新增失败 | ✅ | console+api: **5320 passed / 1 skipped / 0 failed** |
| 5 | v1.1.83 + 待办清单 J-1 ✅ | ✅ | pyproject=1.1.83 + 断言 + CHANGELOG + FEATURES; 待办 L224 ✅ |

## 1. 独立验证实录（我的脚本 16/16 tmp 夹具 + 真实数据对账 3 步）

```
tmp 夹具 (16/16):
✅ 词汇映射 project_created→product_defined / prd_ready→engineering_ready
✅ 统一入口: 非法词汇拒绝 · 防回退拒绝 (development→product_defined) · force 例外通过
✅ 镜像跟随: product + execution_state 与 canonical 同步
✅ 对账: DRIFT1 (product 回退) → 跟随 canonical; DRIFT2/3 (缺 project.json) → 建 canonical;
   SKIP1 (无状态) → 跳过不臆造; 快照落盘; 修复后三处一致

真实数据对账 (~/.factory, 快照先行):
STEP 1 dry-run: 5 待修复 (P-2f622bdf→product_defined / P-94ec0742→product_defined /
  P-e023a04c→engineering_ready / P-f848f51d→development / ai-factory-self→development)
  + 3 已一致跳过 + demo 无法判定
STEP 2 实跑: 5 修复 + 5 快照
STEP 3 复核: 8 项目三处一致, 漂移 0
```

## 2. 关键设计验证（反虚标）

- **canonical 唯一**: project.json.status; product.json/execution_state 均为镜像, 只经 set_project_lifecycle 更新
- **防回退**: 重生成 PRD 不降级 (契约 c 钉住); development 项目 PRD 重生成 → project.json 不变,
  product.json 跟随 canonical
- **词汇统一**: 写侧全部 Lifecycle 词汇; 旧词汇 (project_created/prd_ready) 经映射一次性对账
- **失败安全**: 损坏文件不崩; demo 无状态 → 如实跳过不臆造
- **真实数据修复证据**: P-f848f51d (日记) product.json prd_ready → development (跟随 canonical), 与 execution_state 一致

## 3. 契约测试

- 写侧 test_s10_115_lifecycle_single_source.py (31 用例: 写点枚举/一致性/防回退/对账/映射/统一入口)
  + 读侧 test_s10_115_board_consistency.py (12 用例, 并发读侧纳入)
- 我独立复跑 43 passed
- 既有更新: test_session_pipeline (prd_ready→engineering_ready)、test_session_product (project_created→product_defined) + 版本断言 8 处

## 4. 诚实记录（工程资产）

- **真实数据对账由 Hermes 验收阶段独立执行** (Codex 按边界未碰真实 ~/.factory) — 符合"自报告 vs 独立验收分开看"
- **无法判定**: demo 无任何状态文件 → 如实跳过 (未臆造)
- **并发**: 读侧 (board 对账可见 + 版本文件) 并行落盘并入同 Sprint 提交; 工作区仅剩 demo/、unused/ untracked
- Codex 沙箱 7 个环境性失败 (team_decision 写真实 ~/.factory 权限等) 在 baseline 复现 — 我环境 0 failed
- 快照可回滚: .status_snapshot_20260824-194846.json 等 5 个含修复前三处原值

## 5. 结论

- **通过**。J-1 三轨漂移消除: 写侧统一入口 + 防回退守卫 + 存量对账 (快照先行) + 读侧 canonical 优先;
  真实数据 8 项目全部一致。
- 建议后续: J-2 (节点衔接验证) / J-3 (交付后迭代) 待办链上; 新执行路径的 status 写点自动走统一入口
  (写点枚举测试常驻门禁)。

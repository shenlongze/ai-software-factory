# 04 — MIGRATION PLAN (2026-09-06, 未执行 — 待批准)

本审计不改任何生产代码。以下为批准后可执行的**低风险组** (每组独立
commit, 不 push, 每组后: python tests + tsc + frontend test + API 启动):

## Group 1 (零风险, 建议先做)
- .gitignore 加 desktop/ui/ (构建产物; 与 frontend/dist 同规则)
  → 需确认 desktop 构建脚本产物生成方式 (若 packaging 依赖已提交 ui/,
  改为构建时从 frontend/dist 拷贝)
- 验证: git status 不再显示 desktop/ui; desktop 构建文档更新

## Group 2 (低风险, 清理运行时残留)
- 删除 $SMOKE_ROOT/ (字面展开残留, 非 git 跟踪则 rm 即可; 若跟踪需先确认)
- 顶层 exec/checkpoints.json → 移入应属数据根或删 (确认无代码引用)
- 验证: pytest 核心回归 + git grep 无引用

## Group 3 (未来, 触发条件满足时才做 — 非本阶段)
- 前后端拆部署 → apps/web + apps/desktop + packages/contracts
- 迁移: frontend 移目录 → vite base/代理调整 → tsc → e2e
- Desktop 复用 Web: src-tauri 指向同一 build 源
- Mobile (Flutter) 落地时建 apps/mobile (禁本地生产逻辑)

## 风险
- Group 1-2 风险近零 (构建产物/残留, 无代码引用面)
- Group 3 是真实架构迁移, 需独立 Sprint + 完整验证门

## 本阶段停止条件
- 发现 P0 (多套 Backend/Truth/WebUI 独立执行链): 无 — 审计确认不存在
- 大规模迁移风险: 无 — 推荐保持拓扑

## Git
本审计: READ-ONLY, 零生产代码改动, 未 commit (文档 untracked 保留)。

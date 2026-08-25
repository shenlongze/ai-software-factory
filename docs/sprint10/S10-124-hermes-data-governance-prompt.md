# S10-124 · 数据治理 — 项目列表统一 + 脏数据清理 + lifecycle/backlog 对账 — Hermes 提示词（2026-08-26）

> 目标版本 v1.1.97（当前 HEAD v1.1.95; K-6 并发占用 1.1.96, 若 K-6 先行则顺延）
> 来源: Founder 实测 (2026-08-26): "项目不全 / 有很多脏数据"
> 注意: 与 K-6 (retrieval) / K-7b (frontend) 并行 — 只动 service/org/api 数据层, 不碰 web/frontend

---

请作为 Hermes 派发 Sprint 任务给 Codex，遵守既有纪律（pre-flight → plan → dispatch → verify → acceptance → report）。

【任务】S10-124 · 数据治理（项目列表统一 + 脏数据清理 + lifecycle/backlog 对账）
版本目标：v1.1.97（从实际 HEAD +1；若 K-6 先行消耗则顺延）

【背景（Founder 实测问题）】
1. 项目不全: /api/projects 缺 ai-factory-self（真实项目在 ~/.factory/projects 但未进列表）
2. 脏数据: 混入内置示例 markpad（examples/markpad, 自动发现）+ 未命名产品空间残留
   （~/.factory/workspace/projects/1787xxxxxx × 11, org 已删但空间目录残留）
3. lifecycle/backlog 空: org 层所有项目 lifecycle=idea, backlog 0 任务（org 与 workspace 资产脱节）

【现状（实事求是，pre-flight 必须核对，不限于此）】
1. service.list_projects = workspace 项目定义（factory-core WorkspaceManager: managed ∪ examples）∪ org Project
   — examples(markpad) 自动混入; managed 扫描 ~/.factory/workspace/projects 找 project.yaml 实际为 project.json 不匹配
   → 真实项目 (P-xxx, ai-factory-self) 来自 org/其它路径; ai-factory-self 在 ~/.factory/projects 但未注册 org/workspace
2. org/projects.json 10 项 (lifecycle 全 idea); workspace/projects.json index 3 项; ~/.factory/projects 8 目录
   （含 ai-factory-self; demo 已清）; ~/.factory/workspace/projects 21 目录（含 11 未命名产品空间残留）
3. J-1 (v1.1.83) 已修 workspace 三轨 (project.json/product.json/execution_state) — org↔workspace 未对账
4. backlog (org.management) 与 workspace tasks 脱节; lifecycle workflow (org) 与 workspace 生命周期资产脱节

【设计与实现要求（先出设计文档 docs/sprint10/S10-124-data-governance-plan.md，批准后再实现）】
1. 项目列表数据源统一:
   - 真实项目主源 = workspace 项目目录 (~/.factory/projects, 含 product.json) ∪ org 注册
   - ai-factory-self 纳入列表（在 ~/.factory/projects 存在即显示）
   - examples(markpad) 默认隐藏（或标"示例"徽章, 设计定; 提供配置开关）
2. 脏数据清理（快照先行）:
   - 未命名产品空间残留 (~/.factory/workspace/projects/1787xxxxxx × 11, org 无引用) → 备份 + 清理
   - 对账工具: `factory project reconcile --dry-run|--execute`（或等价, Codex 选简单者; 快照先行, 不臆造）
3. lifecycle/backlog 对账:
   - org Project.lifecycle 从 workspace 生命周期资产推进记录同步（当前全 idea 是脱节）
   - org backlog 从 workspace tasks 同步（有 tasks 的项目补 backlog）
   - 无数据源的项目如实标注（不伪造）
4. 一致性测试: 列表完整（含 ai-factory-self）/ 无示例混入 / 无未命名残留 / 对账可断言（复用 J-1 模式）
5. 注册表门禁（P0-10/11）: 新 CLI 命令/API 同步注册表

【硬边界】
- 快照先行, 清理可回滚; 不删有真实数据的项目（无法判定 → 保留并如实标注）
- 只动 service/org/api 数据层, 不碰 web/frontend（K-7b）与 retrieval（K-6）
- 不调 LLM; 纯规则确定性; 失败安全
- 不动 J-1 workspace 三轨语义（只做 org↔workspace 对账）

【验收标准（独立可验证，非 Codex 自报告）】
1. /api/projects 含 ai-factory-self, 无 markpad 示例混入, 无未命名产品残留
2. 未命名空间清理有快照 + 可回滚（fixture）
3. reconcile: dry-run 预览 / execute 修复 / 快照落盘（fixture 断言）
4. lifecycle/backlog 对账: 有 workspace 资产的项目的 org lifecycle/backlog 同步（断言）
5. 无数据源项目如实标注（不伪造 lifecycle/backlog）
6. 契约测试 ≥8
7. 全量回归 0 新增失败（环境性失败如实标注, 与 HEAD 基线对照）
8. 版本 v1.1.97（pyproject + CHANGELOG + FEATURES + 版本断言 + 待办清单 K-6 后数据治理 ✅ 同步）
9. 设计文档落盘 docs/sprint10/S10-124-data-governance-plan.md

【诚实记录】无法判定归属的项目（org-only 台球计分/ScorePocket/博客）如实标注去留, 不擅删;
清理前快照可回滚; 与 K-6/K-7b 并行零冲突（只动数据层）

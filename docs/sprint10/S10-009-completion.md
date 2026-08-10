# S10-009 — Completion Report: Project Lifecycle (Migration Compatibility + Acceptance)

> 日期: 2026-08-11 | 状态: 完成 | 基线: 292a202 (Task 005, 全量 6802)
> 本任务: S10-009-006 (Migration + Acceptance) | 全量 pytest 6817 全绿
> 依据: docs/design/project-lifecycle.md §八 Migration + §九 验收场景 + S10-009-plan.md Task 6

## Implemented (本 Task 交付)

```
Task 006 (Migration Compatibility + Acceptance, 严格 TDD):
1. 验收测试套件 tests/console/test_console_lifecycle_acceptance.py (唯一 basename,
   真实装配端到端 — build_console_service → org ProjectStore + ProjectSpaceStore
   + 假链注入, 零 mock):
   场景 1 (Draft+Discovery): "我要做一个AI笔记软件" 无 name → unnamed-project-XXX
     (lifecycle=discovery, draft=true) + idea/discovery 目录 + project.json 信源
     + 问答持久化 (可多次, 顺序保留) + complete → product_defined + product-definition.md
   场景 2 (Confirm): 确认 "AI Note" → ai-note/ 目录 + CONFIRMED + 索引正确
     (id→slug 无 unnamed 残留) + conversation/discovery rename 后逐字节保留
   场景 3 (旧项目兼容): 预置旧项目 (仅 org/projects.json: P-OLD ScorePocket
     lifecycle=idea) → list/get 读取正常 + 懒迁移回填目录镜像 + 既有 API
     (PATCH rename / DELETE / start 假链) 不破坏
   场景 4 (index 重建): 删除 workspace/projects.json → 列表不受影响 + 索引自愈
     (get_slug 未命中重建) + rebuild_index 目录扫描全量恢复
   全链回归: draft→answer→complete→confirm→start (workflow runner 假链 —
     零 LLM, 真实 org 编排写事件/产物) 整条用户旅程 + Timeline 事件可见

2. 代码修复 (测试暴露的唯一 gap — 懒迁移未在读取路径触发):
   factory-console/service.py:
   - 新增 _migrate_legacy_spaces(): org/space store 均装配时经
     ProjectSpaceStore.migrate_legacy 回填目录镜像 (幂等; 失败安全静默)
   - list_projects() 入口触发 (list 首次访问回填)
   - project_exists() 入口触发 (get 路径首次访问回填 — run-status/start/chat
     的 404 判定经此)
```

## Architecture (S10-009 最终形态)

```
workspace/projects/{slug}/            # 目录信源 (Project Space, §四)
├── project.json                      # Project 记录信源 (生命周期主体)
├── idea/{conversation.json, idea.md}
├── discovery/{conversation.json, product-definition.md}
├── product/ design/ architecture/ source/ artifacts/ knowledge/
├── runtime/                          # AI Runtime Data (与产品内容隔离)
├── logs/                             # Audit Data
└── management/                       # 项目管理骨架
workspace/projects.json               # index 缓存 (id→slug; 目录扫描可重建)
org/projects.json                     # 降为只读索引/镜像 (旧项目兼容 + 目录项目镜像)

生命周期状态机: draft→discovery→product_defined→design→architecture→confirmed→
  development→release→maintain→archived (旧值 idea/active/maintained 宽容兼容)

读取路径 (S10-009-006 修复): list/get 首次访问 → 懒迁移回填目录镜像 (幂等,
  零破坏) — org/projects.json 既有项目 (MarkPad/ScorePocket 类) 读取不受影响。
```

## Tests

```
新增 15 (tests/console/test_console_lifecycle_acceptance.py):
  场景 1 ×3 / 场景 2 ×2 / 场景 3 ×6 / 场景 4 ×3 / 全链回归 ×1
全量 pytest 6817 passed (基线 6802 + 15; 零回归 — console 522 / org 262 及
  全量含 s7 等全部绿)
TDD 记录: RED — 2 个懒迁移断言先失败 (list/get 路径未触发 ensure_space) →
  GREEN — service.py 修复后全绿 (其余 13 项为既有能力证明, 首跑即绿)
```

## Migration

```
方案 A (目录信源 + 索引兼容) 落地验证:
- 新项目 → workspace/projects/{slug}/ 目录 (project.json 信源)
- org/projects.json 保留为索引镜像 (旧项目兼容 + 目录项目镜像)
- 旧项目懒迁移: 读取路径 (list/get) 首次访问 ensure_space 回填目录镜像
  (幂等; 重复读取零额外写; 回填失败静默不 5xx)  — 本 Task 修复的 gap
- 前端列表 = workspace ∪ org 并集 (同 id 合并) — 旧项目完全可见
- index 缓存可删除重建: list 不依赖缓存; get_slug 未命中 → 目录扫描自愈;
  rebuild_index 全量恢复
兼容保证: 旧值 lifecycle (idea/active/maintained) 宽容解析; 旧字段形状
  (无 slug/draft/discovery) 模型默认值兜底 — P-OLD 类存量数据零迁移成本。
```

## Known Issues

```
1. PATCH rename 只更新 org 记录, 不同步目录镜像 project.json (S10-006.5 既有
   契约 — rename 语义 = org 字段更新; 目录镜像以 confirm/懒迁移为准, 后续如
   需目录级 rename 一致性可纳入 S10-010)
2. DELETE 移除 org 记录 + workflow_runs/chat, 但已迁移的 workspace/projects/
   {slug}/ 目录不清理 (延续 S10-006.5 契约 — 删除不级联; 孤儿目录待数据
   治理任务统一处理)
3. 旧项目懒迁移写目录镜像属于读取路径的"允许写" — 零写铁律测试 (isolation)
   以无 org/space store 装配的服务为审计面, 不受影响; 有装配时 list 会回填
   镜像 (设计内行为, §八 方案 A)
4. GET /api/projects/{id} 单项目详情端点仍未注册 (设计 §五 列示) — 现以
   /lifecycle + /run-status + /timeline 组合读取; 如前端需要详情页可补
```

## Next Recommended (S10-010)

```
1. 前端 UI 接线: 项目创建两阶段卡片 → draft/confirm 全链 (Welcome 改造,
   S10-009 边界外未开发 UI)
2. GET /api/projects/{id} 详情端点 (含 discovery/bindings 投影) — 设计 §五
   已定义, 待前端详情页驱动
3. bindings 落库: confirm 后写 management/bindings.json (workflow/agents/
   skills/mcps) — §七 binding 设计的实例化
4. Management Domain 骨架 (backlog/sprint/task 数据模型) + Execution Engine
   骨架 (任务调度/agent 绑定) — 设计 §十 Task 5/6 后续
5. 目录级数据治理: DELETE 清理项目空间目录 + 孤儿目录扫描
```

## 验收场景达成 (design §九)

```
场景 1: "我想做一个AI笔记软件" → Draft (unnamed, DISCOVERY) + Discovery 会话
        持久化 (conversation.json)         ✅ 端到端测试证明
场景 2: 确认 "AI Note" → rename 事务 (ai-note/ 目录/索引/引用全更新) → CONFIRMED
                                          ✅ 端到端测试证明
场景 3: 既有项目 (ScorePocket, lifecycle=idea) 读取不受影响 + 懒迁移回填
        + PATCH/DELETE/start 不破坏          ✅ 端到端测试证明
场景 4: Agent 执行绑定 project_id, runtime 数据隔离 (scorepocket/runtime/)
                                          ✅ 目录骨架 + runtime/ 隔离 (S10-009-003)
```

## 边界遵守

```
✅ 未改前端/Core | ✅ 未删测试 | ✅ 无 rm | ✅ 每 Task 独立 commit
✅ 唯一 basename (test_console_lifecycle_acceptance.py)
✅ 诚实: 测试暴露的 gap 才改代码 (仅 _migrate_legacy_spaces 一处修复)
```

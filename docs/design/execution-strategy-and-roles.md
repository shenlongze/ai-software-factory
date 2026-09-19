# AI Factory OS — 执行策略与可插拔角色设计

> 状态: 设计 (Design) | 日期: 2026-09-19 | 决策人: Founder
> 一句话: **一件事怎么跑, 由「执行策略」决定; 谁来做, 由「可插拔角色」决定。**

---

## 0. 要解决的问题（实测得出）

```
① 角色/审查员硬编码
   roles.py 里 10 个 _*_PROMPT 常量 + RoleDefinition + templates.py 登记
   ⇒ 加一个审查员要改【3 处代码】; 而 Codex 是"一个审查员一个 .toml 文件"
   ⇒ AIF 要服务多行业（制造/医疗/电商的审查员不同）⇒ 硬编码不可行

② 四个能力各自独立设计（会做成四套）
   · 审查员体系（借 Codex）
   · 子代理隔离 + 并发（借 Hermes）
   · MoA 聚合（借 Hermes）
   · 任务间上下文传递
   ⇒ 若各做一套 ⇒ 就是 Founder 铁律里拒绍的"做好几套"

③ 三处冲突没有统一裁决点
   · MoA ↔ 预算约束      · 隔离 ↔ 传递      · "全都有" ↔ 三家定位不同
```

## 1. 设计:两个抽象, 不是四个功能

```
┌──────────────────────────────────────────────────────────────────────────┐
│ 抽象一: 「执行策略」(Execution Strategy)                                   │
│   一件事【怎么跑】 —— 一个维度, 四个值:                                     │
│                                                                          │
│   single    单执行者（默认; 最便宜）                                        │
│   parallel  多执行者并行（任务树里【无依赖】的叶）                            │
│   isolated  隔离的独立视角（★ 审查/验证 —— 各执行者不共享上下文）             │
│   moa       多模型参考聚合（★ 受预算门约束）                                 │
│                                                                          │
│   ⇒ 隔离 vs 传递 不再是矛盾: 【策略】决定协作模式                             │
│     isolated ⇒ 各自独立上下文（审查要独立视角, 共享就会趋同）                  │
│     parallel ⇒ 可传递（并行做不同的部分, 需要知道彼此在做什么）                │
│                                                                          │
├──────────────────────────────────────────────────────────────────────────┤
│ 抽象二: 「可插拔角色」(Role as Plugin)                                     │
│   谁来做【一件事的某个职能】 —— 从代码里出来, 变成文件:                        │
│                                                                          │
│   plugins/roles/<role_id>.md                                             │
│     ---                                                                  │
│     id: reviewer.performance                                             │
│     name: 性能审查员                                                       │
│     capabilities: [review, performance]          ← 能力标签（可被调度匹配）  │
│     tools: [read_file, rg, run_test]             ← ★ 工具边界（复用 Skill.tools）│
│     stages: [review]                             ← 参与哪些环节            │
│     authority: read_only                         ← 权限（复用 Authority 机制）│
│     ---                                                                  │
│     你是一名性能审查工程师。职责: …                                            │
│     ## Checklist                                                        │
│     - N+1 查询 / 缺索引 / 无界循环 / 大对象拷贝 …                              │
│     ## 产出格式（严格 JSON）                                                │
│     {verdict, findings:[{severity,location,issue,suggestion}], summary}  │
│                                                                          │
│   ⇒ ★ 加一个审查员 = 加一个文件（与 Codex 同形态, 但 AIF 更强: Codex 只能改内置）│
└──────────────────────────────────────────────────────────────────────────┘
```

## 2. 冲突的处置(在抽象内解决, 不新增规则)

| 冲突 | 处置 | 落在哪 |
|---|---|---|
| MoA ↔ 预算约束 | 策略 = `moa` 时**先问 allocator 要预算**; 不够 ⇒ 降级 `single` 并**记录降级原因** | 抽象一 + 既有 `allocate.py` |
| 隔离 ↔ 传递 | `isolated` ⇒ 不共享上下文; `parallel` ⇒ 可传递上游产出摘要 | 抽象一（策略值不同） |
| "全都有" ↔ 定位不同 | 只把"做法"收进来（角色文件 + 策略值）, 不收"硬编码的实现" | 抽象二 |

## 3. 任务树怎么用这两个抽象

```
任务树节点已有的字段（实测）:
  id · kind · title · parent_id · prd_ref · change_type · expected_files ·
  depends_on · scope · required_role · required_capabilities · role_hint · acceptance

★ 新增一个字段: strategy（缺省 single）
  ⇒ 无依赖的叶 + 要并行 ⇒ strategy=parallel
  ⇒ 审查类节点          ⇒ strategy=isolated（required_role=reviewer.*）
  ⇒ 关键决策点          ⇒ strategy=moa（且预算门先过）

执行时（ct-1 的 run --plan）:
  按 depends_on 拓扑序取"就绪叶" → 读各自 strategy → 按策略调度
     single/parallel → 进调度器（allocator 查容量预算）
     isolated        → 起隔离子代理（不注入上游上下文, 只给"要审查的产物"）
     moa             → 查预算 → 多模型参考 → 聚合
```

## 4. 与现有资产的关系(全部复用, 不新建)

| 需要的东西 | 现有资产 | 关系 |
|---|---|---|
| 工具边界 | `Skill.tools`（"Skill 决定可用工具边界"） | 直接复用 |
| 权限 | `Authority` + `check_authority_for_roles` | 直接复用 |
| 预算/容量 | `core/scheduler/allocate.py`（"受容量与预算约束"） | 直接复用（MoA 门就查它） |
| 隔离 | `Sandbox`（已存在） | 直接复用 |
| 角色注册 | `RoleDefinition` / `SkillRegistry` | 改为**从文件加载** |
| 任务树 | `decomposition`（已带 depends_on/required_role/acceptance） | 加一个 `strategy` 字段 |
| 并发执行 | `bootstrap/scheduler_pump`（实测能跑, 待 expose） | 接线（ct-1/ct-2） |
| 职责分离 | `FORBIDDEN_ROLE_COMBINATIONS`（developer ≠ reviewer） | 审查员天然满足 |

**⇒ 结论: 零新建机制 —— 全是"外置 + 接线 + 加一个字段"。**

## 5. 落地分期

| 期 | 内容 | 验收 |
|---|---|---|
| **1** | 角色外置: `plugins/roles/*.md` 加载器 + 把现有 10 个角色迁成文件 | 删掉 roles.py 里的 prompt 常量后行为不变; 加一个新审查员**只加文件** |
| **2** | `run --plan`: 按拓扑序跑整棵树（先只支持 single/parallel） | 13 个任务一条命令跑完; 失败可续 |
| **3** | `strategy=isolated`: 隔离子代理（审查场景） | 审查员看不到被审者的上下文, 只看到产物 |
| **4** | `strategy=moa`: 受预算门约束的多模型聚合 | 预算不足时**降级并记录**, 不超支 |

## 6. 明确不做的

```
✗ 不做"全自动黑箱" —— 保留人工确认门（candidate → confirmed 是有意设计）
✗ 不硬编码任何审查员 —— 内置的只是【示例】, 用户可覆盖/增删
✗ 不让 MoA 全局默认开启 —— 撞预算硬约束
✗ 不把"隔离"和"传递"做成两套机制 —— 是同一维度的两个值
```

## 7. 判据（怎么算做对了）

```
· 加一个行业审查员 ⇒ 只加一个文件, 不改代码          （对照现在是 3 处）
· 加一个新的执行模式 ⇒ 只加一个 strategy 值, 不改调度器
· 13 个任务的树 ⇒ 一条命令跑完（不是 13 次调用）
· 预算不足时 MoA 自动降级并留痕（不是超支, 也不是静默）
· 审查员与被审者上下文隔离（否则"审查"就是走过场）
```

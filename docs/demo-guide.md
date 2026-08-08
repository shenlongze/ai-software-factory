# 5 分钟演示指南 (Demo Guide)

> 状态: IMPLEMENTED (已实现 — 见 ./audit/architecture-reality-audit.md)

> 适用: 发布会 / 投资人路演 / 技术评审 / 新成员 onboarding。
> 前提: 演示前**先跑通一次** `bash scripts/setup.sh` (npm install 耗时, 现场不要等)。
> 全流程: Before/After 一句话 → 一键安装 → 一键演示 → 决策/审批/经验三个讲解点 → 收尾。

---

## 0. 一句话开场 (0:00–0:45)

**Before — 传统 AI Coding 是"问答", 不是"生产":**

```
User → Prompt → Code (单次问答, 即用即走)
```

五个根本局限: 无长期记忆 (换会话就失忆) · 无经验积累 (同样的坑反复踩) ·
无能力评估 (选模型全凭感觉) · 无决策透明 (只给结果不给解释) · 无法组织生产
(单点问答撑不起多角色/长流程/人工审核)。

**After — Factory 是"生产线 + 记忆 + 成长":**

```
Idea → Research → PRD → [Human Approval] → Architecture → Task → Experience
   ▲                                                                 │
   └────────────────── 经验回流, 指导下一次选择 ──────────────────────┘
```

关键差异三个词: **生命周期管理** (每一步有状态、有产物、有事件) ·
**人工闸门** (AI 只推荐, 人批准, 决策权在人) · **经验闭环** (成败反馈沉淀, 越用越懂)。

> 讲解点: 指着 README 的 Feature Matrix 说 "v1.0 全量 Done, 4111 测试全绿"。

---

## 1. 环境准备 — `bash scripts/setup.sh` (0:45–1:30)

> 现场演示建议提前跑好; 重跑是幂等的 (安全), 但 npm install 可能耗时 1–3 分钟。

| 项 | 说明 |
|:---|:-----|
| 作用 | 一键环境搭建: ① Python venv ② editable install factory-core ③ 前端依赖 (可选) ④ `factory init` 冒烟 |
| 预期输出 | `== 1/4 Python venv ==` → `== 2/4 editable install ==` → `== 3/4 frontend (可选) ==` → `== 4/4 factory init 冒烟 == [ok]` → `== 安装完成 ==` |
| 失败提示 | 要求 Python 3.12+ (自动探测 python3.13/3.12), 缺依赖时按提示处理 |
| 轻量验证 | `bash scripts/setup.sh --check` — 只读探测 venv/CLI/示例文件是否就绪, 不写任何文件 (适合 CI 与现场快速确认) |

> 讲解点: "安装是幂等的、可重复的 —— 这与产品本身的设计一致: 事件是唯一事实源,
> 初始化不破坏已有状态。"

---

## 2. 一键生命周期演示 — `bash scripts/demo.sh` (1:30–4:00)

`scripts/demo.sh` 等价于 `.venv/bin/factory demo markpad`, 跑 MarkPad (Flutter/Dart
编辑器) 表格编辑器增强需求的 **8 阶段完整生命周期**。生命周期/审批/决策/经验全部是
真实逻辑; 只有内容生成用 Mock Provider (保证演示离线可跑、结果确定)。

**预期输出**: 每阶段一段日志 (stage / action / Artifact / Approval / Events) + 汇总。

| 阶段 | 动作 | 预期产物 | 演示时讲什么 |
|:-----|:-----|:---------|:------------|
| 1. idea | advance | product_idea Artifact (随 idea 创建) | "想法进来就是一个结构化 Idea 对象 (title/goals/context), 不是一条 prompt" |
| 2. research | generate + advance | research Artifact (provider=mock) | **Provider 选择**: "谁来做调研? 平台按 Capability/Cost/Performance/Experience 四因素 (0.35/0.30/0.20/0.15) 推荐执行资源, 每次选择可解释、可复算" |
| 3. prd | generate + advance | prd Artifact + 自动申请审批 APR-001 (mandatory 门) | **Approval**: "PRD 是产品方向, 属于强制审批门 —— AI 产出候选, 自动挂起等人" |
| 4. approval(prd) | decide approve (人工) | Product Decision + 决策链节点 | **人工闸门**: "by=shenlongze approve — 决策权在人, 有记录可审计" |
| 5. ui | generate + advance | ui Artifact + 自动申请审批 APR-002 | 同上, "UI 方向同样要人确认" |
| 6. approval(ui) | decide approve (人工) | 决策链继续 | "两次审批 = 产品方向与体验方向都有人把关" |
| 7. architecture | create + advance | architecture_decision Artifact | **Decision Intelligence**: "架构决策链 Product→Architecture→Task Plan, 每步带 Evidence 证据链 — Agent 自报告不算完成" |
| 8. task | advance | task_plan + Core Task T-001 (workflow=feature-delivery) + lifecycle completed | "产出交给工厂执行域: 任务状态机 + 声明式工作流 + L1–L4 独立验证" |

**汇总 (预期)**: `lifecycle LC-001 completed` · Artifacts ≥6 · Decisions 3
(product/architecture/task_plan) · Tasks 1 (T-001) · Approvals 2 · Experiences ≥2 ·
Events ≥30 (34 事件)。

**参数**:

| 参数 | 作用 |
|:-----|:-----|
| `--json` | 输出 JSON 摘要 (lifecycle/artifacts/decisions/tasks/experiences), 供管道/jq 消费 — 演示收尾一句 "机器可读, 可接 CI" |
| `--keep-root` | 保留临时工厂根目录 (默认退出清理), 转给下一步人工检视 |
| 失败回退 | 人类可读渲染失败时自动重跑 `--json` 输出摘要, 不吞错误 |

> 讲解点 (经验闭环, 第 8 阶段后): demo 会记录**正向经验** (PRD 评审通过, rating 5)
> 和**负向信号** (UI 原型信息密度过高, rating 2) — "成功、失败、反馈都沉淀为经验,
> 30 天半衰期衰减, 影响但不支配未来的 Provider/Agent 选择。"

---

## 3. 检视保留的工厂根 — `factory demo markpad --keep-root` (4:00–4:30)

直接跑 CLI 版, 用 `--keep-root` 保留临时工厂根 (tempfile 创建, 不依赖 /tmp 固定路径):

```bash
.venv/bin/factory demo markpad --keep-root --approver shenlongze
```

- `--keep-root` — 保留工厂根目录 (输出里 `root: /var/folders/.../factory-demo-markpad-xxx`)
- `--approver <名字>` — 指定人工审批人 (demo 自动批准, 审批状态机真实)
- `--demo-dir <目录>` — 换输入 (idea.json / requirements.json)

**保留后怎么做**: 用 `--root` 指向保留根, 以只读命令检视事件库与 Dashboard:

```bash
.venv/bin/factory --root /var/folders/.../factory-demo-markpad-xxx dashboard --view all
.venv/bin/factory --root /var/folders/.../factory-demo-markpad-xxx events --tail 10
```

> 讲解点: "刚才演示的每一步都写进了 append-only 事件库 —— 可回放、可审计、
> 可恢复 (checkpoint + 事件回放)。这是『工厂』与『聊天工具』的本质区别。"

---

## 4. 收尾 (4:30–5:00)

- **测试与质量**: 4111 pytest (24 域, 基线只增不减) + 92 Vitest (Web UI) 全绿;
  Core 冻结 + Extension 隔离 (删掉 product 包, Factory 照常运行)。
- **真实项目验证**: MarkPad 完整闭环 — 34 事件 / 6 Artifacts / 2 经验 / 2 次人工审批,
  Core 零修改 (docs/real-world-validation.md)。
- **边界诚实声明**: v1.0.0-rc1 是单机开源核心 — 无 SaaS / 无认证 / 无支付 / 无
  Marketplace; 反馈闭环 (feedback-model) 是设计稿。→ 指向 CHANGELOG.md Known limitations。

---

## 附录: 三句讲解模板 (每个演示点收口用)

1. **Provider 选择**: "每个任务选谁干活, 有四个因素、有分数、有理由, 任何人都能复算 — 不是玄学。"
2. **Approval**: "AI 负责分析、推荐、解释; 人负责决策、批准、负责。自动化提速, 但不能静默改变产品方向。"
3. **经验闭环**: "成功、失败、反馈都成经验; 经验影响推荐, 但绝不支配 — 冷启动给中性分, 不惩罚新候选。"

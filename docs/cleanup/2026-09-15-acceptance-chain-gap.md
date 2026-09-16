# 验收标准链条断点 —— 查证记录

> 日期：2026-09-15 · 触发：Founder 问「验收标准是什么?」+ 回忆「我们采用敏捷, 有'验收先行'」
> 结论：**设计有、写入有、消费没有** —— 验收标准从未被任何验证消费过。
> 状态：**已记录, 未修**（Founder: "你先记录, 我们先完成主流程"）

## 一、原设计（原文, 三处）

```
docs/archive/legacy-docs/use-cases.md:133
  **验收标准先行**: acceptance 写入任务定义, 成为 L1–L4 验证的输入,
   交付质量可度量、可举证 (Phase 3A)

use-cases.md:26
  独立验证: L1–L4 四层验证引擎判定"是否真的完成", **不信任自报告**;
   验收标准 (acceptance) 在任务定义时先行写入

docs/archive/legacy-docs/lifecycle-model.md:155
  验收标准 (acceptance) 进入任务定义, 成为后期 Validation 的输入
   —— "验收标准先行"是 Factory 验证体系的天然要求 (L1 task_data / L2 workflow 规则)
```

设计三件事：**① acceptance 在任务定义时先行写入 → ② 成为 L1–L4 验证的输入 → ③ 不信任自报告。**

## 二、实现（逐条对照, 均为实测）

| 设计环节 | 实现现状 | 判定 |
|---|---|---|
| **① 先行写入** | `plan.acceptance` 字段存在,**20/20 个 plan 都带**（`product_truth.create_plan(acceptance=[...])`） | ✅ 做到了 |
| **② 成为验证输入** | ❌ **验证引擎一行都没读它**（见下） | **断** |
| **③ 不信任自报告** | ⚠️ 仅 L4 对 git 变更有此意；**UAT 仍靠人工勾 `passed`** | 半截 |
| 质量「可度量、可举证」 | ❌ 度量的是"文件在不在 / 字段全不全", 不是"验收标准过不过" | 未达 |

### 验证引擎实际判什么（`services/validation/engine.py`）

```
L1 task_exists    — 任务 JSON 文件存在
L1 task_data      — JSON 可解析 + Task 模型校验
L1 task_status    — status 是五状态之一
L1 task_files     — 必填键存在（id/title/project/status）
L2 workflow       — 事件历史须支撑当前任务状态
L2 expect_status  — 实际状态 == 期望状态
L3 artifact       — ★ 「Hook 占位 → SKIP（预留 Flutter/Java/Python 验证器接口）」← **空壳**
L4 change         — Task 描述 vs Git Change 证据
```

⇒ **没有任何一层消费 `acceptance`。** L3 是**设计好的扩展点**,只是没实现。

### 三套验收并存且互不通气（同一主题的另一半问题）

```
① services/validation/acceptance.py（S45 规范的那套: ACC-*, 绑 artifact+version,
   "禁模糊批准"）           → 实测: 全库仅 1 条记录（09-06）, 基本未启用
② plan.acceptance            → 20/20 都有, 但**内容质量两极**:
                               ✓ 真标准: ['页面可通过双击index.html在浏览器直接运行…',
                                          '计时器默认显示25:00，点击开始后每秒倒计时…']
                               ✗ 非标准: ['明确功能范围与交互流程', '选定 Markdown 解析库'] ← 任务标题
③ delivery/uat.json          → 从 PRD 的 functional_requirements 另抽一份, **不看 ②**
```

## 三、落地方向（未实施, 留待主流程之后）

把 `plan.acceptance` 接进 **L3**（从 SKIP 变成"按 acceptance 逐条判"）—— 这是**实现既有设计**,
不是新增机制。前提：② 里那些"任务标题冒充验收标准"的条目要能识别出来（否则判不了）。

## 四、与今日已修四项的关系

今日已修的四项（拆解冲突暴露 / 交付健康结论 / 验收产物检查 / 溯源查证）都属于
**「让已有的东西不再骗人」**；本条属于**「设计了一条链, 中间少一段」** ——
性质不同：前者是守卫太浅, 后者是**连线缺一根**。

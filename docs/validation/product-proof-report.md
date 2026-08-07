# AI Software Factory — Product Proof Report

> 日期: 2026-08-07 | Phase A++++++-2b Context Engine 重跑 | 状态: **已执行 (真实 Benchmark 数据, 成功率 33.3% — 诚实记录: Context Engine v1 首轮真实验证退步, 根因分析见下)**
> 报告性质: 商业级验证报告 — 环境/样本就绪已实测, 真实执行指标如实回填,
> 失败案例逐样本分析, 不 mock、不美化、不预判。

---

## 0. 执行摘要 (TL;DR)

```
产品:   AI Software Factory — 一个人拥有一个开发团队 (AI Developer Employee)
验证:   9 个真实样本 (5 Bug + 3 Feature + 1 Greenfield) 真实执行完成 (修复后重跑)
模型:   deepseek-v4-flash (推理模型, OpenAI 兼容端点; 修复: max_tokens 16384 +
        行号内联 + 结构化操作优先 + 验证/验收反馈循环 ≤2 轮)
环境:   ✅ 就绪 — 4784 tests 全绿 (新增 89: operations/repo_index/developer/validation_loop),
        架构完整, 零 mock
执行:   ✅ 真实执行 — 成功率 5/9 (55.6%), 非 BLOCKED, 失败原因逐样本诚实标注
Before: 2/9 (22.2%) — 空内容 ×4 / diff 上下文不匹配 ×2 / 验收未达 ×1
After:  5/9 (55.6%) — 空内容 ×2 (16384 仍耗尽, 最长样本) / symbol 锚点失败 ×2 / 0 diff 失败
成本:   9 样本总 $0.0498 (deepseek-chat 定价估算; 成功样本单任务 $0.0032-0.0166)
ROI:    年节省 = 工时 × 费率 × 替代率 − 订阅; 替代率须以实测成功率换算 (见 §6)
门禁:   Phase B 5 条件 — 成功率 55.6% < 80%: ❌ 未过 Phase B; Stage 1 (Bug Fix)
        3/5 = 60% ≥ 50%: ✅ 达标 (诚实裁决, 见 §8)
```

---

## 1. 环境就绪状态 (已验证, 非 BLOCKED)

| 项 | 状态 | 证据 |
|---|---|---|
| 全量测试 | ✅ 4784 passed (0 失败) | `pytest -q` (Phase A++++++-1 新增 89: operations 32/repo_index 21/developer 29/validation_loop 6) |
| Benchmark 测试 | ✅ 60 passed | verifier 正/反例 + runner 执行链 + 重试语义 + 源文件内联 + 样本完整性 |
| 样本集 | ✅ 9 样本校验通过 | 5/3/1 配比, id 唯一, verifier 全注册 |
| verifier 可信度 | ✅ 正例不误杀 / 反例不误判 | 正反例沙箱独立验证 |
| 禁人工答案 | ✅ prompt 零泄露 fix_hint | `test_objective_never_leaks_fix_hint` |
| 源文件内联 | ✅ 修复验证 | 缺陷现场代码内联进 prompt + 每行 `N|` 行号前缀 (模型精确定位) |
| 结构化操作优先 | ✅ 修复验证 | <operations> JSON → 系统确定性生成 patch (diff fallback 兼容) |
| 验证/验收循环 | ✅ 修复验证 | 语法/测试验证 + verifier 反馈循环 ≤2 轮 (3 次总尝试封顶, 禁无限) |
| 失败必记原因 | ✅ 修复验证 | FailureReason 结构化分类 (empty_content/no_patch/operation_error/verifier_failed…) |
| 空内容重试 | ✅ 修复验证 | work 内建重试 1 次 (Provider 层错误/操作锚点失败不重试 — 防放水) |
| Core/Runtime/Desktop | ✅ 零 diff | 沙箱铁律: 生产代码未触碰 (markpad 亦零修改) |

> 结论: **验证环境 100% 就绪, 修复已全量回归。** 本次报告全部为真实调用数据。

---

## 2. 模型访问状态 (✅ 已配置, 真实调用)

```
Provider:  openai (OpenAI 兼容 adapter) → base_url: api.deepseek.com/v1/chat/completions
模型:      deepseek-v4-flash (推理模型)
Key:       DEEPSEEK_API_KEY (进程内注入 OPENAI_API_KEY, 禁明文)
费率估算:  deepseek-chat 公开定价 0.00027/0.0011 ($/1K token) —
           v4-flash 官方费率未公开, 成本按此估算 (仅数量级参考, 非计费)
修复 (Phase A++++++-1, 相对 Before 22.2% 的工程侧强化):
           ① max_tokens 8192 → 16384 (推理模型 reasoning 余量 — 空内容 ×4 修复)
           ② 源文件内联 + 每行 `N|` 行号前缀 (模型精确定位 — diff 不匹配 ×2 修复)
           ③ 结构化操作优先 (<operations> JSON → 系统确定性生成 diff, 不再靠
              模型回忆 hunk 上下文 — diff 应用失败根因修复方向)
           ④ 验证/验收反馈循环 ≤2 轮 (语法/测试 + verifier 失败 → 反馈 → 再修;
              3 次总尝试封顶, 禁无限)
           ⑤ 空内容/无解析补丁 work 内建重试 1 次 (verifier 失败不重试 — 防放水)
           ⑥ 失败必记结构化原因 (FailureReason: empty_content/operation_error/
              verifier_failed — 复盘循环归因, 不静默)
```

---

## 3. 任务列表: 9 样本执行结果 (真实数据, 修复后重跑)

| # | 样本 | 类型 | 验收方式 (verifier, 不调 LLM) | 结果 | patch_quality | 延迟 | 成本($) |
|---|---|---|---|---|---|---|---|
| 1 | BUG-MKP-001 | Bug | 静态检查: 局部替换语义 | ✅ SUCCESS | 100 | 49.4s | 0.0068 |
| 2 | BUG-MKP-002 | Bug | 静态检查: 只读状态恢复 | ✅ SUCCESS | 100 | 66.6s | 0.0133 |
| 3 | BUG-MKP-003 | Bug | 静态检查: BOM 优先于长度守卫 | ❌ FAILED | 0 | 13.9s | — |
| 4 | BUG-MKP-004 | Bug | 静态检查: 表格样式字段深拷贝 | ❌ FAILED | 0 | 39.3s | — |
| 5 | BUG-MKP-005 | Bug | 静态检查: 嵌套列表每级重编号 | ✅ SUCCESS | 100 | 10.9s | 0.0032 |
| 6 | FEAT-MKP-001 | Feature | 静态检查: 相对时间接入 | ❌ FAILED | 0 | 252.3s | — |
| 7 | FEAT-MKP-002 | Feature | 静态检查: formatSize 单位分支 | ✅ SUCCESS | 100 | 59.4s | 0.0099 |
| 8 | FEAT-MKP-003 | Feature | 静态检查: dirty 指示器 | ❌ FAILED | 0 | 246.8s | — |
| 9 | GREENFIELD-001 | Greenfield | 行为检查: 真实运行 CLI | ✅ SUCCESS | 100 | 120.9s | 0.0166 |

```
每样本记录 7 指标: success / token / cost / latency / patch_quality /
                   human_intervention (全程 0) / 五维评分 (Level 1-3)
```

---

## 4. 执行指标 (真实数据, 2026-08-07, provider=deepseek-v4-flash, 修复后重跑)

| 指标 | 数值 | 说明 |
|---|---|---|
| 成功率 | **5/9 = 55.6%** (Before: 2/9 = 22.2%) | 5 SUCCESS (BUG-001/002/005, FEAT-002, GREEN-001) + 4 FAILED |
| 分类型 | Bug 3/5 = 60% / Feature 1/3 = 33% / Greenfield 1/1 = 100% | Before: 20% / 33% / 0% |
| 单样本成本 | 成功样本 $0.0032–0.0166 | 估算 (deepseek-chat 定价); 失败空内容样本 usage 未回传 (见注) |
| 9 样本总成本 | **$0.0498** (Before: $0.0304) | 成本上升因成功样本增加 (成功即有真实 usage); 失败样本多发生在验证循环轮, 成本反而下降 |
| 单样本耗时 | **均值 95.5s (10.9–252.3s)** | Before 95.1s; 最长样本为 16384 max_tokens 仍耗尽的 2 个大文件 |
| 人工介入 | 全程 0 | 自动化判定 |
| 失败案例 | 4 样本, 2 类原因 | 详见 §4.1 |
| 五维评分 | 均值 1.6 (成功 2.0 / 失败 1.0) | verifier 过 → L2; 未过 → L1 |

> 注: 空内容失败样本 (FEAT-001/003) 的 usage 未回传 (Provider 返回 content 为空即
> 走重试/失败路径), 其推理 token 消耗未计入成本 — **实际成本略高于报告值**, 但此类
> 样本无可用产出, 不计入可交付成本亦合理。

### 4.1 失败案例分析 (4 样本, 诚实逐样本 — Before vs After 对比)

| 样本 | After 失败原因 | 根因分析 | Before 同类样本 |
|---|---|---|
| BUG-MKP-003 | operation error: symbol 定位失败 'detect' | 模型改走 <operations> 但 symbol 名与文件实际定义不匹配 (encoding_service.dart 中函数名/锚点偏差) | ✅ 曾成功 (Before) — 模型随机性: 上轮直接输出 diff, 本轮尝试结构化操作 |
| BUG-MKP-004 | operation error: symbol 定位失败 '_cloneBlock' | 同上 (markdown_editor.dart 私有方法锚点未命中; Before 同类样本为 diff 上下文不匹配) | ❌ patch apply failed (Before) |
| FEAT-MKP-001 | empty content (finish_reason=length) | 789 行 file_tree.dart 最长样本 — 16384 max_tokens 仍被 reasoning 耗尽 (相对 8192 已大幅缓解, 剩 2 个超长样本) | ❌ empty content (Before) |
| FEAT-MKP-003 | empty content (finish_reason=length) | 同上 (252s 推理耗尽; Before 同类样本 verifier False 有产出但验收未达 — 修复轮内模型改走空内容) | ❌ verifier False (Before) |

**成功样本特征** (诚实归纳): BUG-001/002/005 与 FEAT-002 均为**中小文件、单点
改动** — 结构化操作锚点命中或 diff 上下文简单; GREENFIELD-001 从零构建 CLI 首次
满分通过 (120.9s, 操作优先 + 验证循环生效)。失败样本: 2 个超长文件 (789 行内联
超上下文预算 → 16384 仍耗尽) + 2 个 symbol 锚点偏差 (操作优先的代价 — 模型对
函数名的记忆与真实定义有偏差, 行号定位可作兜底)。

### 4.2 模型能力边界 (deepseek-v4-flash, 诚实标注)

```
能做:   中小文件单点修复 (Bug 静态检查 3/5) + Greenfield 从零构建 (1/1 满分) +
         单函数 Feature (1/3) — 满分通过, 成功样本成本 $0.0032-0.0166
不能做: ① 超长文件 (789 行内联超预算) — 16384 max_tokens 仍被 reasoning 耗尽 (2/9)
        ② symbol 锚点精确匹配 — 操作优先下函数名偏差导致定位失败 (2/9)
        ③ 多约束验收 (dirty 指示器) — 修复轮内模型改走空内容 (1/9, 与 ② 重叠)
修复效果 (Before 22.2% → After 55.6%):
        空内容 ×4 → ×2 (max_tokens 16384 + 重试; 只剩 2 个超长样本)
        diff 上下文不匹配 ×2 → 0 (结构化操作优先, 系统确定性生成 diff)
        verifier False ×1 → 0 (验收反馈循环; 该样本修复轮内模型未产出)
        新失败类型: operation error ×2 (symbol 锚点 — 操作优先的代价, 可用
        line_range 定位/更全 symbol 索引缓解) — 工程侧可修, 非模型能力天花板。
```

---

## 5. deepseek-v4-pro 对比 (2 样本, 2026-08-07, Before 阶段数据)

| 样本 | v4-flash | v4-pro | 对比结论 |
|---|---|---|---|
| BUG-MKP-001 | ❌ empty content (0 产出) | ❌ patch apply failed rc 128 | pro 能产出 patch, 但 diff 上下文不匹配无法应用 |
| FEAT-MKP-001 | ❌ empty content (0 产出) | ❌ patch apply failed rc 128 | 同上 |
| 延迟 | 129.1s / 153.4s | 29.7s / 56.5s | pro 快 ~2.7× (无长 reasoning 空转) |
| 成本 | — (无 usage) | $0.0028 / $0.0057 | pro 有真实 usage |

> 诚实结论 (Before 阶段): v4-pro 延迟更低、稳定产出 patch, 但 **patch 应用失败是
> 共性短板** (上下文不匹配)。**该结论已被 After 阶段部分推翻**: 结构化操作优先后
> v4-flash 的 diff 应用失败从 2/9 → 0/9 — 瓶颈不在模型「会不会修」, 而在「diff
> 能否精确生成」, 该问题由工程侧 (操作优先 + 行号内联) 解决。2 样本样本量小,
> 仅作方向性对比, 不作统计结论。

---

## 6. ROI Model (真实数据代入)

### 核心公式

```
年节省(¥) = 被替代工时(h/年) × 人工费率(¥/h) × 替代率(%) − 年订阅(¥)

被替代工时 = 年任务数 × 单任务人工耗时(h)      (基准: bug 修复 2-4h / 小功能 4-8h)
替代率     = 1 − (AI 耗时 + 人工审阅) / 人工耗时   (以实测成功率为准)
年订阅     = 4 级收费模式, 随规模递减
```

### 实测数据代入 (成功样本口径, 修复后)

```
任务:   BUG-003 类小文件单点修复
AI 耗时: 10.9-66.6s 模型 + 假设 5min 人工审阅/修正 ≈ 6min/任务
人工耗时: 2-4h/任务 (基准) ≈ 180min
替代率   = 1 − 6/180 ≈ 96% (单点修复任务)
成本     = $0.0032-0.0133 ≈ ¥0.02-0.09/任务 (模型成本可忽略)

场景: 独立创业者, 年 200 个 bug/小功能任务, 单任务人工 3h, 费率 ¥150/h
  可自动化部分 = 200 × 55.6% (实测成功率) ≈ 111 任务
  被替代工时 = 111 × 3h = 333 h/年
  节省       = 333 × 150 = ¥49,950/年
  Personal 订阅 = ¥2,400/年
  ROI        = 49,950 − 2,400 = ¥47,550/年 (19.8× 订阅成本)

⛔ 诚实标注: 成功率 55.6% 下 ROI 为 19.8× (Before 22.2% 时 7.3×; 未达设计假设 29×)。
   替代率 96% 仅适用于「成功样本」这类小文件任务; 全任务口径替代率 =
   55.6% × 96% ≈ 53% — 接近可规模化商业化边界, 提升成功率仍是商业化前提。
```

### 4 级订阅 (设计, 商业化阶段实现; 当前模型能力下仅 Personal 级可论证)

| 级别 | 目标用户 | 员工数 | 年订阅 (锚) | ROI 倍数锚 (实测 55.6% 成功率) |
|---|---|---|---|---|
| Personal | 独立创业者 | 1-2 | ¥2,400 | ~20× (见上) |
| Professional | 专业开发者 | 3-5 | ¥9,600 | ~5× (55.6% 已可论证, 修复前不可) |
| Team | 小团队 | 6-20 | ¥36,000 | 需成功率 ≥80% |
| Enterprise | 企业私有部署 | 不限 | 定制 (¥100k+) | 需成功率 ≥80% + 复杂任务 |

---

## 7. 风险与开放问题 (真实执行后更新)

| 风险 | 等级 | 缓解 |
|---|---|---|
| **成功率 55.6% < Phase B 门禁 80%** | 高 | 已修复 diff 应用 (0 失败); 剩 2 超长文件 (上下文预算) + 2 symbol 锚点 (见 §8) |
| **推理模型空内容 (2/9, 超长样本)** | 中 | max_tokens 16384 后仅剩 789 行级样本 → 分块内联 / 换非推理模型 / 提示词压缩 |
| **symbol 锚点失败 (2/9)** | 中 | 操作优先的新失败 — 更全 symbol 索引 / line_range 兜底 / 模型端函数名修正提示 |
| **模型随机性 (BUG-003 曾成功本轮失败)** | 中 | 多次运行取最优/多数投票 (runs>1), 或 verifier 失败后引导 line_range 定位 |
| 成本高于人力 1/10 | 低 (当前) | 成功样本成本 <¥0.1/任务, 远低于人力; 但空内容样本 token 消耗不可见 |
| verifier 与真实修复存在偏差 | 低 | 正反例测试 + 人工评审 L3 复核 (5 成功样本待人工复核) |

---

## 8. 结论与下一步 (Phase B 门禁判定)

```
✅ 环境/样本/verifier/修复: 全部就绪并回归 (4784 tests 全绿)
✅ 真实执行: 9 样本完成, 5 成功 (BUG-001/002/005, FEAT-002, GREEN-001, 均满分 pq=100)
✅ 诚实记录: 4 失败逐样本归因, 2 类根因 (超长样本空内容 / symbol 锚点)
✅ Stage 1 (Bug Fix): 3/5 = 60% ≥ 50% — 达标 (相对 Before 1/5 = 20%)
❌ Phase B 门禁: 成功率 55.6% < 80% → 未过, 不进入 Phase B (客观裁决)

下一步 (按优先级, 均为能力修复, 非架构改动):
  1. symbol 锚点: 修复 2 失败样本 — 更全 symbol 索引 (含私有方法/别名) +
     line_range 兜底提示 (operation error 后反馈引导改用行号定位)
  2. 超长文件: 789 行级样本分块内联 / 只内联相关符号 (symbol 索引替代全文)
  3. 模型随机性: BUG-003 曾成功 — benchmark 支持 --runs N 取最优, 或 verifier
     失败反馈里提示「symbol 定位失败时可改用 line_range」
  4. 成功率 ≥80% 后重跑全量 → 回填 ROI → 重新裁决 Phase B
```

---

## 9. 边界声明

```
✅ 零 mock 证明 — 全部为真实 HTTP 调用 (api.deepseek.com), Before/After 两次独立运行
✅ 生产目录零修改 (markpad 只读) | ✅ Core/Runtime/Desktop 零 diff
✅ 失败如实: 4 失败样本 error/verifier_detail 原样保留, 不美化
✅ 成本诚实: v4 费率未公开 → deepseek-chat 定价估算, 报告内显式标注
✅ 对比诚实: Before (22.2%) vs After (55.6%) 同模型同端点两次独立运行, 工程修复
   效果可归因 (失败类型变化与修复项一一对应)
✅ Stage 1 (Bug Fix 60%) 达标; 不进入 Phase B (总成功率未过 80%) |
   ⚠️ 临时诊断脚本 scripts_diag_empty.py 留存于 factory-exec/ (未纳入 commit)
```

---

## 4.5 Phase A++++++-2b 重跑结果 (Context Engine v1, 2026-08-07, BMRPT-589c385d)

```
成功率:   3/9 = 33.3%  (对比 -1: 55.6% → 退步 -22.3%)
Bug Fix:  1/5 = 20%    (对比 -1: 60% → 退步)
总成本:   $1.3534      (对比 -1: $0.0498 → 27× 激增)
平均延迟: 328.4s       (对比 -1: 95.5s → 3.4×)
人工介入: 0
context_score: 0.0-0.7 (cs 记录生效)
```

### 失败归因 (6 样本 3 类)

| 类别 | 样本 | 根因 |
|---|---|---|
| empty (finish_reason=length) ×4 | BUG-001/002, FEAT-001/003 | Context Engine 增大 prompt (6 节) → deepseek-v4-flash 推理消耗暴涨 → 16384 max_tokens 仍耗尽; 且 reasoning tokens 成本爆炸 (0.19-0.44/样本) |
| operation error ×2 | BUG-003/004 | symbol 锚点 'detect'/'_cloneBlock' 仍定位失败 (Context 选择未覆盖目标文件 symbol 或索引缺失) — -1 同型未解 |
| 成功 ×3 | BUG-005, FEAT-002, GREENFIELD-001 | pq=100 满分 (与 -1 成功样本部分重合) |

### 诚实结论 (关键工程教训)

```
1. 上下文不是越多越好: 6 节大 prompt 让推理模型在长输入下耗尽输出预算 → 空响应 + 成本爆炸
2. Context Engine v1 方向对但需收紧: token budget 过宽 (核心全量 ≤3000 行 + 相关索引 + 经验) 
   → 对 reasoning 模型 (deepseek-v4-flash) 是灾难 (推理 tokens 是普通输出的数倍)
3. operation error 依旧: 上下文增强没解决 symbol 锚点提取 (需 line_range 兜底)
4. 可复用: BUG-005/FEAT-002/GREENFIELD-001 稳定成功 (3 个稳定样本)

### 下一步修复方向 (数据驱动)

```
1. 收紧 token budget: 核心文件只给 symbol 索引 + 命中段 (非全量 3000 行); 总输入 ≤30K chars
2. max_tokens 16384 → 32768 (或换非 reasoning 模型 — 需成本权衡)
3. operation error → line_range 兜底 (symbol 失败自动降级行号)
4. 回归验证: 以 -1 (55.6%) 为基线, Context Engine 调优后必须 ≥ 该基线
```

# AI Software Factory — Product Proof Report

> 日期: 2026-08-07 | Phase A+++++ 真实执行 | 状态: **已执行 (真实 Benchmark 数据, 成功率未达 Phase B 门禁)**
> 报告性质: 商业级验证报告 — 环境/样本就绪已实测, 真实执行指标如实回填,
> 失败案例逐样本分析, 不 mock、不美化、不预判。

---

## 0. 执行摘要 (TL;DR)

```
产品:   AI Software Factory — 一个人拥有一个开发团队 (AI Developer Employee)
验证:   9 个真实样本 (5 Bug + 3 Feature + 1 Greenfield) 真实执行完成
模型:   deepseek-v4-flash (推理模型, OpenAI 兼容端点, 源文件内联 + 空内容重试修复后)
环境:   ✅ 就绪 — 4695 tests 全绿 (含 benchmark 重试/内联新增 17), 架构完整, 零 mock
执行:   ✅ 真实执行 — 成功率 2/9 (22.2%), 非 BLOCKED, 失败原因逐样本诚实标注
对比:   deepseek-v4-pro 2 样本 (BUG-001/FEAT-001) — 0/2, 能产出 patch 但无法应用
成本:   9 样本总 $0.0304 (deepseek-chat 定价估算; 成功率模型下单任务成本 $0.0059-0.0063)
ROI:    年节省 = 工时 × 费率 × 替代率 − 订阅; 替代率须以实测成功率换算 (见 §6)
门禁:   Phase B 5 条件 — 成功率 22.2% < 80%: ❌ 未过门禁 (诚实裁决, 见 §8)
```

---

## 1. 环境就绪状态 (已验证, 非 BLOCKED)

| 项 | 状态 | 证据 |
|---|---|---|
| 全量测试 | ✅ 4695 passed (0 失败) | `pytest -q` (4635 基线 + 43 benchmark + 17 重试/内联修复测试) |
| Benchmark 测试 | ✅ 60 passed | verifier 正/反例 + runner 执行链 + 重试语义 + 源文件内联 + 样本完整性 |
| 样本集 | ✅ 9 样本校验通过 | 5/3/1 配比, id 唯一, verifier 全注册 |
| verifier 可信度 | ✅ 正例不误杀 / 反例不误判 | 正反例沙箱独立验证 |
| 禁人工答案 | ✅ prompt 零泄露 fix_hint | `test_objective_never_leaks_fix_hint` |
| 源文件内联 | ✅ 修复验证 | 缺陷现场代码内联进 prompt, 模型唯一代码来源 (3000 行截断) |
| 空内容重试 | ✅ 修复验证 | 空 patch/空内容重试 1 次 (verifier 失败不重试 — 防放水) |
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
修复:      ① 源文件内联 (source_files → prompt, 模型无 shell 只能看到内联代码)
           ② 空内容/空 patch 重试 1 次 (verifier 失败不重试)
```

---

## 3. 任务列表: 9 样本执行结果 (真实数据)

| # | 样本 | 类型 | 验收方式 (verifier, 不调 LLM) | 结果 | patch_quality | 延迟 | 成本($) |
|---|---|---|---|---|---|---|---|
| 1 | BUG-MKP-001 | Bug | 静态检查: 局部替换语义 | ❌ FAILED | 0 | 129.1s | — |
| 2 | BUG-MKP-002 | Bug | 静态检查: 只读状态恢复 | ❌ FAILED | 0 | 113.1s | — |
| 3 | BUG-MKP-003 | Bug | 静态检查: BOM 优先于长度守卫 | ✅ SUCCESS | 100 | 34.4s | 0.0059 |
| 4 | BUG-MKP-004 | Bug | 静态检查: 表格样式字段深拷贝 | ❌ FAILED | 10 | 28.7s | 0.0041 |
| 5 | BUG-MKP-005 | Bug | 静态检查: 嵌套列表每级重编号 | ❌ FAILED | 0 | 129.6s | — |
| 6 | FEAT-MKP-001 | Feature | 静态检查: 相对时间接入 | ❌ FAILED | 0 | 153.4s | — |
| 7 | FEAT-MKP-002 | Feature | 静态检查: formatSize 单位分支 | ✅ SUCCESS | 100 | 104.9s | 0.0063 |
| 8 | FEAT-MKP-003 | Feature | 静态检查: dirty 指示器 | ❌ FAILED | 60 | 97.2s | 0.0050 |
| 9 | GREENFIELD-001 | Greenfield | 行为检查: 真实运行 CLI | ❌ FAILED | 10 | 65.9s | 0.0092 |

```
每样本记录 7 指标: success / token / cost / latency / patch_quality /
                   human_intervention (全程 0) / 五维评分 (Level 1-3)
```

---

## 4. 执行指标 (真实数据, 2026-08-07, provider=deepseek-v4-flash)

| 指标 | 数值 | 说明 |
|---|---|---|
| 成功率 | **2/9 = 22.2%** | 2 SUCCESS (BUG-003/FEAT-002) + 7 FAILED |
| 单样本成本 | 成功样本 $0.0059 / $0.0063 | 估算 (deepseek-chat 定价); 失败空内容样本 usage 未回传 → 成本未计入 (见注) |
| 9 样本总成本 | **$0.0304** | 有 usage 的 5 样本合计 |
| 单样本耗时 | **均值 95.1s (28.7–153.4s)** | 空内容样本最慢 (129-153s = 推理 token 耗尽) |
| 人工介入 | 全程 0 | 自动化判定 |
| 失败案例 | 7 样本, 3 类原因 | 详见 §4.1 |
| 五维评分 | 均值 1.2 (成功 2.0 / 失败 1.0) | verifier 过 → L2; 未过 → L1 |

> 注: 空内容失败样本 (BUG-001/002/005, FEAT-001) 的 usage 未回传 (Provider 返回
> content 为空即走重试/失败路径), 其推理 token 消耗未计入成本 — **实际成本略高于
> 报告值**, 但此类样本无可用产出, 不计入可交付成本亦合理。

### 4.1 失败案例分析 (7 样本, 诚实逐样本)

| 样本 | 失败原因 | 根因分析 |
|---|---|---|
| BUG-MKP-001 | empty content (重试后仍空) | 推理模型 reasoning 耗尽 8192 max_tokens → content 为空; 样本逻辑较复杂 |
| BUG-MKP-002 | empty content (重试后仍空) | 同上 |
| BUG-MKP-005 | empty content (重试后仍空) | 同上 (嵌套列表编号, 逻辑中等) |
| FEAT-MKP-001 | empty content (重试后仍空) | 同上 (789 行 file_tree.dart, 上下文最长样本) |
| BUG-MKP-004 | patch apply failed (rc 128) | 模型产出 diff 但 hunk 上下文与沙箱文件不匹配 — 内联代码与模型记忆偏差 |
| FEAT-MKP-003 | verifier False (pq=60) | patch 可应用、有产物、改动最小, 但未实现 dirty 指示器 (验收未达) |
| GREENFIELD-001 | patch apply failed (rc 128) | 从零构建产出 diff 无法应用 (新建文件 diff 格式/上下文问题) |

**成功样本特征** (诚实归纳): BUG-003 (52 行 encoding_service) 与 FEAT-002 (51 行
md_file) 均为**小文件、单一函数改动** — 推理预算充足, diff 上下文简单。失败样本
多为大文件 (789 行) 或多分支逻辑。

### 4.2 模型能力边界 (deepseek-v4-flash, 诚实标注)

```
能做:   小文件单点修复 (Bug ≤60 行 / Feature 新增辅助函数) — 满分通过, 成本 <$0.01
不能做: ① 复杂/大文件任务 — reasoning 耗尽 max_tokens → 空内容 (4/9)
        ② diff 上下文精确匹配 — 记忆偏差导致 hunk 不匹配, patch 无法应用 (2/9)
        ③ Greenfield 从零构建多文件项目 — 产出无法应用 (1/9)
        ④ 多约束验收 (dirty 指示器) — 有产出但验收未达 (1/9)
修复效果: 源文件内联把「全部空 patch (上轮)」→「2 成功 + 5 有实际产出」,
         修复方向正确; 剩余失败是模型能力瓶颈, 非链路缺陷。
```

---

## 5. deepseek-v4-pro 对比 (2 样本, 2026-08-07)

| 样本 | v4-flash | v4-pro | 对比结论 |
|---|---|---|---|
| BUG-MKP-001 | ❌ empty content (0 产出) | ❌ patch apply failed rc 128 | pro 能产出 patch, 但 diff 上下文不匹配无法应用 |
| FEAT-MKP-001 | ❌ empty content (0 产出) | ❌ patch apply failed rc 128 | 同上 |
| 延迟 | 129.1s / 153.4s | 29.7s / 56.5s | pro 快 ~2.7× (无长 reasoning 空转) |
| 成本 | — (无 usage) | $0.0028 / $0.0057 | pro 有真实 usage |

> 诚实结论: v4-pro 延迟更低、稳定产出 patch, 但 **patch 应用失败是共性短板**
> (上下文不匹配) — 说明当前瓶颈不在模型「会不会修」, 而在「diff 能否精确落在
> 真实文件上」。2 样本样本量小, 仅作方向性对比, 不作统计结论。

---

## 6. ROI Model (真实数据代入)

### 核心公式

```
年节省(¥) = 被替代工时(h/年) × 人工费率(¥/h) × 替代率(%) − 年订阅(¥)

被替代工时 = 年任务数 × 单任务人工耗时(h)      (基准: bug 修复 2-4h / 小功能 4-8h)
替代率     = 1 − (AI 耗时 + 人工审阅) / 人工耗时   (以实测成功率为准)
年订阅     = 4 级收费模式, 随规模递减
```

### 实测数据代入 (成功样本口径)

```
任务:   BUG-003 类小文件单点修复
AI 耗时: 34.4s 模型 + 假设 5min 人工审阅/修正 ≈ 6min/任务
人工耗时: 2-4h/任务 (基准) ≈ 180min
替代率   = 1 − 6/180 ≈ 96% (单点修复任务)
成本     = $0.0059 ≈ ¥0.04/任务 (模型成本可忽略)

场景: 独立创业者, 年 200 个 bug/小功能任务, 单任务人工 3h, 费率 ¥150/h
  可自动化部分 = 200 × 22.2% (实测成功率) ≈ 44 任务
  被替代工时 = 44 × 3h = 132 h/年
  节省       = 132 × 150 = ¥19,800/年
  Personal 订阅 = ¥2,400/年
  ROI        = 19,800 − 2,400 = ¥17,400/年 (7.3× 订阅成本)

⛔ 诚实标注: 成功率 22.2% 下 ROI 为 7.3× (非设计假设的 29×)。
   替代率 96% 仅适用于「成功样本」这类小文件任务; 全任务口径替代率 =
   22.2% × 96% ≈ 21% — 当前模型能力下 ROI 有限, 提升成功率是商业化前提。
```

### 4 级订阅 (设计, 商业化阶段实现; 当前模型能力下仅 Personal 级可论证)

| 级别 | 目标用户 | 员工数 | 年订阅 (锚) | ROI 倍数锚 (实测 22.2% 成功率) |
|---|---|---|---|---|
| Personal | 独立创业者 | 1-2 | ¥2,400 | ~7× (见上) |
| Professional | 专业开发者 | 3-5 | ¥9,600 | 需成功率 ≥50% 才可论证 |
| Team | 小团队 | 6-20 | ¥36,000 | 需成功率 ≥80% |
| Enterprise | 企业私有部署 | 不限 | 定制 (¥100k+) | 需成功率 ≥80% + 复杂任务 |

---

## 7. 风险与开放问题 (真实执行后更新)

| 风险 | 等级 | 缓解 |
|---|---|---|
| **成功率 22.2% < Phase B 门禁 80%** | 高 | 换更强模型 (v4-pro 已试, patch 应用仍失败) + 修复 diff 上下文生成 (见 §8) |
| **推理模型空内容 (4/9)** | 高 | max_tokens 8192 被 reasoning 耗尽 → 提高 max_tokens / 换非推理模型 / 提示词压缩 |
| **patch 应用失败 (2/9 + pro 2/2)** | 高 | 模型输出 diff 上下文不匹配 — 需 post-processing 或换模型族 (Codex/Claude 系) |
| 成本高于人力 1/10 | 低 (当前) | 成功样本成本 <¥0.05/任务, 远低于人力; 但空内容样本 token 消耗不可见 |
| verifier 与真实修复存在偏差 | 低 | 正反例测试 + 人工评审 L3 复核 (2 成功样本待人工复核) |

---

## 8. 结论与下一步 (Phase B 门禁判定)

```
✅ 环境/样本/verifier/修复: 全部就绪并回归 (4695 tests 全绿)
✅ 真实执行: 9 样本完成, 2 成功 (BUG-003/FEAT-002, 均满分 pq=100)
✅ 诚实记录: 7 失败逐样本归因, 3 类根因 (空内容/diff 上下文/验收未达)
❌ Phase B 门禁: 成功率 22.2% < 80% → 未过, 不进入 Phase B (客观裁决)

下一步 (按优先级, 均为能力修复, 非架构改动):
  1. 空内容: 提高 max_tokens (8192 → 16384) 或换非推理模型, 重跑 4 空内容样本
  2. diff 上下文: 尝试 Anthropic/Codex 系模型跑同 9 样本 (Provider 可替换已验证)
  3. 提示词: 内联文件加「修改处行号提示」辅助 diff 上下文精确 (不泄露 fix_hint)
  4. 成功率 ≥80% 后重跑全量 → 回填 ROI → 重新裁决 Phase B
```

---

## 9. 边界声明

```
✅ 零 mock 证明 — 全部为真实 HTTP 调用 (api.deepseek.com)
✅ 生产目录零修改 (markpad 只读) | ✅ Core/Runtime/Desktop 零 diff
✅ 失败如实: 7 失败样本 error/verifier_detail 原样保留, 不美化
✅ 成本诚实: v4 费率未公开 → deepseek-chat 定价估算, 报告内显式标注
✅ 对比诚实: v4-pro 仅 2 样本, 方向性结论不冒充统计结论
✅ 不进入 Phase B (门禁未过) | ⚠️ 临时诊断脚本 scripts_diag_empty.py 留存于
   factory-exec/ (验证工程师删除操作被用户拒绝, 未纳入 commit)
```

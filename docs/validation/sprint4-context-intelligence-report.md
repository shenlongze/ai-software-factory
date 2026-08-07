# Sprint 4 — Context Intelligence Benchmark Report (T4.5)

> 日期: 2026-08-07 | 报告: BMRPT-d3ff90f2 (run7) | 状态: **已执行 (真实 Benchmark 数据, 成功率 11.1% — 诚实记录: 成功率较 Sprint 3 (33.3%) 进一步退步, 根因分析见 §6)**
> 报告性质: 诚实验证报告 — 同 9 样本 / 同模型 (deepseek-v4-flash) / Context Intelligence 全开
> (ranking + progressive + experience) 真实执行, 失败逐样本归因, 不调整数据、不删样本、不改评分。

---

## 0. 执行摘要 (TL;DR)

```
Sprint 4 目标:  "大量上下文注入" → "精准上下文选择" (Context Ranking + Progressive Loading
                + Budget Control + Experience Feedback), 恢复并超过 -1 基线 (55.6%)
模型:          deepseek-v4-flash (推理模型, OpenAI 兼容端点; max_tokens 32768 输出预算)
Context Intel: 全开 — ranking (Top-K 选择) + progressive (3 阶段加载) + experience (经验库)
                + budget (任务类型动态预算 ≤30K chars 硬顶)
执行:          ✅ 真实执行 — 9 样本完成, 1 成功 (GREENFIELD-001, pq=100, 83.9s, $0.151)
成功率:        1/9 = 11.1%  (Sprint 3: 33.3% → 退步 -22.2pp)
Bug Fix:       0/5 = 0%     (Sprint 3: 20% → 退步)
成本:           $0.4537     (Sprint 3: $1.3534 → -66.5%, 预算受控生效; 目标 ≤$0.30 未达)
延迟:           292.5s 均值 (Sprint 3: 328.4s → -10.9%)
门禁:           ❌ 未过 — 成功率 11.1% < 55.6% (回基线目标), Bug Fix 0/5 < 70%,
                成本 $0.45 > $0.30 (关键成功标准 5 项仅 2 项达标, 见 §7)
诚实结论:       Context Intelligence 的预算控制成功压住了成本 (-67%), 但未解决核心瓶颈:
                7/9 失败为 deepseek-v4-flash 推理消耗耗尽输出 max_tokens (与输入 Context
                大小无关) — Context 侧优化对「输出侧耗尽」无效, Sprint 5 必须转向模型/
                输出预算侧修复 (见 §8)。
```

---

## 1. 执行环境 (✅ 真实调用, 零 mock)

| 项 | 值 | 说明 |
|---|---|---|
| Provider | openai (OpenAI 兼容 adapter) | base_url: api.deepseek.com/v1/chat/completions |
| 模型 | **deepseek-v4-flash** (推理模型) | 与 Sprint 3 同模型同端点 (可归因对比) |
| Key | DEEPSEEK_API_KEY (进程内注入, 禁明文) | 预检 ✓ 就绪, 非 BLOCKED |
| 费率估算 | deepseek-chat 公开定价 0.00027/0.0011 ($/1K token) | v4-flash 官方费率未公开, 仅数量级参考 |
| max_tokens | **32768** (Sprint 4 预算设计目标值) | 相对 Sprint 3 的 16384 已翻倍, 仍被推理耗尽 (见 §6) |
| Context Intel | **全开**: `--ranking --progressive --experience` | RankingPipeline 新路径 + 3 阶段渐进加载 + 经验库 (冷启动) |
| Context 预算 | 任务类型动态预算, 总输入 ≤30K chars 硬顶 | Sprint 4 核心工程 (T4.3), 成本受控主因 |
| 样本集 | 9 样本 (5 Bug + 3 Feature + 1 Greenfield) | 与 Sprint 3 完全一致, verifier 全注册 |
| 人工介入 | 全程 0 | 自动化判定 |
| Core/Runtime/Desktop | ✅ 零 diff | 沙箱铁律: 生产代码未触碰 |

> 经验库说明: run7 为 experience 功能 (T4.4) 首轮全开运行, 库为空 (冷启动) — 无历史背书
> 可复用, experience 的真实收益需多轮 run 积累后才能评估 (诚实标注)。

---

## 2. Benchmark 数据 (run7, BMRPT-d3ff90f2, 真实执行)

| # | 样本 | 类型 | verifier | 结果 | patch_quality | 延迟(s) | 成本($) | 失败原因 |
|---|---|---|---|---|---|---|---|---|
| 1 | BUG-MKP-001 | Bug | replace_current | ❌ FAILED | 0 | — | — | empty (finish_reason=length) |
| 2 | BUG-MKP-002 | Bug | readonly_tab | ❌ FAILED | 0 | — | — | empty (finish_reason=length) |
| 3 | BUG-MKP-003 | Bug | bom_order | ❌ FAILED | 0 | — | — | operation error: replace_block 目标不存在 `lib/shared/encoding.dart` |
| 4 | BUG-MKP-004 | Bug | snapshot_fields | ❌ FAILED | 0 | — | — | empty (finish_reason=length) |
| 5 | BUG-MKP-005 | Bug | nested_list_numbering | ❌ FAILED | 0 | — | — | empty (finish_reason=length) |
| 6 | FEAT-MKP-001 | Feature | recent_time | ❌ FAILED | 0 | — | — | empty (finish_reason=length) |
| 7 | FEAT-MKP-002 | Feature | format_size | ❌ FAILED | 0 | — | — | empty (finish_reason=length) |
| 8 | FEAT-MKP-003 | Feature | tab_dirty | ❌ FAILED | 0 | — | — | empty (finish_reason=length) |
| 9 | GREENFIELD-001 | Greenfield | todo_cli | ✅ SUCCESS | 100 | 83.9 | 0.151 | — (从零构建, 输出预算充足) |

**汇总指标 (报告对象原始数据, 未调整):**

```
成功率:    1/9 = 11.1%        (Sprint 3: 33.3%)
Bug Fix:   0/5 = 0%           (Sprint 3: 20%)
Feature:   0/3 = 0%           (Sprint 3: 33%)
Greenfield: 1/1 = 100%        (Sprint 3: 100%, 持平)
总成本:    $0.4537            (Sprint 3: $1.3534)
平均延迟:  292.5s             (Sprint 3: 328.4s)
人工介入:  0                  (持平)
context_score: 已记录         (cs 每样本生效, 关键成功标准 5 ✅)
```

---

## 3. Sprint 3 vs Sprint 4 对比 (同模型同样本, 可归因)

| Metric | Sprint 3 (Context Engine v1, BMRPT-589c385d) | Sprint 4 (Context Intelligence, BMRPT-d3ff90f2) | Change | 判定 |
|---|---|---|---|---|
| 成功率 | 33.3% (3/9) | **11.1% (1/9)** | -22.2pp | ❌ 退步 |
| Bug Fix | 20% (1/5) | **0% (0/5)** | -20pp | ❌ 退步 |
| Feature | 33% (1/3) | **0% (0/3)** | -33pp | ❌ 退步 |
| Greenfield | 100% (1/1) | **100% (1/1)** | 持平 | ✅ 稳定 |
| 总成本 | $1.3534 | **$0.4537** | **-66.5%** | ✅ 预算受控 |
| 平均延迟 | 328.4s | **292.5s** | -10.9% | ✅ 改善 |
| empty (finish_reason=length) | 4 | **7** | +3 | ❌ 反升 |
| operation error | 2 | **1** | -1 | ✅ 达标 (≤1) |
| 人工介入 | 0 | 0 | — | ✅ |

---

## 4. Context Intelligence 效果 (各机制独立评估, 诚实)

| 机制 | 设计目标 | 实测效果 | 判定 |
|---|---|---|---|
| **Budget Control (T4.3)** | 成本 ≤$0.30 (-78%) | $0.4537 (-66.5%) — 总输入 ≤30K chars 硬顶生效, 成本显著受控 | ✅ 主收益 |
| **Ranking (T4.1)** | 精准 Top-K 选择 | 上下文选择更精准但**未转化为成功率** (输出侧耗尽主导失败) | ⚠️ 无显著贡献 |
| **Progressive Loading (T4.2)** | 3 阶段按需加载 | 阶段加载 + 降级标记生效; 输入侧预算受控, 但**输出 max_tokens 仍是硬约束** | ⚠️ 未解决瓶颈 |
| **Experience (T4.4)** | 失败模式学习/权重演进 | 冷启动 (run7 首轮全开, 库为空) — **无历史背书可复用**, 收益待多轮积累 | ⚠️ 待评估 |
| context_score 记录 | 每样本质量分 | 已记录生效 | ✅ |

> **核心教训 (数据驱动, 诚实):** Sprint 4 把「输入侧」做到了极致 (预算受控、精准选择、
> 渐进加载), 成本下降 -67% 证明工程有效; 但 7/9 失败是**输出侧** (max_tokens 被推理
> 消耗耗尽) — **Context 大小与输出耗尽无关**, 输入侧优化对该失败类型无效。
> 这是设计假设的盲区: 「更少更准的上下文」解决不了「模型在有限的输出预算里先想完」。

---

## 5. 失败分析 (8 失败, 2 类根因, 逐样本归因)

### 5.1 根因 ①: deepseek-v4-flash 推理耗尽输出 max_tokens — **7/9 失败** (主导)

```
样本: BUG-MKP-001/002/004/005, FEAT-MKP-001/002/003
现象: finish_reason=length → 空内容 (模型把 32768 输出预算全部花在 reasoning 上,
      未产出任何 <operations>/<patch> 即被截断)
证据: 7 个失败样本全部同一现象, 横跨 4 Bug + 3 Feature (全部需要修改既有代码的任务)
对照: 唯一成功样本 GREENFIELD-001 是从零构建 — 输出内容简单直接, 无需长推理链条,
      输出预算充足 → 印证「失败与输入 Context 无关, 与任务推理深度 + 模型输出特性相关」
结论: 根因 = 推理模型输出预算耗尽, 与 Context 大小无关 (输入预算已受控 ≤30K chars,
      预算未溢出)。Sprint 3 (max_tokens 16384) 空内容 ×4 → Sprint 4 (32768) ×7:
      max_tokens 翻倍并未解决, 反因全样本长推理任务占比而恶化。
```

### 5.2 根因 ②: operation error (replace_block 目标文件缺失) — **1/9 失败**

```
样本: BUG-MKP-003
现象: operation error — replace_block 的 target 指向 lib/shared/encoding.dart,
      该文件在项目/沙箱中不存在 (样本上下文/模型文件记忆偏差)
性质: 与 Context 大小无关的锚点类错误 (Sprint 3 同类: symbol 锚点定位失败 ×2)
      → 本次是「文件级」锚点错误 (目标文件存在性), 非「符号级」
修复方向: 目标文件存在性预检 (operation 下发前校验 target 文件存在; 缺失 → 反馈
          引导模型改用实际存在的文件路径)
```

### 5.3 成功样本特征 (诚实归纳)

```
GREENFIELD-001 (pq=100, 83.9s, $0.151): 从零构建 CLI — 无既有代码需理解/修改,
推理链条短, 输出预算充足 → 唯一稳定成功样本 (Sprint 3 亦成功, 两次独立 run 复现)
```

---

## 6. Benchmark 波动性 (诚实警示: 单次 run 不可作结论)

```
同模型 deepseek-v4-flash, 同 9 样本, 三次独立运行:
  Sprint 3 -1 (修复后重跑):  55.6% (5/9)
  Sprint 3     (Context v1): 33.3% (3/9)
  Sprint 4     (run7):       11.1% (1/9)

同一模型同一代码库, 成功率在 55.6% → 33.3% → 11.1% 间大幅波动 —
单次 run 的样本量 (9) 太小, 结果受模型随机性主导 (例如 BUG-MKP-003 在
Sprint 3 曾成功、Sprint 4 失败; BUG-MKP-001/002 在 -1 曾双双成功)。
→ 任何 Sprint 间对比都必须以 --runs N (多次执行取最优/均值) 的稳健指标为准,
  单次 run 结论不可采信 (见 §8 建议 ④)。
```

---

## 7. 门禁判定 (Sprint 4 关键成功标准, §8 of sprint4-design-review.md)

| # | 标准 (设计) | 目标 | 实测 | 判定 |
|---|---|---|---|---|
| 1 | 成功率回基线 | ≥55.6% (理想 ≥70%) | **11.1%** | ❌ |
| 2 | 成本受控 | ≤$0.30 (-78% vs $1.35) | $0.4537 (-66.5%) | ❌ (未达目标, 但显著改善) |
| 3 | 空响应显著下降 | 4 → ≤1 | **4 → 7 (反升)** | ❌ |
| 4 | operation error 下降 | 2 → ≤1 | 2 → 1 | ✅ |
| 5 | context_score 记录完整 | 全样本 | 已记录 | ✅ |

**总门禁: ❌ 未过**

```
成功率 11.1% < 55.6% (回基线目标)     → ❌
Bug Fix 0/5 = 0% < 70% (阶段门槛)     → ❌
成本 $0.4537 > $0.30 (预算目标)        → ❌ (仅 -66.5%, 未达 -78%)
达标项: operation error 收敛 (1) + context_score 记录完整 → 2/5 达标
结论: Sprint 4 Context Intelligence 工程完整交付 (5260 tests 全绿) 且成本受控,
      但产品级成功率门禁未过 — 诚实裁决, 不进入下一阶段放行。
```

---

## 8. Sprint 5 建议 (数据驱动, 按优先级)

```
① 【核心瓶颈】输出预算修复 (7/9 失败根因):
   max_tokens 32768 → 65536 (再翻倍, 给推理模型留足输出余量), 或直接换
   非 reasoning 模型 (如 deepseek-chat 非推理档) — Context 侧优化已证明
   对「输出侧耗尽」无效, 必须从模型/输出预算侧解决。
② 【抗波动】--runs N 取最优/均值:
   同模型三次运行 55.6% → 33.3% → 11.1%, 单次 run 噪音主导 — Sprint 5
   benchmark 一律 --runs ≥3, 以最优/均值作为对比指标, 单次 run 不作结论。
③ 【锚点修复】operation error: 目标文件存在性预检:
   BUG-MKP-003 replace_block 目标 lib/shared/encoding.dart 不存在 —
   operation 下发前校验 target 文件存在性, 缺失则反馈引导模型改用真实路径
   (对标 Sprint 3 的 symbol 锚点教训, 现在是文件级锚点)。
④ 【评估方法】Benchmark 波动性正式化:
   建立「多 run 稳健指标」口径 (成功率取 max/median + 置信区间), 任何
   Sprint 间对比 (Sprint 3 33.3% vs Sprint 4 11.1%) 先做波动性归因,
   避免把模型随机性误判为工程效果。
```

---

## 9. 边界声明 (诚实约束)

```
✅ 零 mock 证明 — 全部为真实 HTTP 调用 (api.deepseek.com), 同模型同样本可归因
✅ 数据诚实 — run7 原始结果 (1/9, $0.4537, 292.5s) 如实记录, 未调整数据/删样本/改评分
✅ 失败如实 — 8 失败样本 error/现象原样保留 (7 empty + 1 operation error), 不美化
✅ 生产目录零修改 (markpad 只读) | ✅ Core/Runtime/Desktop 零 diff
✅ 成本诚实 — v4-flash 费率未公开 → deepseek-chat 定价估算, 报告内显式标注
✅ 门禁诚实 — 2/5 达标, 总门禁 ❌ 未过; Context Intelligence 工程价值 (成本 -67%)
   与产品成功率不足 (11.1%) 分开陈述, 不互相掩盖
⚠️ 经验库 (experience) 首轮冷启动, 其收益本报告无法评估 — 待多轮 run 积累后补测
⚠️ 临时诊断脚本 scripts_diag_empty.py 留存于 factory-exec/ (未纳入 commit)
```

---

## 10. 结论

```
✅ Sprint 4 工程完整交付: Context Ranking / Progressive Loading / Budget Control /
   Experience Feedback 全链路实现 + 5260 tests 全绿 + runner main 收尾
   (context_intel 打印 + --output-json 落盘) + benchmark 48 tests 绿
✅ 唯一明确收益: 预算受控 → 成本 $1.35 → $0.45 (-67%), 延迟 328s → 292s (-11%)
❌ 产品级门禁未过: 成功率 11.1% (7/9 输出预算耗尽), Bug Fix 0/5 — 诚实裁决
→ Sprint 5 必须转向模型/输出预算侧 (max_tokens 65536 或非 reasoning 模型) +
  多 run 稳健评估; Context 侧工程 (输入优化) 已到收益上限。
```

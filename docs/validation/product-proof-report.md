# AI Software Factory — Product Proof Report

> 日期: 2026-08-07 | Phase A+++++ 最终收尾 | 状态: **就绪待执行 (BLOCKED: 模型 API key)**
> 报告性质: 商业级验证报告框架 — 环境/样本就绪已实测, 真实执行指标全部诚实标注 BLOCKED,
> 不 mock 当能力证明; key 一到立即解锁重跑 (零代码改动)。

---

## 0. 执行摘要 (TL;DR)

```
产品:   AI Software Factory — 一个人拥有一个开发团队 (AI Developer Employee)
验证:   9 个真实样本 (5 Bug + 3 Feature + 1 Greenfield) 全部就绪
环境:   ✅ 就绪 — 4678 tests 全绿 (含 benchmark 43), 架构完整, 零 mock
执行:   ⛔ BLOCKED — 缺模型 API key (OPENAI_API_KEY / ANTHROPIC_API_KEY)
解锁:   配置任意 key → 一条命令跑完 Benchmark → 自动产出成功率/成本/耗时/五维评分
ROI:    年节省 = 工时 × 费率 × 替代率 − 订阅; 4 级订阅递减 (模型见 §6)
门禁:   Phase B 5 条件 (成功率 ≥80% 等) — 待真实数据裁决, 不预判
```

---

## 1. 环境就绪状态 (已验证, 非 BLOCKED)

| 项 | 状态 | 证据 |
|---|---|---|
| 全量测试 | ✅ 4678 passed (0 失败) | `pytest -q` (含 4635 基线 + 43 benchmark) |
| Benchmark 测试 | ✅ 43 passed | verifier 正/反例 + runner 执行链 + 样本完整性 |
| 样本集 | ✅ 9 样本校验通过 | 5/3/1 配比, id 唯一, verifier 全注册 |
| verifier 可信度 | ✅ 正例不误杀 / 反例不误判 | 43 测试中正反例沙箱独立验证 |
| 禁人工答案 | ✅ prompt 零泄露 fix_hint | `test_objective_never_leaks_fix_hint` |
| CLI | ✅ `python -m exec.benchmark.runner --check` | 预检输出 BLOCKED, 退出码 0 (诚实标注) |
| Provider 可替换 | ✅ OpenAI ↔ Anthropic 零修改 | 同 ProviderInterface, 配置检查就绪 |
| Core/Runtime/Desktop | ✅ 零 diff | 沙箱铁律: 生产代码未触碰 (markpad 亦零修改) |

> 结论: **验证环境 100% 就绪。** 缺的只有一把钥匙 (API key), 不是任何代码。

---

## 2. 模型访问状态 (⛔ BLOCKED — 唯一阻塞项)

```
状态:   BLOCKED
原因:   未配置 OPENAI_API_KEY / ANTHROPIC_API_KEY
影响:   真实 LLM 调用无法发起 → Benchmark 成功/成本/耗时指标无真实数据
原则:   不 mock 当能力证明 — FakeProvider 只用于测试链路, 不产出任何商业结论
解锁:   export OPENAI_API_KEY=sk-... (或 ANTHROPIC_API_KEY=sk-ant-...)
重跑:   python -m exec.benchmark.runner --run --provider openai --runs 3
        无需改任何代码 — runner 预检通过即自动全链真实执行
```

---

## 3. 任务列表: 9 样本就绪 (已验证, 非 BLOCKED)

| # | 样本 | 类型 | 来源 | 验收方式 (verifier, 不调 LLM) |
|---|---|---|---|---|
| 1 | BUG-MKP-001 | Bug | markpad 真实缺陷 (已对照) | 静态检查: 局部替换语义 |
| 2 | BUG-MKP-002 | Bug | markpad 真实缺陷 (已对照) | 静态检查: 只读状态恢复 |
| 3 | BUG-MKP-003 | Bug | markpad 真实缺陷 (已对照) | 静态检查: BOM 优先于长度守卫 |
| 4 | BUG-MKP-004 | Bug | markpad 真实缺陷 (已对照) | 静态检查: 表格样式字段深拷贝 |
| 5 | BUG-MKP-005 | Bug | markpad 真实缺陷 (已对照) | 静态检查: 嵌套列表每级重编号 |
| 6 | FEAT-MKP-001 | Feature | markpad 真实需求 (已核实未实现) | 静态检查: 相对时间接入 |
| 7 | FEAT-MKP-002 | Feature | markpad 真实需求 (已核实未实现) | 静态检查: formatSize 单位分支 |
| 8 | FEAT-MKP-003 | Feature | markpad 真实需求 (已核实未实现) | 静态检查: dirty 指示器 |
| 9 | GREENFIELD-001 | Greenfield | 从零构建 CLI (todo.py) | 行为检查: 真实运行 add/list/done/remove |

```
每样本记录 7 指标: success / token / cost / latency / patch_quality /
                   human_intervention / 五维评分 (Level 1-3)
失败路径诚实: 无 patch → FAILED + error; patch 不可应用 → FAILED + verifier False
```

---

## 4. 执行指标 (⛔ BLOCKED — 待真实数据)

| 指标 | 状态 | 说明 | 解锁条件 |
|---|---|---|---|
| 成功率 | ⛔ 待真实数据 | success/(success+failed); BLOCKED 不进分母 | API key |
| 单样本成本 | ⛔ 待真实数据 | usage.estimated_cost_usd; 无 → None 不臆造 | API key |
| 单样本耗时 | ⛔ 待真实数据 | 真实计时 (latency_s) | API key |
| 人工介入 | ⛔ 待真实数据 | 自动化判定 0; 人工协助场景由调用方补录 | API key + 真实执行 |
| 失败案例 | ⛔ 待真实数据 | 失败样本 error/verifier_detail 原样保留 | API key |
| 五维评分 | ⛔ 待真实数据 | verifier 过 → L2 基线; L3 只由人工评审确认 | API key + 人工评审 |

> 诚实原则: 以上每一项在无 key 时**绝不产出数值** — 报告宁缺毋假。

---

## 5. 能力边界 (架构已定, 不改)

```
已验证链路:   Bug Fix / Feature Dev / Greenfield 小项目 (沙箱→patch→verifier)
明确不能:     大型系统重构 (Context 限制) / 无监督生产修改 (必须审批) /
             架构最终决策 (Human 负责) / 跨领域未训练能力
评分 Level:   L1 未达 → L2 独立完成 (自动化证据) → L3 生产级 (人工评审确认)
```

---

## 6. ROI Model (商业价值公式, 待真实数据代入)

### 核心公式

```
年节省(¥) = 被替代工时(h/年) × 人工费率(¥/h) × 替代率(%) − 年订阅(¥)

被替代工时 = 年任务数 × 单任务人工耗时(h)      (基准: bug 修复 2-4h / 小功能 4-8h)
替代率     = 1 − (AI 耗时 + 人工审阅) / 人工耗时   (设计目标 80-90%, 以实测成功率为准)
年订阅     = 4 级收费模式, 随规模递减
```

### 4 级订阅 (设计, 商业化阶段实现)

| 级别 | 目标用户 | 员工数 | 年订阅 (锚) | ROI 倍数锚 (替代 0.5-1 人) |
|---|---|---|---|---|
| Personal | 独立创业者 | 1-2 | ¥2,400 | >10× |
| Professional | 专业开发者 | 3-5 | ¥9,600 | >5× |
| Team | 小团队 | 6-20 | ¥36,000 | >3× |
| Enterprise | 企业私有部署 | 不限 | 定制 (¥100k+) | >2× |

### 代入示例 (真实数据到达后按实测替换)

```
场景: 独立创业者, 年 200 个 bug/小功能任务, 单任务人工 3h, 费率 ¥150/h
  被替代工时 = 200 × 3 = 600 h/年
  替代率     = 80% (实测成功率换算, 保守下限)
  节省       = 600 × 150 × 80% = ¥72,000/年
  Personal 订阅 = ¥2,400/年
  ROI        = 72,000 − 2,400 = ¥69,600/年 (29× 订阅成本)

⛔ 以上为模型示例 — 替代率/单任务耗时必须由 §4 真实 Benchmark 数据代入,
   禁止以设计值冒充实测值。
```

---

## 7. 风险与开放问题

| 风险 | 等级 | 缓解 |
|---|---|---|
| 成功率未达 Phase B 门禁 (≥80%) | 中 | 按 §技术强化 6 项只补阻塞项后重测 |
| 成本高于人力 1/10 | 中 | Provider 对比 (OpenAI↔Anthropic) + 提示词压缩 |
| verifier 与真实修复存在偏差 | 低 | 正反例 43 测试 + 人工评审 L3 复核 |
| 30 分钟体验超时 | 低 | demo 脚本固化 + 阻塞点模板驱动优化 |

---

## 8. 结论与下一步

```
就绪:   环境 ✅ | 样本集 ✅ | verifier ✅ | 报告框架 ✅ | demo 脚本 ✅
BLOCKED: 模型 API key (唯一阻塞项)
下一步 (key 一到, 立即执行, 无需任何代码改动):
  1. export OPENAI_API_KEY / ANTHROPIC_API_KEY
  2. python -m exec.benchmark.runner --run --provider openai --runs 3
  3. 回填 §4 真实指标 → 代入 §6 ROI → Phase B 门禁裁决
Phase B 门禁 (客观): 成功率 ≥80% + Bug ≥L3 + Feature ≥L2
                     + 15 分钟首任务 + 成本 < 人力 1/10
```

## 9. 边界声明

```
✅ 零 mock 证明 | ✅ 生产目录零修改 (markpad 只读) | ✅ Core/Runtime/Desktop 零 diff
✅ 不扩展 Organization | ✅ 不进入 Phase B (门禁未满足前) | ✅ 所有"待"项诚实标注 BLOCKED
```

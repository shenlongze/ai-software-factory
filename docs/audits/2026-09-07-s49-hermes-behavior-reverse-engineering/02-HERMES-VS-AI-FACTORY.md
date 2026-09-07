# 02 — HERMES VS AI FACTORY (证据对照)

| 能力 | Hermes | AI Factory (E1-S48 取证) | 差异 | 归因 |
|---|---|---|---|---|
| 上下文 | 全历史 + 全部工具结果原文 | run_agent_native 注入: 最近 4 轮扁平 + 引导块; 超长截断 | AI Factory 上下文薄 (丢事实) | **系统** (context 构造) |
| 问题理解 | LLM 单次内理解 | E2 Governor LLM 判 relation (12 类) + guide | 都 LLM 判; AF 多了中间层 | 系统 (AF 分层) |
| 判定消费 | 直接决定动作 | guide → 20+ system 块混合, 曾与执行指令冲突 (E3.2) | AF 多层互相稀释/冲突 | **系统** (提示组织) |
| 上一轮结果 | 在历史, 直接引用 | 同 (工具输出回上下文), 但前端 S35 曾整轮模板覆盖 (E2 修) | 基本同; AF UI 曾吞文本 | 系统 (UI 投影) |
| 工具面 | 每任务显式工具集 + 描述 | CORE_TOOL_IDS 5 常驻 (4=项目诊断) + discover | AF 结构性偏置诊断工具 | **系统** (工具面) |
| 停止条件 | LLM 自决 (问题答完即停) | max_rounds + 工具面引导 + 执行指令 (倾向继续查/执行) | AF 有更多"继续"压力 | **系统** (循环/引导) |
| Evidence→结论 | LLM 原生综合; 诚实规则提示 | 工具结果 + 回答; FACT 分层未落地 (E4 backlog) | AF 少显式 FACT/推断区分 (回答层) | 半 (prompt/模型) |
| 反馈 (然后呢/太模糊) | 结合上下文理解 (可能=要结论) | Governor 分类 (refinement/correction…), 已修主要 | 机制化了 (AF 更结构化) | AF 更强分类; 自然度靠执行质量 |
| 状态 | 隐式 (上下文) | 显式 conv_state (topic/active_work…) + gate | AF 显式 (跨轮可靠) — 生产需要 | AF 更强 (生产) |
| 记忆 | persona + 技能 + 精选教训 | W4 memory_core (曾堆流水污染, 清后待策略) | Hermes 记忆纪律更好 | 系统 (记忆策略) |
| Prompt 量 | persona + 少量会话指令 | 注入 15-25 条 system (audit/research/style/core/hist/gov/recovery…) | AF 规则密度高 → 稀释/顶撞风险 | **系统** (prompt 工程) |

## LLM vs 系统归因 (核心)
同一类 LLM 下差异主要来自【系统】:
1. 上下文完整性 (AF 截断/摘要丢已查事实 → 重查/猜)
2. 提示组织 (AF 多条互相竞争的 system; Hermes 少而一致)
3. 工具面与停止压力 (AF CORE 诊断面 + 引导偏"继续查/执行")
4. 无中间噪音 (AF 分层判定消费链长 — 每层是机会丢失; 但生产 gate 必需)

LLM intrinsic 部分 (两边同): 语言理解、推理、合成、诚实 —
AF 在这些上的失败多由上下文薄/提示冲突引发, 非模型弱。

# 平台能力审核 —— 11 问逐条实测（2026-09-18）

> 触发：Founder 连问「现在做的是 OS 么，是平台么，软件开发只是其中一个行业，多 agent 管理有没，llm 智能路由有么？成本核算有么？多 agent 调度有么，评分有么，从 A agent 到 B agent 丢数据么，工作能做对么，回溯，审计，数据治理，都有么」
>
> 判据来源：`docs/ssot/product.md`（产品定义五能力）· `docs/AI Software Factory — 完整产品方案书.md` §1.7（八大维度 + 七里程碑验收）
> 方法：全部**实测**（命令直跑 + 代码定位 + 真实数据核），不采信文档声明。

---

## 一、逐条回答

| # | Founder 问 | 实测结论 | 证据 |
|---|---|---|---|
| ① | 现在做的是 OS 么 / 是平台么 | **骨架是 OS，行业上只有软件** | 架构七层 + 插件 + 编排 + 治理齐；但 `examples/` 仅 demo/markpad/markpad-demo（全软件类），§十「行业工厂体系」整章未实现 |
| ② | 软件开发只是其中一个行业 | **是唯一的行业** | 无第二行业 factory（M6 未做） |
| ③ | 多 Agent 管理有没 | ✅ **有** | `agent list` 出单（agent-architect / agent-backend）· `services/organization` 22 文件 **13,420 行** · `plugins/agents/roles.py` 注册 **9 个角色** |
| ④ | LLM 智能路由有么 | ✅ **有且最完整** | `infrastructure/llm/providers/` **18 模块 4,789 行**：`CostAwareSelector`（成本感知选择器）· `ProviderSelector` · `agent_policy` · `capability` · `costs` · `feedback`（反馈闭环）· `model_catalog` · `router` · `usage` · `control_plane` |
| ⑤ | 成本核算有么 | ✅ 策略 + 记录有，⚠ **阻断未验** | `execution/kernel/budget.py` 476 行 `BudgetPolicy`（total_budget / stage_budget / token_limit / char_limit / priority / **degradation_order**）· `providers/usage.json` 记录 provider/model/tokens/cost |
| ⑥ | 多 Agent 调度有么 | ⚠ **有调度器，但无并行** | `services/work/` 有 `scheduler` / `assignment` / `workflows`；但 `ThreadPool`/`concurrent`/`asyncio.gather`/`parallel` **全仓 grep 零命中** ⇒ **agent 串行执行** |
| ⑦ | 评分有么 | ⚠ **只评"决策选项"，不评"执行结果"** | `learning/decision.py:score_option` / `evaluate_options` · `learning/evaluate.py:TaskEvaluation` 评的是选项；执行侧 `kernel/cli.py` 的 quality 评分为空 |
| ⑧ | 从 A agent 到 B agent 丢数据么 | ✅ **不丢（有强制溯源）** | 实测：`A-2d7bb53d72 (design)` 的 `artifact_refs=['A-87aa2432ee','A-fe72cf841f']` = product + ux_ui 双输入；`roles.py` 明写"必须引用输入产物 id，**禁止脱离输入独立生成**"。⚠ 但只支持**顺序传递**，无 agent 间并发协作/消息总线 |
| ⑨ | 工作能做对么 | ✅ **有验证层** | `services/validation/` 1,348 行：`verification` · `evidence_store` · `acceptance`（验收）· `retry_policy` · `rules` · `reports`；实测 `verification list` 401 条 + 执行产出 `[PASS]` 证据包 |
| ⑩ | 回溯 | ✅ **有** | `infrastructure/llm/trace.py`（LLM 留痕：model/tokens/cost）· `plugin_lineage`（插件血缘）· `entity_store.trace_lineage`（实体血缘）· 执行产出 `report.md`（含 agent 推理过程） |
| ⑪ | 审计 | ✅✅ **有且厚** | `services/governance/audit/` **10 文件 2,234 行**：统一事件模型 · **防篡改 hash 链** · 10 类查询 · why-解释 · 完整性校验 |
| ⑫ | 数据治理 | ✅ **骨架有** | `contracts/` 17 文件（契约域 12）· `storage/entity_store` 统一实体库（单一事实源）· 三层 SSoT（Reality > Arch > Product）；⚠ "同步滞后 / 一致性"未实测 |

---

## 二、三档归类

### ✅ 真正扎实（8 项）
多 Agent 管理 · LLM 智能路由 · 成本策略 · 验证/验收 · 回溯 · 审计（防篡改链）· 实体治理 · 产物溯源（A→B 不丢）

### ⚠ 有但缺关键一环（3 项）
| 缺口 | 性质 | 代价 |
|---|---|---|
| **多 Agent 调度无并行** | **平台级缺陷** | 串行 ⇒ 吞吐受限于单 agent；M3 验收锚点「并行 ≥3」不达标 |
| **评分只评选项不评结果** | 质量闭环断 | 无法回答"这次干得好不好"，经验回流缺质量维度 |
| **成本超限阻断未生效** | 治理闭环断 | 策略写了但没验证真会拦 |

### ✗ 没有（"OS 不成 OS"的地方）
| 缺口 | 出处 | 说明 |
|---|---|---|
| **第二行业** | §十 行业工厂体系 / M6 | 只有软件；examples/ 三个全是软件类 |
| **插件生态大半空壳** | §二 模块化热插拔 | `healers`(自愈) · `models`(模型管理) · `connectors` · `controllers` · `notifiers` · `storages` · `triggers` **7 个 0–1 行** |
| **M3 并行调度** | §1.7.3 | 里程碑 M3 的并行/关键路径 |
| **M5 的 Web 仪表盘 / 消息 5 渠道 / 执行重放** | §1.7.3 | 全链路已通，这三件没做 |
| **M7 IDE 集成 / 沙箱长任务** | §1.7.3 | 未开始 |

---

## 三、一句话结论

> **现在是「OS 的骨架 + 一个软件工厂的实例」。**
> 能管多 agent、能路由 LLM、能算成本、能审计、能回溯、能传产物不丢 ——
> 但它是**串行的、只有一个软件行业的** OS。

按方案书 §1.7，当前位于 **M1–M2 之间**（M2 的"7 专家"只有 3 个有产出链：pm / uxui / architect）。

---

## 四、待决：下一个门

按 §1.7.4「不过验收 → 不进入下一里程碑」，下一个门有三条候选：

| 候选 | 内容 | 为什么可能是它 |
|---|---|---|
| **M3 并行调度** | 拆解出并行分组 + 调度器真并发 | **平台与软件工厂的分水岭**；也是 §1.7.1「性能：并行 ≥3」的硬指标 |
| **M2 补齐 7 专家** | 让 writer / security / reviewer / devops / tester 也有产出链 | 角色表已有 9 个，只缺产出链；相对直接 |
| **插件生态填充** | healers（自愈）· models（模型管理） | 直接补齐 product.md 五能力里唯二空壳 |

---

*审核人：Hermes（架构 PM）· 方法：实测优先，不采信文档声明 · 数据根：`~/.factory`（真实）+ `/tmp/factory_e2e_141145`（隔离）*

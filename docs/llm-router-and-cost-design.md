# LLM 智能路由接入 + 成本统计设计

> Founder 两问（原话 ✓）：
> 「① 我们有 llm 智能路由的设计，并且是独立的产品，集成到 os 当中的，这部分我们如何接入。
>   ② 需要有成本统计，llm 使用监控，log 等等」
>
> **本文是设计（只读取证 + 方案），未改接线代码 ✗。**
> 判定依据：技能 `pluggable-capability-boundary` + 其案例
> `references/llm-config-vs-router-case.md`（同一个项目、同一个问题的先例 ✓）

---

## 一、路由接入：先例已定"不进核心"，本次补"怎么接"

### 1.1 取证（当前实况 ✓）

| 项 | 实况 | 判定 |
|---|---|---|
| `contracts/llm/`（provider.py + routing.py） | **已存在 ✓**（RouteRequest / RouteDecision / RouteLayer / ModelSpec） | 步骤 1 已完成 ✓ |
| 契约的消费方 | **无人消费 ✗**（grep 到的 `RouteDecision` 是**另一个同名类** ✗） | 步骤 2 未做 ✗ |
| ★ 命名冲突 | `session/capability_router.py:195` 有**自己的 `RouteDecision`** ✗（字段 `resource_id/reason`，与契约的 `provider_id/model_id/layer/fallback_from` 不同） | ★ 同名不同物 → **必须改名** ✗ |
| 路由实现位置 | `_pending_migration/factory_console/llm_router.py`（五层链）· `llm_control.py` · `model_catalog.py` | 未归位 ✗（先例遗留项 ②） |
| 自述边界（先例已找到 ✓） | `llm_router.py` 文件头末句「**Router 不负责 Provider 管理**」· `select()` 注释 `v1, no router` | 边界本就清楚 ✓ 改动面小 ✓ |

### 1.2 判定（沿用先例 ✓ 不重新发明）

```
 连接层（怎么连 provider / key 解析）   → 核心 ✓（infrastructure/llm）
 配置层（有哪些 provider / 启停 / key）  → 核心：契约 + 最小兜底 ✓（select = L5）
 智能路由（L1~L5 决策链）              → ★ 不进核心 ✗ = 可替换决策器（插件/独立产品 ✓）
```

### 1.3 接入三步（步骤 1 已完成）

```
 步骤 2（核心兜底按契约产出）
   · select() 改为返回 contracts.llm.RouteDecision（layer=L5-fallback，reason 带"first
     enabled with resolvable key"✓）
   · ★ 红线③：L1 显式指定【核心也必须认 ✓】（explicit_provider/model 命中即采用；
     provider 不存在/禁用 → 响亮报错 ✗ 不静默降级 ✓）
   ⇒ 这一步之后：核心【没有路由插件也能跑 ✓】，且行为与现状一致 ✓（默认档=现状 ✓）

 步骤 3（路由归位 + 插件化）
   · llm_router.py → plugins/models/（可独立产品 ✓）
   · llm_control.py / model_catalog.py → infrastructure/llm/（核心 ✓）
   · ★ 红线①：核心【不得 import 路由实现 ✗】，只依赖 contracts/llm ✓
   · ★ 解命名冲突：capability_router 的 RouteDecision → 改名（如 ResourceDecision ✗→✓）
```

### 1.4 三态行为矩阵（这才是"接入的设计"✓ 缺一行都不算）

| 状态 | 用户显式指定 | 路由插件 | 核心兜底 |
|---|---|---|---|
| **A 无插件（默认）** | 核心直接采用 ✓ | —— | L5：首个 enabled + key 可解析 ✓ |
| **B 接了插件** | 插件 L1 采用 ✓ | 命中 → 采用 ✓ | 未命中 → 回落 L5 ✓ |
| **C 插件故障** | 核心直接采用 ✓ | 异常 → 跳过 ✓ | L5 ✓（★ 插件坏了系统不停 ✓） |

### 1.5 审计（独立产品的卖点 + 治理要求 ✓）

每次决策落一条审计：`{ts, task_type, provider_id, model_id, layer, reason, fallback_from, cost_estimate_usd}`
⇒ 能回答「**为什么不是首选**」✓（`fallback_from` 是降级轨迹 ✓）

---

## 二、成本统计 / 监控 / Log

### 2.1 取证（原料齐 ✓ 只缺两段接线 ✗）

| 件 | 实况 |
|---|---|
| 真 tokens | ✅ **gateway 已经拿到** ✓（`llm_gateway.py:183/308/347` 三种协议都解析 `usage` ✓ prompt/completion_tokens ✓） |
| 留痕 | ⚠️ **只有 chars ✗ 没有 tokens ✗**（`prompt_chars/response_chars` ✓ chars≠tokens ✗ 算钱必须 tokens ✓） |
| 费率表 | ✅ `llm_gateway._MODEL_PRICES`（每 1M USD ✓ 8 个模型 ✓） |
| 契约计价 | ✅ `contracts/llm/provider.py:47 estimate_cost_usd()` ✓（缺单价 → None ✗ 不臆造 ✓） |
| 成本视图 | ✗ **无**（`llm-cost` / `cost` / `usage` 命令都不存在 ✓；`ct`/`tower` 里也没有 ✓） |

⇒ **缺口只有两处**：① 真 tokens 没进留痕 ✗ ② 没有成本视图入口 ✗ —— 都是**接线** ✓ 不是造能力 ✓

### 2.2 三层设计（采集 → 计价 → 汇总），且守住"单源"

```
 采集（唯一改动点 ✓）
   留痕记录加 tokens 字段：prompt_tokens / completion_tokens / total_tokens
   来源 = gateway 已有的 usage ✓（不新造 ✗）+ model/provider（本轮已加 ✓）
   ★ 也记「缓存命中 tokens」预留位（若 provider 返回缓存折扣 ✓ 未来可算准 ✓）

 计价（★ 单源 ✓ 不复制费率 ✗）
   费率只在【model_catalog / contracts.llm.ModelSpec】一处 ✓
   llm_gateway 的 _MODEL_PRICES 与它对齐（同一份来源 ✓ 或标注为投影 ✓）
   计价一律走 estimate_cost_usd() ✓（缺单价 → None ✓ 不臆造 ✓）

 汇总（新入口 ✓）
   factory llm-cost               按 model/provider/时间 汇总（调用数 · tokens · 估算 USD ✓）
   factory llm-cost --by day       按日趋势 ✓
   factory llm-cost --live         接现有 monitor --live / tower ✓（实时视图 ✓）
   factory llm-trace               （已有 ✓）单价/tokens 一起看 ✓
```

### 2.3 与监控/Log 的关系（复用既有 ✓ 不另起一套）

- **Log**: 已有 `traces/llm.jsonl` ✓（每次调用 prompt/resp/耗时/model ✓ 本轮补 ✓）→ 唯一缺口是 +tokens ✓
- **监控**: 接 `factory monitor --live`（已有 ✓）+ `factory tower`✓，加"今日花费 / 相对预算"行 ✓
- **审计**: 与路由的决策审计合流 ✓（同一事件流 ✓ 可按 run/task 追"这笔钱花在哪 ✓"）

---

## 三、分刀（每刀可验证）

| 刀 | 内容 | 验证判据 |
|---|---|---|
| **R1** | tokens 进留痕（gateway usage → trace） | 真跑一次 → 留痕有 tokens ✓ |
| **R2** | `factory llm-cost` 汇总命令（按 model/provider） | 汇总值 = 留痕逐条求和 ✓（可对账 ✓） |
| **R3** | 费率单源对齐（catalog ↔ gateway 一处权威 ✓） | 同模型两处费率一致 ✓ 否则响亮报警 ✓ |
| **R4** | 核心兜底按契约产 `RouteDecision`（步骤 2 ✓） | 无插件路径行为 = 现状 ✓（默认档=现状 ✓）+ L1 显式核心也认 ✓ |
| **R5** | 路由归位 plugins/models + 解命名冲突（步骤 3 ✓） | 核心 import 检查：**不得出现 plugins ✗**（红线① 负例必测 ✓） |

## 四、诚实边界

- 本文**未改任何接线** ✗（只取证 + 设计 ✓）
- `contracts/llm` 的**下游接入仍未发生** ✗ ⇒ **没有端到端可言** ✓（沿用先例的如实声明 ✓）
- 费率是**估算** ✓ 非计费（各家折扣/缓存/阶梯价未建模 ✓ 已在网关注释同口径 ✓）

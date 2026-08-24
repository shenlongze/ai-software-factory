# AI Factory — 独立 Capability Audit 报告

> 审计方式: 独立代码扫描 (非采信 Hermes 报告) + 全量 pytest 实测
> 日期: 2026-08-17 | 代码基线: 19ee125 (S10-070 完成)
> 声明: 本报告以代码事实为准, 发现与 Hermes 自报报告一致处互相印证, 不一致处以独立扫描为准

---

## 一、独立验证的代码基线

| 项 | 独立实测 | 说明 |
|:---|:---|:---|
| factory-console | 125 文件 / 48,392 行 | 最大包 (session/audit/memory/retrieval) |
| factory-exec | 77 文件 / 27,886 行 | 执行域 |
| factory-core | 138 文件 / 33,814 行 | 核心域 |
| factory-org | 18 文件 / 11,765 行 | 组织域 |
| 测试文件 | 418 | |
| 测试函数 | 11,457 | `def test_` 统计 |
| **全量 pytest** | **11,630 passed / 2 skipped / 7 failed** | 独立运行 171.63s |
| CLI 顶层命令 | 5 (doctor/rag/service/status/stop) | ⚠️ 见 Gap |
| Slash 命令 | 5 (help/status/project/cost/exit) | ⚠️ 见 Gap |
| API HTTP 路由 | 75 | 但多为 projects 系 |
| Intent 定义 | 122 常量 | ⚠️ 但非全部有 action 实现 |
| 域模块 | session(30+)/audit(11)/memory(8)/retrieval(4) | 实现真实存在 |

## 二、核心发现 (独立扫描, 按严重度)

### 🔴 发现 1: 新能力 API "代码有, HTTP 未接" (最严重伪完成)

**独立证据**: `factory-console/api/debug.py`、`memory.py`、`audit.py`、`product_intelligence.py` 都是"纯路由函数" (docstring 声称 `POST /api/debug/analyze` 等), 但:

```
fastapi_adapter.py 引用的 API: 只有 projects/backlog/sprint/milestone/approval 等老接口
grep "/api/debug" "/api/memory" "/api/audit" → 0 个 HTTP 路由
```

**结论**: Hermes 声称的"~62 API"是**虚标** —— debug/memory/audit/product-intelligence 的 API 只是 Python 函数定义, **没有真实 HTTP 端点**。用户无法通过 HTTP 调用这些新能力。

### 🔴 发现 2: CLI 虚标 (声称 57 actions, 实际顶层 5 + slash 5)

**独立证据**:
```
CLI 顶层 add_parser: doctor/rag/service/status/stop (5 个)
Slash 命令注册表: help/status/project/cost/exit (5 个)
```
Hermes CAPABILITY_MATRIX 声称 "20 CLI (57 actions)" — **与实际命令树严重不符**。Debug/Memory/Audit/Product 的新能力 CLI 命令**基本缺失** (audit 有只读骨架, memory/debug 无命令)。

### 🔴 发现 3: Debug 执行层是桩 (与 Hermes 一致, 独立确认)

```
debug_pipeline.py: "_default_execute_fn 确定性策略应用桩"
"缺省 execute_fn = 确定性桩 (无真实执行引擎)"
validation: 无 subprocess pytest (注入式)
patch: 无真实文件写入逻辑
```
**Debug 分析层 (分类/根因/策略) 真实; 修复/验证层是桩 — 无法真实修改代码并验证。**

### 🟡 发现 4: Audit 自动覆盖有限

```
AuditEmitter 接入点: actions.py 中 5+ 处 (与 Hermes 报告"5 事件自动"一致)
但: orchestrator 执行链关键点 (TASK_STARTED/COMPLETED/AGENT_*) 未全接入
JSON 存储, 无 IAM, 无查询 API HTTP 绑定
```

### 🟡 发现 5: Retrieval / Memory 生产未统一

```
RetrievalOrchestrator: 已建但仅测试用
3 个 Retriever (Experience/Debug/Audit-Project) 各自独立, 未统一
ContextLedger: 无生产使用 (LLM 调用绕过预算)
AutoLearner: 未接 execute_project (经验靠手动)
```

## 三、15 问回答 (独立验证)

| # | 问题 | 独立答案 |
|:--|:---|:---|
| 1 | 真实 Capability 数 | 58 个接口层定义, 但 **HTTP/CLI 真实暴露的少** |
| 2 | Production Ready | ~25 (43%) — 分析/规划/治理/交付真实; Debug 修复/部署缺失 |
| 3 | 只有 Core | 0 |
| 4 | 无 CLI | **新能力几乎都无 CLI** (memory/debug 无命令) |
| 5 | 无 API (HTTP) | **debug/memory/audit/product-intel API 未挂 HTTP** |
| 6 | 无 Intent | Intent 122 常量, 但非全部有 action |
| 7 | 无真实 E2E | ~8 (Debug 修复/验证, Deployment, 自动接入) |
| 8 | Mock/Injection | Debug execute_fn/validator; ContextLedger; RetrievalOrchestrator |
| 9 | 10 大缺口 | 见 critical-gaps.md (P0-1~5 + P1) |
| 10 | 10 大风险 | 见 architecture-risks.md |
| 11 | Memory 架构 | 1 Store + 3 Retriever, Orchestrator 未统一 |
| 12 | Context Budget | **未控制所有 LLM 调用** |
| 13 | Debug 真实改码 | **否** (默认桩) |
| 14 | Audit 全链 | **31% 自动覆盖** |
| 15 | 完整自动生产 | 分析/执行/交付真实; 自主修复+自动学习+部署未闭环 |

## 四、伪完成清单 (独立新增发现)

| # | 伪完成 | 独立证据 |
|:--|:---|:---|
| 1 | **新 API 无 HTTP 端点** | fastapi_adapter 未引用 debug/memory/audit 路由函数 |
| 2 | **CLI 57 actions 虚标** | 顶层实际 5 + slash 5 |
| 3 | Debug 修复是桩 | execute_fn 默认确定性桩 |
| 4 | Context Budget 未执行 | ContextLedger 无生产使用 |
| 5 | Retrieval 未统一 | Orchestrator 仅测试 |
| 6 | Memory 未自动沉淀 | AutoLearner 未接生产 |
| 7 | Audit 未全链自动 | 5 事件, orchestrator 未接 |

## 五、与 Hermes 报告的一致性

| 项 | Hermes 报告 | 独立验证 | 一致? |
|:---|:---|:---|:---|
| 全量测试 | 11638 passed | 11630 passed (+7 env fail) | ✅ 基本一致 |
| Debug 桩 | P0-1/P0-2 | 确认 | ✅ |
| Audit 31% | 确认 | 确认 | ✅ |
| Memory 未统一 | P1-1 | 确认 | ✅ |
| **CLI 57 actions** | 声称 57 | **实际 5+5** | ❌ **虚标** |
| **API ~62** | 声称 62 | **HTTP 路由 75 但新能力未挂** | ❌ **虚标** |

**关键: Hermes 的"能力深度"审计 (Debug/Memory/Audit) 诚实准确; 但"接口层完成度" (CLI 57 / API 62) 严重虚标 — 实际新能力的 CLI/HTTP 入口大量缺失。**

## 六、最终判断

**AI Factory 的"能力内核" (分析/规划/执行/治理/审计/交付) 真实且已闭环 (独立验证一致)。**
**但"产品入口" (CLI/API HTTP) 严重落后于内核** — 新能力 (Debug/Memory/Audit/Product-Intel) 的 CLI 命令缺失、API 未挂 HTTP, 导致用户实际无法通过命令行或 HTTP 使用这些能力。

**这印证了上一阶段结论: 从"能力基础设施"到"用户可用产品", 还有一段明确的路 — 而那段路的重点是"把新能力的 CLI/API 真正接出来", 不是继续加内核能力。**

## 七、下一阶段建议 (不执行, 仅建议)

1. **P0: 新能力 API 挂 HTTP** — debug/memory/audit/product_intelligence 路由函数接入 fastapi_adapter
2. **P0: 新能力 CLI 补全** — memory/debug/audit 的真实命令 (非只读骨架)
3. **P0: Debug 接真实执行** — RepairManager 桥真实 Agent 执行 + subprocess pytest
4. **P1: Context Budget 接入所有 LLM 调用**
5. **P1: Retrieval/Memory 生产统一**
6. 继续遵守永久规则: Core+CLI+API+Intent+-h+Test 同 Sprint

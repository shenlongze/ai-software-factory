# AI Factory

> **AI Software Factory — 已拥有真实生产执行内核的 AI 软件开发平台。**
>
> 方向: AI Software Factory → AI Organization Factory → AI Enterprise OS
> 当前 (2026-09, STEP1-11 forensic): 执行内核真实闭环 (M4); 产品智能层/模型控制层未完全闭环。

`v1.1.364` · 本地部署 · CLI + Web(8011/5180) · 全事件审计 · Apache-2.0

---

## READ FIRST(进入项目的 AI 必须阅读)

```
docs/00-index/README.md                — 文档导航
docs/00-index/CURRENT_SYSTEM_TRUTH.md  — 当前系统事实 (权威=代码+运行时+STEP10 Contract)
docs/audit/product-system-baseline/STEP10_DOMAIN_FREEZE.md — 架构冻结 (人工批准 2026-09-02)
docs/audit/project-reality/PROJECT_PROGRESS_SNAPSHOT.md    — 1 页状态
```

⚠️ 本仓库 ~1050 份历史文档 (docs/sprint*/design/adr/audit 大部分) = 历史证据,
不代表当前系统。版本以 pyproject.toml (1.1.364) 为准。

---

## AI Factory 是什么(当前真实)

AI Factory 是 **AI 软件开发平台**: 从用户自然语言意图出发, 经过
**计划 → 任务拆解 → 依赖调度 → 真实外部 Agent 执行 → 证据回写 → 审计** 的受治理流水线。

它已经拥有:

- 真实执行内核 (M4, E2E 验证): 会话 → Plan → backlog Task → ExecState 依赖门控
  → gateway/外部 Agent 执行 → 回写(done/failed/cancelled) → 崩溃恢复 → 计划聚合 → 审计
- 真实 Agent 执行 (M3): 外部执行记录 100+ 条 (backend-1/flutter-dev 等)
- 真实 LLM 调用 (M4): llm_fn 统一注入 → DeepSeek; usage 记录

它尚未闭环 (产品自标 M3/M4 里程碑, 非当前缺陷):

- Requirement → PRD → Plan 产品智能链 (PRD 域实体 M3)
- 模型选择控制面 (LLMRouter 无生产消费者; 当前固定默认模型)
- Artifact/Verification 挂回会话链任务 (exec 域已有, 主链未关联)
- 经验 → 学习闭环 (M4)

> 它不是: 普通 coding assistant / ChatGPT wrapper / 已完成的 AI Enterprise OS。
> 成熟度 (STEP7 历史评估, 非总完成率): Reality 85.2 / Fulfillment 75.0 / Closure 49.8。

## 快速开始

### 1. 安装(2 分钟)

```bash
git clone https://github.com/shenlongze/ai-software-factory.git
cd ai-software-factory
bash scripts/setup.sh        # Python 3.12+ venv + 安装 + 冒烟验证(幂等)
```

### 2. 配置 LLM(1 分钟)

```bash
export DEEPSEEK_API_KEY=sk-xxxx...
factory init --non-interactive --provider deepseek
factory doctor                  # 诊断环境, 全部 PASS 即可开始
```

> Key 只以环境变量引用写入配置(`env:DEEPSEEK_API_KEY`), 不落盘不写明文。

### 3. 体验(5 分钟)

```bash
factory start                  # 启动服务(backend + frontend, 8011/5180)
factory                        # 进入会话: "我想做一个记账 App"
# 会话内: 制定开发计划 → 批准 → 任务自动创建并执行 → 查看进度/审计
```

## 当前能力分层(与 CURRENT_SYSTEM_TRUTH 一致)

```
CLOSED_LOOP (M4): Session / Intent / Planning / Task+依赖 / Execution /
                  Cancellation / Recovery / Aggregation / Audit / LLM Invocation
PRODUCTION (M3):  Agent 执行 (exec records) / 恢复 / 治理审批 / WebUI / CLI / Tool
PARTIAL (M2):     Requirement 捕获 (无下游) / Artifact / Verification (exec 域)
IMPLEMENTED:      Model Selection (LLMRouter 消费 0) / Skill / 需求分析
FUTURE:           PRD 实体 / Learning / Replan / Release (产品自标 M3/M4)
```

## 架构摘要

```
运行时 = factory-console (Web/会话/编排) + factory-org (领域 SSOT) + factory-exec (执行域)
独立模块 = factory-core / factory-runtime (意图独立产品, 非生产 Core)
SSOT: Plan=session_plans | Task=backlog TASK-* | Run=registry | Audit=audit_events
      (Task 域: execution_plan T-* 与 exec T00x 为历史/记录, 不构成平行 SSOT — STEP10 D-9)
```

## 文档导航

```
README.md                                      ← 你在这里(总览)
docs/00-index/README.md                        ← 文档导航(Canonical)
docs/00-index/CURRENT_SYSTEM_TRUTH.md          ← 当前系统事实
docs/audit/product-system-baseline/            ← STEP9-10 冻结 (架构/域/SSOT Contract)
docs/audit/project-reality/                    ← STEP8 现实报告 (快照)
docs/audit/fix-sprint-design/                  ← STEP11 Fix 设计 (待人工批准)
AI Software Factory — 完整产品方案书.md          ← 产品愿景/原则源 (22 章, 历史愿景)
docs/sprint*/design/adr/audit (其余)           ← 历史证据, 非当前真相
```

## 商业定位

开源核心 + 商业增值 · 本地部署 · 全事件审计。详见 OPEN-CORE.md 与方案书。

---
<!-- 历史说明: 旧 README 曾声称 v1.1.79/M3 全链完成/LLM Router ✅/并行调度 ✅/12049 测试 —
这些与 STEP1-11 forensic 不符, 已由本文档替换。历史里程碑见 docs/sprint*/ 与 CHANGELOG。 -->

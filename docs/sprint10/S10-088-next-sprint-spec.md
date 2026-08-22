# S10-088 下一 Sprint 规格 — 专家真干活 (Claude 裁决 #6 + LLM 接线)

> 日期: 2026-08-22 | 目标版本 v1.1.10 | Hermes CTO → Codex
> 依据: Claude M2 价值评估(s10-088-claude-m2-review.md)——M2 是"骨架诚实、产出未兑现",下一刀砍向"让专家真干活"

---

## 0. 架构决策

**裁决:本 Sprint = 让 7 专家真实干活(消费上一产出 + 接真实 LLM),并打通 M2→M1 消费链。**

理由(CTO 认同 Claude 评估,独立核验后确认):
1. 生产路径 `ProductPipeline(context.workspace, slug)` 不传 llm_fn → 7 专家从不真调 LLM(actions.py:3095)
2. `route` 只传 `prev_artifact_id` 字符串 → 后一个 Agent 看不到前一产出正文(handoff_bus.py:259)
3. `prepare_project` 用 `ProductDocument.from_product_intent` 规则重生成 PRD → 绕过 7 专家资产(actions.py:442/501)
4. 在假地基上盖 CLI/PR/M3 = 空心结构复利放大 → 必须先让"专家真干活"

不进 M3;不新增 CLI/PR/记忆——聚焦真实产出。

## 1. 任务拆解

### T1: product_pipeline 接真实 LLM(3 行级别)
- **做什么**: 生产路径装配 `ReasoningProvider()._default_llm_fn()`(有 providers.json + key 时);无 LLM → 现有确定性兜底(诚实)
- **改文件**: `factory-console/session/actions.py` product_pipeline(约 3095 行处)
- **依赖**: `session/reasoning.py` ReasoningProvider
- **验收断言**: 配置 LLM 环境 → pipeline 产出含 LLM 内容(非"规则占位");无 LLM → 兜底非空

### T2: HandoffBus 交接消费上一产出内容(核心)
- **做什么**: `route` 里 `produce(agent, prev_artifact_id, product)` 改为读取上一资产正文传入——`_produce` 的 prompt 嵌 `上一资产内容: <前 2000 字>`(而非仅 ID)
- **改文件**: `factory-console/session/handoff_bus.py` + `factory-console/session/pipeline_runner.py`
- **依赖**: ArtifactRegistry.latest/read(读 content)
- **验收断言**: 后一角色 prompt 含前一产出正文(测试断言 produce 调用参数含 content)

### T3: prepare_project 消费专家 prd 资产(M2→M1 打通)
- **做什么**: prepare_project 若项目存在 HandoffBus 产出的 `prd` 资产 → 用它生成 PRD.md;否则规则兜底(向后兼容)
- **改文件**: `factory-console/session/actions.py` prepare_project(约 442/501 行处)
- **验收断言**: 走"让PM分析"后 prepare_project → PRD.md 含专家产出内容(非规则模板);无专家资产 → 原行为

### T4: build_team 落盘 registry(专家可见)
- **做什么**: ExpertFactory.build_team 装配后 `registry.add`(agents.json 落盘);保留不自动落盘选项(测试兼容)
- **改文件**: `factory-console/session/expert_factory.py`
- **验收断言**: build_team 后 agents.json 含 7 个 agt-*;查看团队可见

### T5: 真实产出断言(market 资产非占位)
- **做什么**: LLM 可用时 market 资产必须含 LLM 真实内容(≥1 条非"待补充/规则占位"段落);测试断言
- **改文件**: `tests/console/test_m2_agent_core.py` 扩展 + 可能 `pipeline_runner.py`
- **验收断言**: 注入 fake llm_fn → market 资产含 fake LLM 输出

## 2. 契约要求

```
1. llm_fn 注入点保留(测试/生产同路径, 无特判)
2. 无 LLM → 确定性兜底非空(不破坏现有)
3. created_by=agent_id + parent_artifact 血缘保留
4. 失败明确报错(禁静默)
```

## 3. 验收标准(可断言)

| # | 断言 |
|---|---|
| 1 | 配置 LLM → "让PM分析" 7 资产含 LLM 内容(非规则占位) |
| 2 | 后一角色 produce 收到前一资产正文(prompt 含 content) |
| 3 | "让PM分析" → prepare_project → PRD.md 含专家产出(非规则模板) |
| 4 | build_team → agents.json 含 7 个 agt-* |
| 5 | M1 链路零回归;全量 0 failed(runtime flaky 除外) |
| 6 | 版本 v1.1.10 同步 |

## 4. 明确不做(防漂移)

- ❌ expert build CLI
- ❌ 审批→PR 链路 / 真实 issue 源(E4)
- ❌ 记忆回流(E5)
- ❌ A6 多 LLM 路由 / 真 MCP 工具进循环
- ❌ M3 递归原子拆解(但 T3 已为 M3 铺路: PRD 消费链打通)

## 5. 版本

v1.1.9 → **v1.1.10**(同步 pyproject/install.sh/docs/CHANGELOG/版本断言)

## 6. 完成标准

1. T1-T5 落地,每任务独立提交
2. 配置 LLM 的真实环境: "我要做CRM" → 让PM分析 → 7 专家 LLM 产出 + 互引 → prepare_project → PRD 含专家内容
3. Hermes 独立验证(定向 + 全量)
4. git clean + push + Completion Report

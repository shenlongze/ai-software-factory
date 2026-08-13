# S10-023 Phase 3 真实执行报告 — LLM Real Execution Activated

> 日期:2026-08-13 | 状态:✅ 成功 | 前置:S10-021 Control Plane + S10-022 Model Catalog + S10-023 CLI 装配修复
> 性质:第一次真实 LLM 生产执行闭环(Task→Model→LLM→Artifact→Audit→Usage)
> 证据:真实 DeepSeek API 调用(非 mock),完整链路已跑通

---

## 1. 执行摘要

**AI Factory 第一次真实 LLM 生产执行成功。**

- 任务:E2-001(Echo test,最简可验证任务)+ backend-1 Agent
- 链路:providers.json → LLMControlPlane → workflow_runner._build_provider → OpenAIProvider(DeepSeek 兼容端点)→ 真实 API → ExecutionResult → Runtime Session
- 结果:**status=success**,耗时 1.32s,费用 $0.000233

## 2. 执行记录(用户要求的 6 项指标)

| 指标 | 值 | 来源 |
|---|---|---|
| provider_id | deepseek(记录器标识 deepseek-rec) | session llm_request_sent 事件 |
| model_id | deepseek-chat | ControlPlane resolve_runtime_config |
| tokens | prompt=750 / completion=55 / total=805 | ExecutionResult.usage |
| latency | 1.32s | ExecutionResult duration |
| cost | $0.000233 | ExecutionResult usage.estimated_cost_usd |
| status | success | session execution_completed |

## 3. 链路验证(逐环节)

| 环节 | 证据 |
|---|---|
| providers.json → ControlPlane | selected_provider_id=deepseek;resolve_runtime_config 返回 model/base_url/key 解析成功 |
| ControlPlane → Provider | _build_provider 经 ControlPlane 装配 OpenAIProvider(DeepSeek 端点,实例级 provider_id 覆盖) |
| Provider → 真实 API | DeepSeek 返回 750/55 tokens 的真实响应(PONG 冒烟 + E2-001 完整执行) |
| Response → Artifact | ExecutionReport:patch 8 diff lines,1 个结构化操作(create_file);validation PASS |
| Artifact → Audit | runtime-session rs-7ce6c4b3:agent_started→task_received→thinking_started→decision_created→llm_request_sent→llm_response_received→output_generated→execution_completed |
| Usage | ExecutionResult.usage 记录 tokens/cost;Recorder 记录 latency |

## 4. 关键发现(诚实记录)

### 4.1 过程中发现并解决的问题
1. **8011 后端 PYTHONPATH 缺仓库根** → service 自装配异常被失败安全吞掉 → 诚实 FAILED。修复:启动命令挂完整 PYTHONPATH(含仓库根)
2. **API 调用必须传 context.project_dir** → execution_loop.py:796 前置校验:FINAL 路径需要 project_dir,缺失时返回误导性错误 "no LLM provider configured"。**实际是 project_dir 缺失,不是 provider 问题**——错误消息应改进(记录为 P2 改进项)
3. **LLM 尝试 create_file 已存在文件** → 首次用含 main.py 的项目目录失败(诚实报 operation error)。换空目录后成功。属 LLM 操作选择问题,非链路 bug

### 4.2 记录缺口(两条路径设计分离,非 bug,需知悉)
1. **events.db 无 org.execution.*** 事件** — exec 路径用 RuntimeSessionStore(runtime-sessions/sessions.json),org.execution 事件是 org 编排层(workflow)另一套机制。API runtime execute 路径的审计在 session 内,不在 org events
2. **provider.usage.recorded 仍为 hermes** — factory-core UsageStore 只服务 hermes adapter;exec 路径 usage 在 ExecutionResult + Recorder。两条 usage 记录路径未统一(Phase 4 Router 数据基础需考虑合并)

### 4.3 审批门确认
- Patch 未应用:报告明确 "human review required before apply (execution.approved gate)" — 符合治理设计(执行产出需人工审批才落地),非缺陷

## 5. 冒烟验证过程(时间线)

| 步骤 | 结果 |
|---|---|
| 1. ControlPlane 装配验证 | ✅ selected=deepseek, model=deepseek-chat, key 解析成功 |
| 2. 最小真实 API 调用(max_tokens=64) | ✅ PONG, 12 tokens, $0.000045, 0.799s |
| 3. 后端 8011 启动(完整 PYTHONPATH + key 注入) | ✅ 200 |
| 4. execute_runtime_task 无 project_dir | ❌ 诚实 FAILED("no LLM provider configured" — 实际缺 project_dir) |
| 5. 含 main.py 项目目录 | ❌ 诚实报 create_file 冲突(LLM 操作选择) |
| 6. 空项目目录 | ✅ **success** — 完整闭环 |

## 6. 成本汇总

| 调用 | tokens | cost |
|---|---|---|
| PONG 冒烟 | 12 | $0.000045 |
| E2-001 执行 | 805 | $0.000233 |
| **合计** | 817 | **$0.000278**(不到 0.03 美分) |

## 7. 结论

**Phase 3 目标达成:AI Factory 第一次真实生产执行闭环已跑通。**

- Task → Model → LLM → Artifact → Audit → Usage 全链真实可用
- 数据基础已建立:provider_id/model_id/tokens/latency/cost/status 全部可记录(供未来 Smart Router)
- 费用极小($0.000278),key 未落盘、日志无 key、全程诚实(失败不伪造、成功有证据)

### 遗留改进项(非阻塞,后续 Sprint 可选)
- P2:execution_loop.py:796 错误消息改进(区分 "project_dir missing" 与 "provider key missing")
- P2:两条 usage 记录路径统一(exec Recorder ↔ factory-core UsageStore)

---

> 报告完毕 | 真实执行证据:runtime-session rs-7ce6c4b3 + ExecutionResult(EXR-db568d84)+ DeepSeek API 实际响应
> 未修改任何代码(仅运行时配置 providers.json + 临时项目目录,已清理)

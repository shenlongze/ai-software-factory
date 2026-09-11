# Kernel 契约抽取清单（Phase 0.6）

> 日期: 2026-09-11 | 性质: **只读产出（未搬家/未建目标目录/未改 import/未删文件）**
> 背景: kernel.* 候选 83 文件中——**41 实现（不合格）/ 20 合格（接口4+注册表2+事实源14）/ 22 误归**
> 目标: 回答"从 41 个实现里抽出什么进 kernel 契约"

## 一、41 个实现的抽取结论（逐行）

| 现文件 | 目标 kernel 段 | 要抽出的契约 | 剩余部分降级到 | 依据 |
|--------|---------------|-------------|---------------|------|
| `factory-console/agent_policy.py` | kernel.governance | `PolicyCheck`(Protocol: check(action)->Decision) | services.organization | Agent 权限策略 = 治理 Gate 契约 |
| `factory-console/api/review_feedback.py` | ~~kernel.governance~~ | **误归** → projections.gateway | projections.gateway | api/ 层是投影网关 |
| `factory-console/audit/__init__.py` | kernel.events | 无契约（导出聚合） | 随 audit/ 留 kernel.events | 包导出 |
| `factory-console/audit/audit_context.py` | kernel.events | `TraceContext`(dataclass) | kernel.events | 上下文数据契约 |
| `factory-console/audit/audit_emitter.py` | kernel.events | `AuditSink`(Protocol: emit(event)) | kernel.events | 事实写入 SPI |
| `factory-console/audit/audit_explain.py` | kernel.events | 无契约，整体降级 | services.observation_runtime | 解释逻辑是服务 |
| `factory-console/audit/audit_integrity.py` | kernel.events | `IntegrityVerifier`(Protocol) | kernel.events | 链完整性契约 |
| `factory-console/audit/audit_query.py` | kernel.events | `AuditQuery`(Protocol: query(filter)) | kernel.events | 事实读取 SPI |
| `factory-console/audit/trace_context.py` | kernel.events | 无契约（与 audit_context 重复） | 合并入 kernel.events | 同上 |
| `factory-console/chat_store.py` | kernel.conversation | `ConversationStore`(Protocol) | kernel.conversation | 会话存储 SPI |
| `factory-console/config.py` | ~~kernel.governance~~ | **误归** → bootstrap | bootstrap | 配置属装配层 |
| `factory-console/console_sessions.py` | kernel.conversation | `SessionRegistry`(Protocol) | projections.cli | 会话注册契约 |
| `factory-console/conversation_app.py` | kernel.conversation | `ConversationService`(Protocol: handle(msg)->Goal) | services.* (实现) | 会话入口契约 |
| `factory-console/conversation_os.py` | kernel.conversation | 无契约，整体降级 | archive/legacy(LEGACY 已标) | LEGACY REPL |
| `factory-console/conversation_quality.py` | kernel.conversation | 无契约，整体降级 | services.* | 质量评估是服务 |
| `factory-console/external_skills.py` | kernel.capability | `SkillProvider`(Protocol: list/resolve) | extensions.skills | 能力提供 SPI |
| `factory-console/governance_service.py` | kernel.governance | `GovernanceGate`(Protocol: request/decide) | services.approval_runtime | 治理 Gate 契约(复杂流程降服务) |
| `factory-console/integrity_lock.py` | kernel.governance | 无契约，整体降级 | infrastructure.* | 锁是基础设施 |
| `factory-console/llm_control.py` | kernel.governance | `BudgetControl`(Protocol) | services.* | 预算挂点契约 |
| `factory-console/llm_semantic_interpreter.py` | kernel.conversation | `Interpreter`(Protocol: interpret(text)->Intent) | extensions.models | 语义解释是插件 |
| `factory-console/node_runtime.py` | kernel.node | `NodeExecutor`(Protocol: run(node)->Result+Evidence) | extensions.factories(流程) | 执行节点核心契约 |
| `factory-console/ops_scheduler.py` | kernel.scheduler | 无契约，整体降级 | infrastructure.* (cron) | 定时器非任务调度 |
| `factory-console/os_core_capability.py` | kernel.capability | `CapabilityRegistry`(Protocol: register/resolve) | services.* | 能力注册表契约 |
| `factory-console/os_core_execution.py` | kernel.node | `ExecutionRecord`(dataclass) | kernel.node | 执行事实契约 |
| `factory-console/os_core_resolution.py` | kernel.capability | `Resolver`(Protocol: resolve(req)->Binding) | kernel.capability | 能力解析 SPI |
| `factory-console/os_core_runtime.py` | kernel.node | `RuntimeAdapter`(Protocol) | extensions.models | 运行时适配(provider 调用降插件) |
| `factory-console/os_core_scheduler.py` | kernel.scheduler | `Scheduler`(Protocol: next(state)->Unit) | kernel.scheduler | **调度核心契约** |
| `factory-console/os_core_task.py` | kernel.node | `Task`(dataclass) | services.work | 任务数据契约 |
| `factory-console/os_core_task_node.py` | kernel.node | `TaskNode`(dataclass) | kernel.node | 计划单元契约 |
| `factory-console/product_understanding.py` | kernel.conversation | `Understanding`(Protocol: process(msg)->Fact) | services.* | 理解服务契约 |
| `factory-console/production_runtime.py` | kernel.node | 无契约，整体降级 | extensions.factories | 生产 runtime 是 Factory 实现 |
| `factory-console/retry_policy.py` | kernel.node | `RetryPolicy`(dataclass) | kernel.node | 重试策略契约 |
| `factory-console/review_feedback.py` | kernel.governance | `ReviewGate`(Protocol: review(artifact)) | services.* | 评审 Gate 契约 |
| `factory-console/run_liveness.py` | kernel.node | `LivenessProbe`(Protocol) | infrastructure.* | 存活探测是基础设施 |
| `factory-console/semantic_proposal.py` | kernel.conversation | `Proposal`(dataclass) | services.* | 提案数据契约 |
| `factory-console/session/answer_verify.py` | kernel.conversation | 无契约，整体降级 | services.* | 验证是服务 |
| `factory-console/session/capability_router.py` | kernel.capability | `CapabilityRouter`(Protocol) | kernel.capability | 路由契约(与 Resolver 合并) |
| `factory-console/session/conversation.py` | ~~kernel.conversation~~ | **误归** → archive(M3) | archive/session-m3 | M3 旧链 |
| `factory-console/session/dialog_style.py` | kernel.conversation | 无契约，整体降级 | projections.cli | 展示风格属投影 |
| `factory-console/session/intent_core.py` | kernel.conversation | `Intent`(dataclass) | kernel.conversation | 意图契约 |
| `factory-console/session/messages.py` | kernel.conversation | `Message`(dataclass) | kernel.conversation | 消息契约 |

**统计**：有契约可抽 **31** / 无契约整体降级 **8**（audit_explain/conversation_os/conversation_quality/integrity_lock/ops_scheduler/production_runtime/answer_verify/dialog_style）/ 误归 **3**（api/review_feedback · config · session/conversation）

## 二、kernel 六段契约清单（抽出后应存在）

| 段 | 应存在的契约 | 从哪几个实现抽 | 优先级 |
|----|-------------|---------------|--------|
| **conversation** | `ConversationService` · `ConversationStore` · `Intent` · `Message` · `Understanding` | conversation_app · chat_store · intent_core · messages · product_understanding | P1 |
| **capability** | `CapabilityRegistry` · `Resolver` · `CapabilityRouter` · `SkillProvider` | os_core_capability · os_core_resolution · capability_router · external_skills | P1 |
| **scheduler** | `Scheduler`(next(state)->Unit) | os_core_scheduler（主）+ production_run/org.execution（就绪判定） | **P0** |
| **node** | `NodeExecutor` · `ExecutionRecord` · `TaskNode` · `RetryPolicy` · `RuntimeAdapter` | node_runtime · os_core_execution · os_core_task_node · retry_policy · os_core_runtime | **P0** |
| **events** | `AuditEvent` · `AuditSink` · `AuditQuery` · `IntegrityVerifier` · `TraceContext` | audit/{audit_event,audit_emitter,audit_query,audit_integrity,audit_context} | P1 |
| **governance** | `GovernanceGate` · `PolicyCheck` · `BudgetControl` · `ReviewGate` | governance_service · agent_policy · llm_control · review_feedback | P1 |

**六段均有契约可抽**（无空段）✅

## 三、scheduler 专项

**kernel.scheduler 应暴露的契约（签名级）**：
```python
class Scheduler(Protocol):
    def next(self, state: ExecutionState) -> ExecutionUnit | None: ...
    # 只读事实状态 → 返回下一个该执行谁（含就绪判定），不含执行
```

**从哪抽**：
| 源 | 抽什么 | 剩余降级到 |
|----|-------|-----------|
| `production_run.py` | 依赖就绪判定（`depends_on` → ready/BLOCKED 逻辑） | extensions.factories（workflow 编排保留） |
| `org/execution.py` | `plan_tasks` 的排序**数据契约** | services.organization（组织级执行模型） |
| `golden_path.py` | 图编排的"下一个叶"判定 | extensions.factories |
| `session/scheduler.py` | ❌ 不抽（M3 dead） | archive |

## 四、依赖违规 10 处修复建议

| 违规路径 | 类型 | Phase 1 时如何修 |
|---------|------|-----------------|
| `os_core_{evidence,execution,outcome,plugin,professional,resolution,task,task_node,work,runtime}.py` | kernel 内部 `from .os_core_X import <具体函数>`（越 contracts 直连实现） | Phase 1 抽契约时，改为 import `kernel/*/contract.py` 的 Protocol/dataclass；实现间调用改经注册表注入 |

**汇总**：10 处均为"kernel 内部跨段直连具体实现"——抽契约后统一改为**依赖 contracts + DI 注入**即可解。

---

# HARD STOP 触发记录

| 条件 | 结果 |
|------|------|
| 精确重跑后 factory-core asset 106 → **8**（<30） | ✅ **触发**（原数字严重失真：base 名匹配虚高 98 个） |
| factory-exec asset 38 → **2** | ✅ 同上（虚高 36） |
| 六段契约清单为空且 UNCLEAR | ❌ 未触发（六段均有契约） |
| 41 实现里 ≥20 标"无契约整体降级" | ❌ 未触发（仅 8） |

**含义**：`factory-core` 实为 **121 legacy / 9 contract / 8 真 covered** —— 几乎全是废弃代码（宪法未覆盖的 L4 旧层），archive 判定**成立**；上次 asset 106 是方法缺陷，已修正。

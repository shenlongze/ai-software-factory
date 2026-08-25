# S10-120 — K-4 trace_id 贯穿：设计文档 + 实现计划（CTO 架构设计 + Codex 指令）

> 日期: 2026-08-25 | 前置: v1.1.89 · K-1~K-3 ✅ (战役第四战役, Founder 拍板提前)
> 用途: 三部门循环第 ②→③ 步 — Hermes(CTO) 设计 → Codex(工程) 实现
> 规格来源: docs/sprint10/S10-120 提示词（K-4: I-1 + F-9 最小面）

---

## 0. 现状审计（CTO 独立复核）

| 资产 | 现状 | 缺口 |
|---|---|---|
| AuditEvent | audit_event.py L195-196: trace_id/correlation_id 字段 (默认 "") | **从未填充** (实测 2408 条全空) |
| AuditStore | query(trace_id=) / get_chain(trace_id) 已实现 (audit_store.py L162/166) | trace_id 空 → 不可用 |
| audit_trace action | actions.py L3465 已注册 (S10-069) | 实际不可用 (全空) |
| AuditEmitter.emit | L66: **fields 可传 trace_id, 64 发射点无人传 | 无自动填充 |
| CostRecord | trace_id 可选字段 (S10-065) | 未填充 |
| 入口 | InteractiveSession._dispatch (session.py:340) / fastapi 路由 (fastapi_adapter) / CLI / exec runtime | 无 trace 上下文 |

版本: 1.1.89 → 目标 1.1.90。

## 1. 架构决策

### 1.1 Trace 上下文（核心机制, 新模块 `factory-console/audit/trace_context.py`）

```python
_trace_var: ContextVar[Optional[str]] = ContextVar("factory_trace_id", default=None)
_correlation_var: ContextVar[Optional[str]] = ContextVar("factory_correlation_id", default=None)

def new_trace_id() -> str: ...                    # uuid4 hex (确定性生成)
def get_trace_id() -> str:                        # contextvar → str; 无上下文/异常 → "" (失败安全)
def get_correlation_id() -> str: ...
def set_trace(trace_id: str, correlation_id: str = "") -> None
def trace_context(trace_id: str, correlation_id: str = "") -> ContextManager  # 入口用 (with 自动 reset)
def child_correlation(trace_id: str) -> str       # 父子关联: 子动作 correlation = f"{trace_id}:{n}"
```

- contextvar (线程安全, 不跨请求泄漏 — with 块退出自动恢复)
- 无上下文 → "" (向后兼容, 旧路径零变化)

### 1.2 入口生成 trace_id（一次请求全程同一）

1. **InteractiveSession._dispatch** (session.py:340): 每用户输入 → `with trace_context(new_trace_id())` 包整个 dispatch
2. **fastapi**: ASGI/路由中间件 — 每请求生成 trace_id (请求头 X-Trace-ID 可选覆盖)
3. **CLI 命令执行**: cli_factory run/main 入口包 trace_context
4. **exec runtime**: agent_runtime 执行包 trace_context (子任务 correlation 关联)

### 1.3 AuditEmitter.emit 自动填充（64 发射点零改动）

- emit 内部: trace_id 未显式传 (或空) → 读 contextvar; correlation_id 同理
- 显式传的 trace_id 优先 (不覆盖)

### 1.4 执行/成本链路

- execution_records: record += trace_id (contextvar)
- cost_records: CostLedger.record trace_id (contextvar)

### 1.5 验证面 + F-9 最小面

- audit_trace(trace_id) 返回该链路全部事件 (现成 action 激活)
- 审计决策链可用 (S10-069)
- F-9: 关键调试日志带 trace_id (audit + 执行入口日志 — 最小面, 不铺开)

### 1.6 注册表门禁

- 无新 CLI/API (audit_trace 已注册) → 零注册表改动; 若加查询入口须同步

## 2. 契约测试（tests/console/test_s10_120_trace_chain.py, ≥8）

1. **CLI 贯穿一致**: 一次 _dispatch 输入 → 该请求全部审计事件 trace_id 非空且相同
2. **API 贯穿一致**: TestClient 请求 → 事件 trace_id 一致
3. **audit_trace 可用**: trace_id → 返回该链路全部事件; 决策链可用
4. **无上下文零变化**: 直接 emit 不设 context → trace_id="" (旧行为)
5. **父子关联**: 子动作 correlation_id 关联 trace (get_chain 含子链)
6. **execution_records 带 trace_id**: 执行记录含 trace_id
7. **cost_records 带 trace_id**: cost 记录含 trace_id
8. **失败安全**: contextvar 异常 → "" 不崩
9. 全量回归 0 新增失败

## 3. 版本与发布

- pyproject `1.1.89` → `1.1.90`; CHANGELOG v1.1.90; 版本断言同步; docs/FEATURES.md;
  docs/sprint10/待办清单-已发现未落地.md: K-4 L18 ✅ + I-1 L232 ✅ + F-9 L194 ✅

## 4. Codex 实施范围

**Allowed/Files**:
- NEW `factory-console/audit/trace_context.py` (contextvar + set/get/trace_context/child_correlation)
- MOD `factory-console/audit/audit_emitter.py` (emit 自动填充 trace_id/correlation_id — 显式优先)
- MOD `factory-console/session/session.py` (_dispatch 入口包 trace_context)
- MOD `factory-console/web/backend/fastapi_adapter.py` (请求中间件 trace_id)
- MOD `factory-console/cli_factory.py` (CLI 命令入口包 trace_context)
- MOD `factory-exec/exec/agent_runtime.py` (执行入口 + 子任务 correlation)
- MOD `factory-console/session/actions.py` (execution_records += trace_id)
- MOD `factory-console/session/cost_ledger.py` (record += trace_id contextvar)
- NEW `tests/console/test_s10_120_trace_chain.py`
- MOD pyproject.toml / CHANGELOG.md / 版本断言 / docs/FEATURES.md / docs/sprint10/待办清单-已发现未落地.md

**Forbidden（硬边界）**:
- 不做 I-2 链路可视化 / I-3 链路可控 (K-8 战役)
- 无 trace 上下文路径 → trace_id="" (旧行为零变化); 不伪造不泄漏
- 审计封存/哈希/血缘语义不变; contextvar 不跨请求泄漏
- 不调 LLM; 纯确定性; 失败安全 (contextvar 读取失败 → "" 不崩)
- 禁 git add -A; 禁新增第三方依赖

**Validation**:
- `pytest tests/console/test_s10_120_trace_chain.py -q` 全绿
- env -u 聚焦 (audit/session/actions/cost_ledger + 既有审计/会话测试) 全绿
- env -u 全量 console+api 0 新增失败 (并发未提交改动隔离验证)
- 实测: CLI/API 贯穿一致; audit_trace 可用; 无上下文零变化; records 带 trace_id
- commit: `feat(S10-120): K-4 trace_id贯穿 — contextvar 入口生成 + emit自动填充 + audit_trace可用 + 执行/成本链路, v1.1.90`

## 5. 验收标准（Hermes 独立验证）

- [ ] 1. CLI 一次请求 → 全部审计事件 trace_id 非空相同
- [ ] 2. API (TestClient) → 事件 trace_id 一致
- [ ] 3. audit_trace 返回该链路全部事件; 决策链可用
- [ ] 4. 无上下文路径 → trace_id="" 零变化
- [ ] 5. execution_records / cost_records 带 trace_id
- [ ] 6. 契约测试 ≥8 全绿
- [ ] 7. 全量回归 0 新增失败
- [ ] 8. v1.1.90 + K-4/I-1/F-9 ✅
- [ ] 9. 设计文档落盘

## 6. 诚实记录要求

- 无法贯穿的路径 (历史记录/无上下文调用) 如实标注, 不伪造 trace_id
- contextvar 与线程模型冲突 → 列出征询, 不擅自扩大

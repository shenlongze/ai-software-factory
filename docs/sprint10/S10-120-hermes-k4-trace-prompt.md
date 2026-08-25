# S10-120 · K-4 trace_id 贯穿（I-1 + F-9）— Hermes 提示词（2026-08-25）

> 战役: K-4（docs/战役规划-统一路线.md §2 K-4）· 目标版本 v1.1.90（当前 HEAD v1.1.89）
> 交付后: 待办清单 K-4/I-1/F-9 ✅ · 战役规划状态追踪 K-4 ✅

---

请作为 Hermes 派发 Sprint 任务给 Codex，遵守既有纪律（pre-flight → plan → dispatch → verify → acceptance → report）。

【任务】S10-120 · K-4 trace_id 贯穿（战役规划第四战役）
版本目标：v1.1.90（从实际 HEAD +1；若并发消耗则顺延，不回退版本）

【背景（K-4 是什么）】
战役规划第四战役（依赖无，成本低收益高——Founder 拍板提前）。审计/评测/链路可视化的地基：
一次请求从入口到执行全程带同一 trace_id，审计可按 trace_id 追踪。
合并项：I-1 trace_id 贯穿 · F-9 日志 trace 落盘（最小面）。

【现状（实事求是，pre-flight 必须核对，不限于此）】
1. AuditEvent 已有 trace_id/correlation_id 字段（audit_event.py:195-196, 默认 ""）——从未填充
2. 实测 2408 条审计事件 trace_id/correlation_id 全空（能力缺口 I-1）
3. AuditStore.query(trace_id=...) / get_chain(trace_id) 已实现（audit_store.py）——
   审计追踪/审计决策链 action 已存在（actions.py audit_trace/audit_decision_chain, S10-069）
   但因 trace_id 全空实际不可用
4. cost_ledger.py CostRecord 有 trace_id 字段（S10-065）也未填充
5. AuditEmitter.emit 64 个发射点（actions/service）——trace_id 经 **fields 可传但无人传
6. 入口: InteractiveSession._dispatch（CLI）/ fastapi 路由 / exec runtime / /board 相关

【设计与实现要求（先出设计文档 docs/sprint10/S10-120-k4-trace-plan.md，批准后再实现）】
1. Trace 上下文（核心机制）:
   - 模块级 contextvar（Python 3.12 线程安全）: ContextVar[Optional[str]]
   - 入口设置, AuditEmitter.emit 读取（trace_id 未显式传 → 读 contextvar）
   - 无上下文 → ""（向后兼容, 旧路径零变化——不泄漏不伪造）
2. 入口生成 trace_id（一次请求全程同一）:
   - InteractiveSession._dispatch 每用户输入
   - fastapi 每请求（中间件或路由入口统一设置）
   - CLI 命令执行
   - exec runtime 执行
3. correlation_id: 父子关联（项目运行 → 子任务/子动作）——同一 trace 内可再关联
4. AuditEmitter.emit 自动填充: trace_id/correlation_id 未显式传 → 读 contextvar（64 发射点不用逐个改）
5. 执行/成本链路: execution_records + cost_records 也带 trace_id（同 contextvar）
6. 验证面: audit_trace(trace_id) 返回该链路全部事件; 审计决策链可用（S10-069 现成 action 激活）
7. F-9 最小面: 关键调试日志带 trace_id（audit + 执行入口日志即可, 不铺开）
8. 注册表门禁（P0-10/11）: 无新 CLI/API 则零注册表改动; 若加 trace 查询入口须同步注册表

【硬边界】
- 只做 trace 贯穿, 不做 I-2 链路可视化 / I-3 链路可控（K-8 战役）
- 无 trace 上下文路径必须 trace_id=""（旧行为零变化, 诚实标注未贯穿路径）
- 审计封存/哈希/血缘语义不变; contextvar 不跨请求泄漏
- 不调 LLM; 纯确定性; 失败安全（contextvar 读取失败 → "" 不崩）

【验收标准（独立可验证，非 Codex 自报告）】
1. CLI 输入一次请求 → 该请求全部审计事件 trace_id 非空且相同（fixture 断言）
2. API 请求（TestClient）→ 事件 trace_id 一致
3. audit_trace(trace_id) 返回该链路全部事件; 决策链可用
4. 无上下文路径（直接调 emit 不设 context）→ trace_id="" 零变化
5. execution_records / cost_records 带 trace_id
6. 契约测试 ≥8（贯穿一致/API/审计追踪可用/无上下文零变化/父子关联/失败安全）
7. 全量回归 0 新增失败（环境性失败如实标注, 与 HEAD 基线对照）
8. 版本 v1.1.90（pyproject + CHANGELOG + FEATURES + 版本断言 + 待办清单 K-4/I-1/F-9 ✅ 同步）
9. 设计文档落盘 docs/sprint10/S10-120-k4-trace-plan.md

【诚实记录】任何无法贯穿的路径（如历史记录、无上下文调用）如实标注, 不伪造 trace_id;
改动波及面超预期（如 contextvar 与现有线程模型冲突）→ 列出并征询, 不擅自扩大

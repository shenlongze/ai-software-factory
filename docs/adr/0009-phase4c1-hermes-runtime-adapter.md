# ADR-0009: Phase 4C-1 Hermes Runtime Adapter — 调用方案/失败映射/配置/CLI smoke 语义

> 状态: 已接受 | 日期: 2026-08-05 | 作者: 后端开发工程师
> 关联: `docs/design/phase4c1-status.md` · `docs/adr/0007-phase4b2-execution-dispatch.md` · `docs/adr/0006-phase4b1-runtime-adapter.md` · `docs/architecture.md` §7.1

## 背景

Phase 4B-2 建立了派发层 (Dispatcher/Runner/Service) 与首个 mock 实现 EchoRuntimeAdapter;
本阶段落地首个**真实** RuntimeAdapter — HermesRuntimeAdapter, 经 subprocess 调用本机
`hermes` CLI 执行 Agent 任务。设计文档只约定"构造 Hermes 调用参数 (如 --task/--step/
--instruction) + subprocess + 失败转 FAILED", 落地时有四处设计张力需明确:

1. **Hermes CLI 调用形态**: hermes CLI 没有 --task/--step/--instruction 参数
   (设计文档"如"为示例); 需确定实际 argv 形态与 input 四字段 (task/step/instruction/
   agent_id) 的映射方式。
2. **失败处理清单的映射**: 命令不存在 (FileNotFoundError) / timeout (TimeoutExpired) /
   exit≠0 / stdout 空 → FAILED — error 消息的形态、OS 级错误 (PermissionError 等)
   是否也兜底、结果 id/request_id 绑定。
3. **命令与超时的配置入口**: 本机无 hermes 的环境 (CI/测试/其他机器) 如何验证 FAILED
   路径; 命令名/超时是否可覆盖。
4. **CLI `runtime test` smoke 语义**: 是否要求身份已注册、退出码语义 (SUCCESS/FAILED/
   未注册)、smoke 是否落库/发事件 (Adapter 不写 Event, ADR-0002 要求 CLI 行为留痕)。

## 决策

1. **调用方案: `hermes -z <prompt>` one-shot prompt 模式** (KISS, 已在本机验证:
   非交互、stdout 出结果、exit 0):
   - argv = `[command, "-z", prompt]`; prompt 由 input 四字段组合 —
     task/step/agent_id 作为前缀上下文行 (`task: T-001\nstep: dev\nagent_id: A-001`),
     instruction 为正文; input 全空时兜底 `execute execution <id>`
     (prompt 永不为空, -z 必带参数)。
   - 输出协议落地 (设计文档"output (str 或 dict)"取 dict): SUCCESS 结果
     `output = {stdout, instruction, runtime_id, exit_code}`; FAILED 结果 output 为空 dict。
   - 结果 id 从执行 id 派生 (`EXR-<execution_id>`, 同 echo), request_id 绑定请求
     (派发层校验依赖, ADR-0007 决策 1)。
2. **失败处理: 全部转 FAILED 结果, 不抛未处理异常** (error 消息前缀稳定供测试/审计):
   - FileNotFoundError → `hermes command not found: <command>`
   - subprocess.TimeoutExpired → `hermes command timed out after <timeout>s`
   - 其他 OSError (PermissionError 等) → 防御兜底转 FAILED (OS 级错误不属 4 类清单,
     但同属"无法执行", 统一不抛)
   - exit code ≠ 0 → `hermes command exited with code <rc>: <stderr 或 stdout>`
   - exit 0 但 stdout 为空 (含纯空白) → `hermes command produced no output (stdout empty)[: <stderr>]`
     — stdout 是唯一结果通道, 空输出视为未完成 (已实测 hermes 结果走 stdout, stderr 空)。
   - 未列举的意外异常仍交由 Runner 防御 catch 转 FAILED (ADR-0007 决策 4 不变)。
3. **配置: 环境变量覆盖 + 构造参数优先**:
   - `FACTORY_HERMES_CMD` (默认 `hermes`, 走 PATH) / `FACTORY_HERMES_TIMEOUT`
     (默认 300s, one-shot 调用可达分钟级) — 无 hermes 环境可指到假命令验证 FAILED
     路径, 测试可注入假命令; 构造函数 `HermesRuntimeAdapter(command=, timeout=)`
     优先于环境变量。
   - 不改 RuntimeAdapter 抽象接口 / 事件 API / 其他模块 (纯增量新文件)。
4. **CLI `factory runtime test <runtime_id>` smoke 语义**:
   - 前置: runtime 身份须已注册 (registry 是派发解析的唯一事实源, ADR-0007 决策 3
     不变); 已注册但无内置实现 → 配置缺口 rc 1 (同 cmd_execution_run 契约)。
   - 退出码: 0 = smoke SUCCESS / 1 = smoke FAILED (runtime 不健康) 或配置缺口 /
     7 = runtime 未注册 (cli-design §5)。业务 FAILED 与 execution run 不同
     (run 命令 rc 0) — smoke 是健康检查, FAILED 即命令失败, rc 1 便于脚本消费。
   - 副作用边界: smoke 构造最小 execution (`id=EX-SMOKE-<runtime_id>`,
     task_id=SMOKE, input={instruction: 默认 "Reply with exactly: OK"}),
     **不落库** (runtimes.json 无 executions/results 残留)、Adapter 不写 Event;
     本命令仅发 `runtime.viewed` 审计事件 (payload 带 runtime_id/execution_id/
     smoke_status/error, 满足 ADR-0002"所有 CLI 行为必须产生 Event")。

## 后果

- 新文件: `factory-core/runtime/adapters/hermes.py` (HermesRuntimeAdapter, 零依赖
  events/registry/store — ADR-0006 解耦铁律可被测试源码级断言) +
  `runtime/adapters/__init__.py` BUILTIN_ADAPTERS 增加 `hermes-runtime` (实现随包,
  身份仍须 `factory runtime add` 显式注册, 同 echo, ADR-0007 决策 3 不变)。
- CLI: `factory runtime test <runtime_id> [--instruction TEXT]`, 支持 `--json`;
  既有 runtime add/list、execution run/status 行为不变。
- 手动冒烟链路: `runtime add --id hermes-runtime --type agent` →
  `runtime test hermes-runtime` (本机有 hermes → SUCCESS rc 0; 无 hermes /
  FACTORY_HERMES_CMD 指向不存在 → FAILED rc 1, 失败处理路径同样被验证)。
- 测试: `tests/runtime/` 新增 3 文件 84 例 (Mock subprocess.run: 成功/命令不存在/
  timeout/exit≠0/stdout 空/OS 错误 + prompt 构造 + env 配置 + 注册 + CLI smoke +
  Runner 生命周期 + CLI execution run 全链路), 824 基线不回归 (已验: 908 全绿)。
- 风险: `hermes -z` 为真实 LLM 调用 (分钟级耗时、消耗 token) — smoke/执行由调用方
  触发, 超时默认 300s 可配; subprocess 继承调用方环境, hermes 不在 PATH 时须设
  FACTORY_HERMES_CMD。无并发保护 (单进程整文件 JSON 写, 同既有 runtimes.json 假设)。
- 后续 Phase: 多 Agent 编排 / 自动生成代码流程 / Factory 逻辑入 Hermes 均被本阶段
  边界明确禁止 (phase4c1-status §边界), 不在本 ADR 范围内。

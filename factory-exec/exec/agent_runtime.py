"""factory-exec/exec/agent_runtime.py — AgentRuntime (执行权归属: 调 Provider/沙箱/产补丁)。

设计依据 (docs/architecture/phase-a-execution-mvp-design.md §2):
```
Task → ExecutionRequest → Developer Agent (Employee→Agent Instance→Provider)
  → Sandbox (副本 + 修改追踪) → Artifact (patch + test_result + report)
  → Validation (检查) → Human Approval → Apply → Experience
```

执行权归属 (设计 §2 铁律):
- 拥有执行权: AgentRuntime (本模块 — 调 Provider/沙箱/产补丁)
- 只负责描述: ExecutionRequest (声明意图, 不执行)
- 只负责检查: Validation/Approval (门禁, 无执行)
- 只负责记录: Experience (沉淀, 无执行)

职责 (execute):
1. 校验输入 (project_dir 必须; 缺失/不可达 → failed 结果, 不抛)。
2. 沙箱创建 (项目副本, 原项目零接触 — 沙箱铁律)。
3. Developer Agent work (prompt 组装 → Provider → patch 解析 → 报告)。
4. patch 写入沙箱副本 → Validation (语法 + 测试命令, 沙箱内)。
5. patch 导出 (git diff → .patch 文件) + 三 Artifact (patch/test_result/report)。
6. 落库 (request/result/artifacts) + org.execution.* 事件链。

失败语义 (同 subprocess-adapter 模式): 全部路径转 ExecutionResult failed
(error 稳定前缀), 不抛未处理异常 — CLI/审批/Experience 只消费结果对象。
终态事件单一: completed|failed 只发一次, 报告的状态转换完成后发。

验证语义 (设计 §6): 沙箱内测试/分析/报告生成可自动 (不改外部状态);
测试失败不自动 fail 执行 — 留给 Human Approval 例外放行 (设计 §6 例外清单),
test_result Artifact + 报告明示 FAIL, 审批人决定。
"""

from __future__ import annotations

import importlib
import logging
import time
from pathlib import Path
from typing import Any, Optional

from . import events as exec_events
from .candidate import SequentialRunner
from .developer import DeveloperAgent, DeveloperError
from .experience import ExperienceRecorder
from .models import (
    AgentInstance,
    Artifact,
    ArtifactType,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    SandboxSession,
    new_id,
)
from .provider import ProviderInterface
from .sandbox import Sandbox
from .store import ExecStore
from .validation import Validation, ValidationResult

logger = logging.getLogger("factory.exec.agent_runtime")

#: S10-120 K-4: trace 上下文模块 (factory-console.audit.trace_context — 双名
#: 解析同 cli.py 模式; 延迟导入; 失败安全: 不可导入 → None → trace_id 保持 ""
#: 旧行为零变化, 执行链不破坏)。
_TRACE_CTX: Optional[Any] = None
_TRACE_CTX_TRIED = False


def _trace_module() -> Optional[Any]:
    """trace_context 模块 (双名解析同 _console_import, 缓存; 失败安全 → None)。

    关键: factory_console.audit.trace_context 与 factory-console.audit.trace_context
    是**两个独立模块对象** (sys.modules 键不同 → ContextVar 各自独立), 若选错
    名称, session/API 设置的 trace 无法传播到 exec runtime。故按仓库 stub 判定
    优先使用与 factory-console 代码一致的名称 (源码态 → factory-console; 部署态
    → factory_console), 保证同一进程共享同一 ContextVar。
    """
    global _TRACE_CTX, _TRACE_CTX_TRIED
    if _TRACE_CTX_TRIED:
        return _TRACE_CTX
    _TRACE_CTX_TRIED = True
    try:
        import importlib.util as _util

        _spec = _util.find_spec("factory_console")
        _loc = str(_spec.origin or "") if _spec is not None else ""
    except (ImportError, ValueError):  # noqa: BLE001 — 失败安全
        _loc = ""
    _is_repo_stub = (
        "factory_console/__init__.py" in _loc.replace("\\", "/")
        and "site-packages" not in _loc
    )
    names = (
        ("factory-console.audit.trace_context", "factory_console.audit.trace_context")
        if _is_repo_stub
        else ("factory_console.audit.trace_context", "factory-console.audit.trace_context")
    )
    for name in names:
        try:
            _TRACE_CTX = importlib.import_module(name)
            return _TRACE_CTX
        except (ImportError, ModuleNotFoundError):  # noqa: BLE001 — 失败安全
            continue
    return None


#: 项目上下文文件清单上限 (prompt 体积控制; 真实场景 Agent 可自行读文件)
_PROJECT_CONTEXT_FILE_LIMIT = 60

#: 验证循环总尝试上限 (1 次初始 + 2 轮自动修复 — 任务约束 ≤2 轮, 禁无限循环)
_MAX_VALIDATION_ATTEMPTS = 3


def _project_context(sandbox_dir: Path) -> str:
    """项目文件清单 (相对路径, 隐藏目录跳过; prompt 的项目上下文)。"""
    files: list[str] = []
    if not sandbox_dir.is_dir():
        return "(sandbox missing)"
    for path in sorted(sandbox_dir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(sandbox_dir)
        if any(part.startswith(".") for part in rel.parts):
            continue
        files.append(str(rel))
    if not files:
        return "(empty project)"
    shown = files[:_PROJECT_CONTEXT_FILE_LIMIT]
    lines = "\n".join(f"- {f}" for f in shown)
    if len(files) > _PROJECT_CONTEXT_FILE_LIMIT:
        lines += f"\n... ({len(files) - _PROJECT_CONTEXT_FILE_LIMIT} more files)"
    return lines


def _repo_intelligence_context(sandbox_dir: Path) -> str:
    """Repository Intelligence 轻量上下文 (Phase A++++++-2a)。

    组装: Architecture Summary 摘要 + Call Graph 摘要段 (按文件聚合边数 top),
    帮助 Developer 理解仓库结构/修改影响面。轻量: 不重写 Stage 1 的
    _project_context 文件清单, 只追加架构级摘要。

    失败安全: 分析失败/无文件 → "" (上下文增强不破坏执行链, 与
    _project_context 同语义 — 计算失败不致命)。
    """
    try:
        from .repo_intelligence import RepositoryIntelligence

        ri = RepositoryIntelligence(sandbox_dir).analyze()
        parts: list[str] = []
        if ri.architecture is not None:
            arch_text = ri.architecture.format_text()
            if arch_text.strip():
                parts.append(arch_text)
        cg_text = ri.format_call_graph()
        if cg_text.strip() and cg_text.strip() != "(no call edges detected)":
            parts.append(cg_text)
        return "\n\n".join(parts)
    except Exception:  # noqa: BLE001 — 失败安全: 上下文增强不致命
        return ""


class AgentRuntime:
    """执行运行时: ExecutionRequest → ExecutionResult (全程不抛未处理异常)。

    构造:
    - provider: ProviderInterface (智能来源; CLI 从 ProviderRegistry 解析)。
    - store: ExecStore (None = 纯内存, 不落库 — 单元测试)。
    - logger: EventLogger (None = 事件静默)。
    - validation_command: 沙箱内测试命令 (None = 只做语法检查)。
    - artifacts_dir: 产物落盘根目录 (缺省 store.dir; patches/ 子目录放 patch)。
    - work_root: 沙箱副本父目录 (None = 系统临时目录)。
    - experience: ExperienceRecorder (None = 不记录经验 — 装配点注入)。
    - experience_extractor: T4.4 ContextExperienceExtractor (None = 不提取
      上下文经验 — 装配点注入; 提供 → 任务结束后自动提取 ContextExperienceRecord
      (成功: 有效 Context/最佳 Budget/成功路径; 失败: 结构化 failure_type +
      missing_symbols), 提取/落库异常静默 — 审计增强数据不破坏执行链)。
    - ranking_enabled: T4.1 Ranking Pipeline 新路径开关 (默认 False — 旧
      ContextAssembler.assemble 路径; True → ranking_assemble, 失败安全回退旧路径)。
    - execution_strategy_enabled: T5.2 多 Run 执行策略 Feature Flag (默认
      False — 旧流程逐位不变; True → SequentialRunner N 次独立执行 →
      Candidate 列表 → 临时选择; 策略路径异常 → 失败安全回退旧流程)。
    - execution_strategy_runs: 策略 Run 次数 (默认 3, ≥1 归一)。
    """

    def __init__(
        self,
        provider: ProviderInterface,
        *,
        store: ExecStore | None = None,
        logger: Any = None,
        validation_command: str | None = None,
        artifacts_dir: str | Path | None = None,
        work_root: str | Path | None = None,
        experience: ExperienceRecorder | None = None,
        experience_extractor: Any = None,
        git_bin: str = "git",
        conventions: str | None = None,
        ranking_enabled: bool = False,
        execution_strategy_enabled: bool = False,
        execution_strategy_runs: int = 3,
    ) -> None:
        self._store = store
        self._logger = logger
        self._validation_command = validation_command
        self._artifacts_dir = (
            Path(artifacts_dir) if artifacts_dir is not None
            else (store.dir if store is not None else None)
        )
        self._work_root = work_root
        self._experience = experience
        self._experience_extractor = experience_extractor
        self._git_bin = git_bin
        self._ranking_enabled = ranking_enabled
        self._execution_strategy_enabled = execution_strategy_enabled
        self._execution_strategy_runs = max(1, int(execution_strategy_runs))
        self._last_candidates: list[Any] = []
        self._last_evaluation: Any = None
        self._developer = DeveloperAgent(
            provider, conventions=conventions or _default_conventions()
        )

    def _extract_experience(
        self,
        result: ExecutionResult,
        request: ExecutionRequest,
        *,
        assembler: Any = None,
        validation: Any = None,
        employee_id: str = "",
    ) -> None:
        """任务结束后自动提取 ContextExperienceRecord (T4.4; 失败安全)。

        全链路 Trace 输入: assembler.last_ranking_result (RankingPipelineResult
        — 含 ranking_trace/context_used/progressive/budget_trace); 旧路径
        (assembler None 或未走 ranking) → 对应 trace 缺省空, 提取不破坏。
        """
        if self._experience_extractor is None:
            return
        try:
            ranking = None
            if assembler is not None:
                ranking = getattr(assembler, "last_ranking_result", None)
            progressive = getattr(ranking, "progressive", None) if ranking is not None else None
            budget = getattr(ranking, "budget", None) if ranking is not None else None
            self._experience_extractor.extract(
                result=result,
                request=request,
                ranking=ranking,
                progressive=progressive,
                budget=budget,
                validation=validation,
                context_score=getattr(result, "context_score", None),
                employee_id=employee_id,
            )
        except Exception:  # noqa: BLE001 — 经验提取失败安全 (8B-3 语义)
            pass

    @property
    def developer(self) -> DeveloperAgent:
        return self._developer

    @property
    def store(self) -> ExecStore | None:
        return self._store

    @property
    def last_candidates(self) -> list[Any]:
        """最近一次策略执行的候选列表 (T5.2; 未走策略路径 → 空; 审计用)。"""
        return list(self._last_candidates)

    @property
    def last_evaluation(self) -> Any:
        """最近一次策略评估结果 (T5.3; 未走策略路径 → None; 审计用)。

        EvaluationResult: selected_candidate_id / ranking / score_breakdown /
        rejection_reason — 为什么选它 / 为什么拒绝, 可解释可审计。
        """
        return self._last_evaluation

    # ------------------------------------------------------------------ 内部

    def _fail(
        self, request: ExecutionRequest, error: str, *, duration: float = 0.0,
        employee: Any = None, failure_reason: str = "",
        assembler: Any = None, validation: Any = None,
    ) -> ExecutionResult:
        """构造 failed 结果 + 发 org.execution.failed (终态单一)。

        失败同样记录 Experience (设计 §8: 成功/失败都记录; 失败 = 负信号 +
        failure_reason 结构化 — 供未来复盘/推荐, 不静默失败)。经验失败安全
        (记录异常静默)。

        T4.4: 失败路径同样自动提取 ContextExperienceRecord (assembler/
        validation 由调用方在可用时传入 — 早期失败 (无上下文) → None,
        提取器按失败文本分类, 链路不破坏)。
        """
        result = ExecutionResult(
            id=new_id("EXS"),
            request_id=request.id,
            status=ExecutionStatus.FAILED,
            error=error[:1000],
            duration=duration,
        )
        if self._store is not None:
            self._store.save_result(result)
        exec_events.record_execution_failed(self._logger, request=request, error=error)
        if self._experience is not None:
            try:
                self._experience.record(
                    result=result,
                    employee_id=getattr(employee, "id", "") or "",
                    request=request,
                    failure_reason=failure_reason,
                )
            except Exception:  # noqa: BLE001 — 经验失败安全 (8B-3 语义)
                pass
        self._extract_experience(
            result,
            request,
            assembler=assembler,
            validation=validation,
            employee_id=getattr(employee, "id", "") or "",
        )
        return result

    def _write_artifact_file(self, name: str, content: str) -> str:
        """产物文件落盘 (<artifacts_dir>/<name>); 目录自动创建。"""
        if self._artifacts_dir is None:
            return ""
        target = self._artifacts_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return str(target)

    # ------------------------------------------------------------------ 执行

    def execute(
        self,
        request: ExecutionRequest,
        employee: Any = None,
        agent_instance: Any = None,
    ) -> ExecutionResult:
        """执行请求 → ExecutionResult (沙箱副本 + patch; 全程失败安全)。

        S10-120 K-4 执行入口: 包 trace_context — 一次请求从入口到执行全程
        同一 trace_id (审计/执行/成本可追踪)。已处于 trace 上下文 (session
        dispatch 等调用方) → 继承同一 trace (不分裂链路); 无上下文 (独立
        执行入口) → 生成新 trace_id。失败安全: trace 模块不可导入 → 旧行为
        零变化 (trace_id "")。

        T5.2 Feature Flag (execution_strategy_enabled, 默认 False):
        - False: 旧流程逐位不变 (Task→LLM→Validation 单次执行 → _execute_legacy)。
        - True: 多 Run 执行策略 (SequentialRunner N 次独立执行 → Candidate 列表
          → T5.3 CandidateEvaluator 正式选择; 候选经 last_candidates、评估明细
          经 last_evaluation 审计); 策略路径异常 → 失败安全回退旧流程 (执行链
          不破坏, 同 T4.1 ranking 回退语义)。
        """
        mod = _trace_module()
        trace = mod.get_trace_id() if mod is not None else ""
        # F-9 最小面: 执行入口日志带 trace_id (不铺开; 失败安全)
        logger.debug("agent runtime execute trace=%s task=%s", trace or "-", getattr(request, "task_id", "") or "")
        if trace:
            return self._execute(request, employee, agent_instance)
        if mod is not None:
            with mod.trace_context(mod.new_trace_id()):
                logger.debug(
                    "agent runtime execute trace=%s task=%s",
                    mod.get_trace_id(), getattr(request, "task_id", "") or "",
                )
                return self._execute(request, employee, agent_instance)
        return self._execute(request, employee, agent_instance)

    def _execute(
        self,
        request: ExecutionRequest,
        employee: Any = None,
        agent_instance: Any = None,
    ) -> ExecutionResult:
        """执行请求主体 (S10-120: execute 已建 trace 上下文后执行)。"""
        if self._execution_strategy_enabled:
            try:
                return self._execute_strategy(request, employee, agent_instance)
            except Exception:  # noqa: BLE001 — T5.2 失败安全: 回退旧流程
                pass
        return self._execute_legacy(request, employee, agent_instance)

    def _execute_strategy(
        self,
        request: ExecutionRequest,
        employee: Any = None,
        agent_instance: Any = None,
    ) -> ExecutionResult:
        """多 Run 执行策略 (T5.2; flag 开时): N 次独立顺序执行 → Candidate 收集。

        每次 Run = 独立 Provider 调用 (同一 request/Context, 独立随机性 —
        新沙箱 + 新 generate; 抗单次波动, 不复制 Agent)。Run 状态经
        SequentialRunner 记录 (pending→running→success|failed); 失败候选
        必存 (failure_reason 必填 — 禁静默丢弃)。逐 Run 的 T4.4 经验记录
        由 _execute_legacy 既有接线自动完成 (不重复建库)。

        T5.3: 结果 = CandidateEvaluator 正式选择 (验证通过候选 5 层总分选
        Best — 评估明细经 runner.last_evaluation / self.last_evaluation
        审计, 为什么选它可解释); 全失败 → 最后一个失败结果 + 诚实拒绝理由
        (不静默伪装成功); 候选列表经 last_candidates 属性可审计。

        S10-117 C-3 (K-2): 多候选优选输出增强 — 评估明细 (selected_candidate_id /
        ranking / score_breakdown / rejection_reason) 经 result.evaluation 透出
        (可解释可审计); 单候选路径 (flag 关 → _execute_legacy) 零变化。
        """
        provider_id = getattr(self._developer.provider, "provider_id", "")
        model = getattr(self._developer.provider, "model", "") or ""
        # S10-120 K-4: 子任务 correlation 关联 — 每个候选 Run 是同一 trace 的
        # 子动作 (correlation_id = f"{trace}:{n}", 唯一可排序; get_chain 可寻)。
        mod = _trace_module()
        trace = mod.get_trace_id() if mod is not None else ""

        def _run_executor(_index: int) -> ExecutionResult:
            if mod is not None and trace:
                with mod.trace_context(trace, mod.child_correlation(trace)):
                    return self._execute_legacy(request, employee, agent_instance)
            return self._execute_legacy(request, employee, agent_instance)

        runner = SequentialRunner(
            executor=_run_executor,
            runs=self._execution_strategy_runs,
            provider=provider_id,
            model=model,
        )
        runner.run(request=request)
        self._last_candidates = runner.candidates
        result = runner.select_result()  # T5.3: 经 CandidateEvaluator 正式选择
        self._last_evaluation = runner.last_evaluation
        # C-3: 评估明细随结果透出 (失败安全: 序列化异常 → 保持缺省 {}, 不破坏结果)
        if result is not None and self._last_evaluation is not None:
            try:
                result.evaluation = self._last_evaluation.model_dump(mode="json")
            except Exception:  # noqa: BLE001 — 失败安全
                pass
        return result

    def _execute_legacy(
        self,
        request: ExecutionRequest,
        employee: Any = None,
        agent_instance: Any = None,
    ) -> ExecutionResult:
        """执行请求 → ExecutionResult (沙箱副本 + patch; 全程失败安全)。

        T5.2: 旧流程单次执行路径 (Feature Flag 关闭 / 策略回退时的逐位不变
        行为; execute() 在 flag 关闭时原样派发到此)。

        employee/agent_instance: duck-typed (含 id/name 即可 — org Employee
        或本层 AgentInstance 均可; 零硬依赖 factory-org)。
        """
        started = time.monotonic()
        if self._store is not None:
            self._store.save_request(request)
        agent = agent_instance if agent_instance is not None else AgentInstance(id="developer-1")
        employee_id = getattr(employee, "id", "") or ""
        project_dir = request.input.get("project_dir") if isinstance(request.input, dict) else None
        provider_id = getattr(self._developer.provider, "provider_id", "")

        if not project_dir:
            return self._fail(request, "request.input missing project_dir", employee=employee)
        project_path = Path(str(project_dir))
        if not project_path.is_dir():
            return self._fail(
                request, f"project dir not found: {project_path}", employee=employee
            )
        exec_events.record_execution_requested(
            self._logger, request=request, employee=employee,
            agent=agent, provider_id=provider_id,
        )

        sandbox: Sandbox | None = None
        try:
            sandbox = Sandbox(project_path, work_root=self._work_root, git_bin=self._git_bin)
            session = sandbox.create(request_id=request.id)
        except Exception as exc:  # noqa: BLE001 — 失败安全: 沙箱错误 → failed
            return self._fail(request, f"sandbox error: {exc}", employee=employee)

        exec_events.record_execution_started(
            self._logger, request=request, employee=employee, agent=agent,
            sandbox_path=session.workspace_copy_path,
        )
        # 事件链锚点 (artifact.event_refs: 已发生的 requested/started seq)
        event_refs = self._event_refs(session)

        # 项目上下文 (文件清单; 计算失败不致命 — 空上下文继续)
        try:
            context = _project_context(Path(session.workspace_copy_path))
        except Exception:  # noqa: BLE001 — 上下文失败安全
            context = "(project context unavailable)"

        # Phase A++++++-2a: Repository Intelligence 轻量接入 — Architecture
        # Summary 摘要 + Call Graph 摘要段 (仓库结构/影响面; 失败安全 → 空)。
        try:
            repo_context = _repo_intelligence_context(Path(session.workspace_copy_path))
        except Exception:  # noqa: BLE001 — 上下文增强失败安全
            repo_context = ""

        # Phase A++++++-2b: Context Assembly Engine — 6 节结构化上下文
        # (Task/Architecture/Code/Tests/History/Experience + 质量分)。失败安全:
        # 组装异常 → None → developer 走旧路径 (Stage 1 兼容, 执行链不破坏)。
        # T4.1: ranking_enabled=True → Ranking Pipeline 新路径 (ranking_assemble
        # 内部失败安全回退旧 assemble); 默认 False → 旧路径逐位不动。
        assembled_context = None
        context_score: float | None = None
        assembler: Any = None
        try:
            from .context import ContextAssembler

            analyzer = None
            if self._experience is not None:
                analyzer = getattr(self._experience, "analyzer", None)
            assembler = ContextAssembler(
                Path(session.workspace_copy_path),
                project_dir=project_path,
                analyzer=analyzer,
                git_bin=self._git_bin,
            )
            if self._ranking_enabled:
                assembled_context = assembler.ranking_assemble(request)
            else:
                assembled_context = assembler.assemble(request)
            context_score = assembled_context.context_score
        except Exception:  # noqa: BLE001 — 上下文组装失败安全
            assembled_context = None

        # Phase A++++++-1 验证循环 (Modify → Validate → Fix → Validate, ≤2 轮修复):
        # 每次 work → 应用 patch → 语法/测试验证; 验证失败 → 反馈失败输出给
        # Developer 再修 (最多 _MAX_VALIDATION_ATTEMPTS 次总尝试 = 1 + 2 修复);
        # 循环记录尝试次数 (report validation_attempts), 禁无限循环。
        feedback = ""
        output = None
        vresult: ValidationResult | None = None
        attempt = 0
        while True:
            try:
                output = self._developer.work(
                    request=request,
                    project_context=context,
                    sandbox_path=session.workspace_copy_path,
                    extra_instruction=feedback,
                    repo_context=repo_context,
                    context=assembled_context,
                    skills=list(getattr(agent, "skills", None) or []),
                )
            except DeveloperError as exc:
                return self._fail(
                    request, f"provider error: {exc}",
                    duration=time.monotonic() - started,
                    employee=employee,
                    failure_reason=getattr(exc, "failure_reason", ""),
                    assembler=assembler,
                )
            except Exception as exc:  # noqa: BLE001 — 防御兜底: 意外错误 → failed
                return self._fail(
                    request, f"execution error: {exc}",
                    duration=time.monotonic() - started,
                    employee=employee,
                    assembler=assembler,
                )
            try:
                if output.patch_text.strip():
                    sandbox.apply_patch(output.patch_text)
                validation = Validation(Path(session.workspace_copy_path))
                vresult = validation.validate(self._validation_command)
            except Exception as exc:  # noqa: BLE001 — 失败安全
                return self._fail(
                    request, f"sandbox error: {exc}",
                    duration=time.monotonic() - started,
                    employee=employee,
                    assembler=assembler,
                )
            attempt += 1
            if vresult.passed or attempt >= _MAX_VALIDATION_ATTEMPTS:
                break
            feedback = (
                f"你的修改未通过验证 (第 {attempt} 轮, 最多 "
                f"{_MAX_VALIDATION_ATTEMPTS - 1} 轮自动修复)。\n"
                f"验证结果:\n{vresult.output[:1500]}\n"
                "请分析失败原因并修复, 直接输出新的 <operations> 或 <patch>。"
            )

        duration = time.monotonic() - started
        result_id = new_id("EXS")
        artifacts: list[Artifact] = []
        # patch 产物 (git diff 导出; 空 diff 也落文件 — 链统一, apply 为 no-op)
        patch_path = ""
        if self._artifacts_dir is not None:
            patch_path = str(
                Path(self._artifacts_dir) / "patches" / f"{result_id}.patch"
            )
            try:
                sandbox.export_patch(patch_path)
            except Exception as exc:  # noqa: BLE001 — 失败安全
                return self._fail(
                    request, f"sandbox error: {exc}", duration=duration,
                    employee=employee, assembler=assembler, validation=vresult,
                )
        artifacts.append(
            Artifact(
                id=new_id("ART"),
                type=ArtifactType.PATCH,
                task_id=request.task_id,
                employee_id=employee_id,
                agent_id=agent.id if hasattr(agent, "id") else "",
                event_refs=event_refs,
                path=patch_path,
            )
        )
        # test_result 产物 (验证输出)
        test_path = self._write_artifact_file(
            f"{result_id}.test.txt", vresult.output
        )
        artifacts.append(
            Artifact(
                id=new_id("ART"),
                type=ArtifactType.TEST_RESULT,
                task_id=request.task_id,
                employee_id=employee_id,
                agent_id=agent.id if hasattr(agent, "id") else "",
                event_refs=event_refs,
                path=test_path,
            )
        )
        # report 产物 (执行报告, 审批 Review 输入; 含验证结果 + 循环尝试次数)
        assert output is not None and vresult is not None  # 循环保证 (失败路径已 return)
        report_text = self._developer.build_report(
            request=request,
            raw_content=output.raw_content,
            patch_text=output.patch_text,
            validation=vresult,
            duration=duration,
            usage=output.usage,
            operations=output.operations,
            validation_attempts=attempt,
        )
        report_path = self._write_artifact_file(
            f"{result_id}.report.md", report_text
        )
        artifacts.append(
            Artifact(
                id=new_id("ART"),
                type=ArtifactType.REPORT,
                task_id=request.task_id,
                employee_id=employee_id,
                agent_id=agent.id if hasattr(agent, "id") else "",
                event_refs=event_refs,
                path=report_path,
            )
        )

        result = ExecutionResult(
            id=result_id,
            request_id=request.id,
            status=ExecutionStatus.SUCCESS,
            artifacts=artifacts,
            usage=dict(output.usage),
            report=report_text,
            duration=duration,
            context_score=context_score,
        )
        if self._store is not None:
            self._store.save_result(result)
            for artifact in artifacts:
                self._store.save_artifact(artifact)
        exec_events.record_execution_completed(self._logger, result=result)
        if self._experience is not None:
            try:
                self._experience.record(result=result, employee_id=employee_id, request=request)
            except Exception:  # noqa: BLE001 — 经验失败安全 (8B-3 语义)
                pass
        # T4.4: 成功路径自动提取 ContextExperienceRecord (全链路 Trace:
        # assembler.last_ranking_result → ranking/progressive/budget; 失败安全)
        self._extract_experience(
            result,
            request,
            assembler=assembler,
            validation=vresult,
            employee_id=employee_id,
        )
        return result

    def _event_refs(self, session: SandboxSession) -> list[str]:
        """已发生执行事件的 seq 锚点 (artifact.event_refs; logger=None → 空)。"""
        if self._logger is None:
            return []
        try:
            return [
                str(e.seq)
                for e in self._logger.store.query()
                if e.type.value.startswith("org.execution.")
            ][-8:]
        except Exception:  # noqa: BLE001 — 审计锚点失败安全
            return []


def _default_conventions() -> str:
    """默认工程规范 (延迟引用避免 import 环 — DeveloperAgent 模块级常量)。"""
    from .developer import DEFAULT_CONVENTIONS

    return DEFAULT_CONVENTIONS

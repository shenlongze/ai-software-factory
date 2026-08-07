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

import time
from pathlib import Path
from typing import Any

from . import events as exec_events
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
from .validation import Validation

#: 项目上下文文件清单上限 (prompt 体积控制; 真实场景 Agent 可自行读文件)
_PROJECT_CONTEXT_FILE_LIMIT = 60


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
        git_bin: str = "git",
        conventions: str | None = None,
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
        self._git_bin = git_bin
        self._developer = DeveloperAgent(
            provider, conventions=conventions or _default_conventions()
        )

    @property
    def developer(self) -> DeveloperAgent:
        return self._developer

    @property
    def store(self) -> ExecStore | None:
        return self._store

    # ------------------------------------------------------------------ 内部

    def _fail(
        self, request: ExecutionRequest, error: str, *, duration: float = 0.0
    ) -> ExecutionResult:
        """构造 failed 结果 + 发 org.execution.failed (终态单一)。"""
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
            return self._fail(request, "request.input missing project_dir")
        project_path = Path(str(project_dir))
        if not project_path.is_dir():
            return self._fail(
                request, f"project dir not found: {project_path}"
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
            return self._fail(request, f"sandbox error: {exc}")

        exec_events.record_execution_started(
            self._logger, request=request, employee=employee, agent=agent,
            sandbox_path=session.workspace_copy_path,
        )
        # 事件链锚点 (artifact.event_refs: 已发生的 requested/started seq)
        event_refs = self._event_refs(session)

        try:
            context = _project_context(Path(session.workspace_copy_path))
            output = self._developer.work(
                request=request,
                project_context=context,
                sandbox_path=session.workspace_copy_path,
            )
        except DeveloperError as exc:
            return self._fail(
                request, f"provider error: {exc}", duration=time.monotonic() - started
            )
        except Exception as exc:  # noqa: BLE001 — 防御兜底: 意外错误 → failed
            return self._fail(
                request, f"execution error: {exc}", duration=time.monotonic() - started
            )

        try:
            if output.patch_text.strip():
                sandbox.apply_patch(output.patch_text)
            validation = Validation(Path(session.workspace_copy_path))
            vresult = validation.validate(self._validation_command)
        except Exception as exc:  # noqa: BLE001 — 失败安全
            return self._fail(
                request, f"sandbox error: {exc}", duration=time.monotonic() - started
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
                    request, f"sandbox error: {exc}", duration=duration
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
        # report 产物 (执行报告, 审批 Review 输入)
        report_path = self._write_artifact_file(
            f"{result_id}.report.md", output.report
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
            report=output.report,
            duration=duration,
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

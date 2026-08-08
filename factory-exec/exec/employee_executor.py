"""factory-exec/exec/employee_executor.py — Employee-Execution 连接 (Sprint 6)。

目标模型 (任务要求):
```
Employee → Capability → Agent Runtime → Workflow → Execution → Evidence
  (接收任务)  (调用能力)    (执行引擎)      (阶段)    (结果)     (事件+经验)
```

实现 (KISS, 统一 Employee 抽象, 不复制 Agent):
- EmployeeExecutor 是**连接层** (装配点): 接收任务 (task_id/objective/
  project_dir) → 从 Employee 解析 capabilities (员工能力 ∪ 绑定角色能力,
  roles.merge_capabilities) → 构造 ExecutionRequest → 调 AgentRuntime
  (真实执行引擎, 零复制) → 返回 ExecutionResult (result/artifacts) → 落
  经验 (ContextExperienceStore + 10A-4 ExperienceRecorder, 失败安全)。

约束 (与既有 exec 架构一致):
- Employee duck-typed (含 id/name/capabilities/role_ids 即可) — 零硬依赖
  factory-org (org Employee 模型保持, 本模块为「新模块连接」路径)。
- 不复制 Agent: 执行权仍在 AgentRuntime; 本层只做 任务→能力→运行时→经验
  的编排 (装配), 不实现任何 Provider/沙箱/补丁逻辑。
- 角色选择: execute(role_id=...) → 按角色选 prompt 模板 (requirement 前缀
  + role.prompt_template) 与能力 (merge_capabilities)。
- 失败安全: 经验记录异常静默 (同 8B-3 语义, 不破坏执行链); store 缺失时
  纯内存执行。
- 诚实: 角色 execution_kind=planning 时 (非 developer) 可执行但明确标注
  规划产物 (demo_ui_feature 演示走此路径); execute 仍走真实运行时。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent_runtime import AgentRuntime
from .experience import ExperienceRecorder
from .models import ExecutionRequest, ExecutionResult, new_id
from .provider import ProviderInterface
from .roles import (
    RoleError,
    get_role,
    list_roles,
    merge_capabilities,
    require_role,
)

#: 默认角色 (Developer — 唯一 executable 角色; 与 org 模板 Developer 对齐)
DEFAULT_ROLE_ID = "developer"


class EmployeeExecutorError(Exception):
    """EmployeeExecutor 业务错误 (任务/能力解析失败等)。"""


class EmployeeExecutor:
    """Employee → Capability → AgentRuntime → Execution → Evidence 连接层。

    构造:
    - provider: ProviderInterface (真实 LLM; 由装配方注入, 本层不建 Provider)。
    - store: ExecStore (None = 纯内存, 不落库 — 单元测试)。
    - logger: EventLogger (None = 事件静默)。
    - experience_analyzer: 10A-4 ExperienceAnalyzer (None = 10A-4 经验跳过)。
    - experience_store: ContextExperienceStore 或根目录路径 (None = 上下文经验
      不落库 — 提取器仍工作, 只是不持久化; 测试/轻量场景)。
    - validation_command / work_root / git_bin: 透传 AgentRuntime。
    - conventions: Developer 工程规范 (None = 默认)。

    方法:
    - execute(employee, *, task_id, objective, project_dir, ...) → ExecutionResult
      单次任务执行 (接收任务 → 调用能力 → 执行 → 返回结果 → 存经验)。
    - execute_for_workflow(employee, workflow_stage, ...) → ExecutionResult
      workflow 阶段执行 (stage → role 映射, 按角色执行; demo 演示用)。
    """

    def __init__(
        self,
        provider: ProviderInterface,
        *,
        store: Any = None,
        logger: Any = None,
        experience_analyzer: Any = None,
        experience_store: Any = None,
        validation_command: str | None = None,
        work_root: str | Path | None = None,
        git_bin: str = "git",
        conventions: str | None = None,
    ) -> None:
        self._provider = provider
        self._store = store
        self._logger = logger
        self._validation_command = validation_command
        self._work_root = work_root
        self._git_bin = git_bin
        self._conventions = conventions
        # 经验装配 (失败安全): 10A-4 记录器 + 上下文经验提取器 (T4.4 复用)
        self._experience_recorder = ExperienceRecorder(experience_analyzer)
        self._experience_extractor = self._build_extractor(experience_store)

    @staticmethod
    def _build_extractor(experience_store: Any) -> Any:
        """上下文经验提取器 (ContextExperienceStore → ExperienceExtractor)。

        store 缺失 → None (AgentRuntime 不提取上下文经验 — 与既有语义一致);
        store 为路径 (str/Path) → 自动包装 ContextExperienceStore (装配方
        传根目录即可, KISS); 导入失败 → None (失败安全, 删除 experience_ctx
        不影响连接层)。
        """
        if experience_store is None:
            return None
        try:
            from .experience_ctx import ContextExperienceStore, ExperienceExtractor

            store = (
                experience_store
                if isinstance(experience_store, ContextExperienceStore)
                else ContextExperienceStore(experience_store)
            )
            return ExperienceExtractor(store)
        except Exception:  # noqa: BLE001 — 经验装配失败安全
            return None

    # ------------------------------------------------------------------ 属性

    @property
    def provider(self) -> ProviderInterface:
        return self._provider

    @property
    def runtime(self) -> AgentRuntime:
        """即时构造 AgentRuntime (每次执行独立运行时实例, 零共享状态)。

        单例缓存违反 KISS (store/logger 生命周期归装配方); 每执行构造一次
        与 exec CLI 行为一致 (cmd_exec_run 每次构造 runtime)。Developer
        Agent 零存储零事件, 构造代价可忽略。
        """
        return AgentRuntime(
            self._provider,
            store=self._store,
            logger=self._logger,
            validation_command=self._validation_command,
            work_root=self._work_root,
            git_bin=self._git_bin,
            experience=self._experience_recorder,
            experience_extractor=self._experience_extractor,
            conventions=self._conventions,
        )

    # ------------------------------------------------------------------ 执行

    def _resolve_capabilities(
        self, employee: Any, role_id: str | None
    ) -> list[str]:
        """员工能力 ∪ 角色能力 (去重保序; 未指定角色 → 仅员工能力)。

        role_id 未注册 → RoleError 响亮 (拼写错误立即暴露, 不静默降级)。
        """
        employee_caps = list(getattr(employee, "capabilities", None) or [])
        if role_id is None:
            return merge_capabilities(employee_caps)
        role = require_role(role_id)
        return merge_capabilities(employee_caps, role.capabilities)

    def _build_request(
        self,
        *,
        employee: Any,
        task_id: str,
        objective: str,
        project_dir: str | Path,
        requirement: str = "",
        role_id: str | None = None,
        output_refs: list[str] | None = None,
    ) -> ExecutionRequest:
        """构造 ExecutionRequest (任务声明; 执行权在 AgentRuntime)。

        role_id → 角色 prompt 模板前缀 (requirement 首段: 「角色职责」),
        能力合并进 input.capabilities — 执行时按角色选择 prompt/能力。
        """
        caps = self._resolve_capabilities(employee, role_id)
        requirement_text = requirement or ""
        if role_id is not None:
            role = get_role(role_id)
            if role is not None and role.prompt_template:
                requirement_text = (
                    f"{role.prompt_template}\n\n{requirement_text}".strip()
                )
        return ExecutionRequest(
            id=new_id("EXR"),
            task_id=task_id,
            objective=objective,
            requirement=requirement_text,
            output_refs=output_refs or [],
            input={
                "project_dir": str(project_dir),
                "employee_id": getattr(employee, "id", "") or "",
                "capabilities": caps,
                "role_id": role_id or "",
            },
        )

    def execute(
        self,
        employee: Any,
        *,
        task_id: str,
        objective: str,
        project_dir: str | Path,
        requirement: str = "",
        role_id: str | None = None,
        output_refs: list[str] | None = None,
    ) -> ExecutionResult:
        """接收任务 → 调用能力 → 执行 → 返回结果 (经验在 Runtime 内落库)。

        role_id 缺省: 员工已绑定 Developer 角色 → 用 developer; 否则 None
        (纯员工能力, 无角色 prompt — 保持最小语义, 不臆造角色)。
        """
        if role_id is None:
            bound = list(getattr(employee, "role_ids", None) or [])
            role_id = DEFAULT_ROLE_ID if bound else None
        request = self._build_request(
            employee=employee,
            task_id=task_id,
            objective=objective,
            project_dir=project_dir,
            requirement=requirement,
            role_id=role_id,
            output_refs=output_refs,
        )
        # 执行 (AgentRuntime 真实引擎: 沙箱 + Developer + 验证循环 + 经验)
        return self.runtime.execute(request, employee=employee)

    def execute_for_workflow(
        self,
        employee: Any,
        *,
        stage_id: str,
        task_id: str,
        objective: str,
        project_dir: str | Path,
        requirement: str = "",
        output_refs: list[str] | None = None,
    ) -> ExecutionResult:
        """按 workflow 阶段执行 (阶段 → 角色映射, 验收演示用)。

        stage_id → 角色 (roles 注册表 workflow_stages 反向查); 阶段未映射
        到任何角色 → EmployeeExecutorError (声明缺失响亮暴露)。
        """
        role_id = self._role_for_stage(stage_id)
        return self.execute(
            employee,
            task_id=task_id,
            objective=objective,
            project_dir=project_dir,
            requirement=requirement,
            role_id=role_id,
            output_refs=output_refs,
        )

    @staticmethod
    def _role_for_stage(stage_id: str) -> str:
        """workflow 阶段 → 角色 id (注册表反向查; 未映射 → 响亮错误)。"""
        for role in list_roles():
            if stage_id in role.workflow_stages:
                return role.role_id
        raise EmployeeExecutorError(f"no role mapped for workflow stage: {stage_id!r}")

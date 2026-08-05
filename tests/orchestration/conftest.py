"""tests/orchestration/conftest.py — Execution Orchestration 测试 fixtures。

sys.path 兜底同既有模式 (workflows/runtime/assignment); 复用 cli_helpers 与
runtime_helpers (make_request 等)。
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_FACTORY_CORE = _ROOT / "factory-core"
if str(_FACTORY_CORE) not in sys.path:
    sys.path.insert(0, str(_FACTORY_CORE))
_CLI_TESTS = _ROOT / "tests" / "cli"
if str(_CLI_TESTS) not in sys.path:  # 复用 cli_helpers (run_cli/open_events/event_types)
    sys.path.insert(0, str(_CLI_TESTS))
_RUNTIME_TESTS = _ROOT / "tests" / "runtime"
if str(_RUNTIME_TESTS) not in sys.path:  # 复用 runtime_helpers (make_request)
    sys.path.insert(0, str(_RUNTIME_TESTS))

import pytest

from agents.models import Agent
from agents.registry import AgentRegistry
from agents.store import AgentStore
from assignment.allocator import AgentAllocator
from assignment.matcher import AgentMatcher
from assignment.store import AssignmentStore
from events.logger import EventLogger
from events.store import EventStore
from execution.service import ExecutionService
from orchestration.engine import OrchestrationEngine
from runtime.adapters import BUILTIN_ADAPTERS
from runtime.adapter import RuntimeAdapter
from runtime.models import ExecutionResult, ExecutionRequest, ExecutionStatus, RuntimeInfo
from runtime.registry import RuntimeRegistry
from runtime.store import RuntimeStore
from tasks.models import Task
from tasks.store import TaskStore
from workflows.engine import WorkflowEngine
from workflows.models import Workflow, WorkflowStep
from workflows.store import WorkflowStore


# ------------------------------------------------------------------ 目录/存储 fixtures

@pytest.fixture
def workflows_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "workflows"


@pytest.fixture
def tasks_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "tasks"


@pytest.fixture
def agents_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "agents"


@pytest.fixture
def assignments_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "assignments"


@pytest.fixture
def runtimes_dir(tmp_path: Path) -> Path:
    return tmp_path / "factory" / "runtimes"


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "events.db"


@pytest.fixture
def logger(db_path: Path) -> EventLogger:
    """带事件库的 EventLogger (事件集成断言); 退出时关闭连接。"""
    s = EventStore(db_path)
    yield EventLogger(s)
    s.close()


@pytest.fixture
def workflow_store(workflows_dir: Path) -> WorkflowStore:
    return WorkflowStore(workflows_dir)


@pytest.fixture
def task_store(tasks_dir: Path) -> TaskStore:
    return TaskStore(tasks_dir)


@pytest.fixture
def agent_store(agents_dir: Path) -> AgentStore:
    return AgentStore(agents_dir)


@pytest.fixture
def assignment_store(assignments_dir: Path) -> AssignmentStore:
    return AssignmentStore(assignments_dir)


@pytest.fixture
def runtime_store(runtimes_dir: Path) -> RuntimeStore:
    return RuntimeStore(runtimes_dir)


@pytest.fixture
def agent_registry(agent_store: AgentStore) -> AgentRegistry:
    return AgentRegistry(agent_store)


# ------------------------------------------------------------------ 数据构造 helpers

def make_step(step_id: str, order: int, *, skill: str | None = None,
              role: str | None = None) -> WorkflowStep:
    """构造步骤 (required_skill/required_role 可缺省 — 匹配时不限制)。"""
    return WorkflowStep(
        id=step_id, name=step_id, order=order,
        required_skill=skill, required_role=role,
    )


def make_workflow(wf_id: str = "wf-auto", *, steps: list[WorkflowStep] | None = None) -> Workflow:
    """构造工作流定义; 缺省单步 dev (backend-developer/development)。"""
    if steps is None:
        steps = [make_step("dev", 1, skill="development", role="backend-developer")]
    return Workflow(id=wf_id, name=wf_id, description="测试定义", steps=steps)


def make_agent(agent_id: str, *, role: str, skills: list[str] | None = None) -> Agent:
    """构造 Agent (默认 AVAILABLE)。"""
    return Agent(id=agent_id, name=agent_id, role=role, skills=skills or [])


def make_task(task_id: str = "T-001", *, workflow: str | None = "wf-auto") -> Task:
    """构造任务 (直接经 Task 模型, 不走 CLI/事件)。"""
    return Task(id=task_id, title=f"任务 {task_id}", project="markpad", type="feature",
                workflow=workflow)


def seed_agent(agent_store: AgentStore, agent: Agent) -> Agent:
    """注册 Agent 入库 (无 logger 的纯存储注册)。"""
    AgentRegistry(agent_store).register(agent)
    return agent


def seed_workflow(workflow_store: WorkflowStore, workflow: Workflow) -> Workflow:
    """工作流定义入库 (无 logger)。"""
    workflow_store.save_workflow(workflow)
    return workflow


def seed_task(task_store: TaskStore, task: Task) -> Task:
    task_store.create(task)
    return task


def seed_runtime(runtime_store: RuntimeStore, runtime_id: str = "echo",
                 *, type_: str = "mock") -> RuntimeInfo:
    """注册 Runtime 身份 (registry 是派发解析的唯一事实源, ADR-0007 决策 3)。"""
    return RuntimeRegistry(runtime_store).register(
        RuntimeInfo(id=runtime_id, name=runtime_id, type=type_)
    )[0]


class FailingAdapter(RuntimeAdapter):
    """固定 FAILED 的测试 Adapter (验证执行 FAILED → Workflow FAILED, 无半完成)。"""

    RUNTIME_ID = "echo"

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(
            id=f"EXR-{request.id}", request_id=request.id,
            status=ExecutionStatus.FAILED, error="boom",
        )


class RecordingAdapter(RuntimeAdapter):
    """记录收到的请求 (断言 dispatcher 已解析 runtime_id / 回填 agent_id)。"""

    RUNTIME_ID = "echo"

    def __init__(self) -> None:
        self.requests: list[ExecutionRequest] = []

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        self.requests.append(request)
        return ExecutionResult(
            id=f"EXR-{request.id}", request_id=request.id,
            status=ExecutionStatus.SUCCESS,
            output={"echo": request.input, "runtime_id": self.RUNTIME_ID},
        )


# ------------------------------------------------------------------ 装配 fixtures

@pytest.fixture
def orchestrator_factory(
    workflow_store: WorkflowStore,
    task_store: TaskStore,
    agent_store: AgentStore,
    assignment_store: AssignmentStore,
    runtime_store: RuntimeStore,
    logger: EventLogger,
):
    """构造 (engine, 各依赖) 的工厂: 支持自定义 adapters / 无 logger。"""
    def _make(
        *, adapters: dict[str, RuntimeAdapter] | None = None,
        use_logger: bool = True,
        workflow: Workflow | None = None,
    ) -> OrchestrationEngine:
        if workflow is not None:
            seed_workflow(workflow_store, workflow)
        wf_logger = logger if use_logger else None
        registry = AgentRegistry(agent_store, logger=wf_logger)
        wf_engine = WorkflowEngine(
            workflow_store, task_store=task_store, logger=wf_logger,
            runtime_store=runtime_store, agent_registry=registry,
        )
        allocator = AgentAllocator(
            assignment_store, registry, logger=wf_logger, runtime_store=runtime_store,
        )
        service = ExecutionService(
            runtime_store, RuntimeRegistry(runtime_store, logger=wf_logger),
            adapters=adapters if adapters is not None else BUILTIN_ADAPTERS,
            logger=wf_logger,
        )
        return OrchestrationEngine(
            workflow_engine=wf_engine, allocator=allocator,
            execution_service=service, logger=wf_logger,
        )
    return _make


@pytest.fixture
def orchestrator(orchestrator_factory) -> OrchestrationEngine:
    """默认装配的 OrchestrationEngine (echo 内置 Adapter, 事件记录)。"""
    return orchestrator_factory()


@pytest.fixture
def cli_root(tmp_path: Path) -> Path:
    """独立工厂根目录 (CLI 测试, 每个测试隔离)。"""
    return tmp_path / "factory"

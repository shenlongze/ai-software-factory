"""tests/exec/test_exec_employee_executor.py — EmployeeExecutor 连接层 (Sprint 6)。

覆盖 (mock Provider, 不调真实 LLM): 阶段→角色映射 (已知/未知阶段) /
员工能力 ∪ 角色能力合并 (去重保序) / 未注册角色 RoleError 响亮 / 请求构造
(角色 prompt 模板前缀 + 能力进 input) / execute 全链 (真实沙箱 + patch +
三产物 + 经验) / 默认角色绑定 (员工绑定 Developer → developer 角色) /
execute_for_workflow 阶段派发 / 10A-4 经验记录 (ExperienceAnalyzer mock) /
上下文经验落库 (ContextExperienceStore + ExperienceExtractor) / Provider
错误 → failed 结果 (失败安全)。

设计 (employee_executor.py): Employee duck-typed (id/name/capabilities/
role_ids); 执行权仍在 AgentRuntime — 本层只做 任务→能力→运行时→经验 编排。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from exec.employee_executor import (
    DEFAULT_ROLE_ID,
    EmployeeExecutor,
    EmployeeExecutorError,
)
from exec.models import ArtifactType, ExecutionStatus
from exec.roles import RoleError
from exec_helpers import FakeProvider, git_diff_text, write_files

CALC_BEFORE = "def add(a, b):\n    return a + b\n\n"
CALC_AFTER = "def add(a, b):\n    return abs(a + b)\n\n"


class _Employee:
    """duck-typed Employee (org Employee 模型兼容: id/name/capabilities/role_ids)。"""

    def __init__(
        self,
        employee_id: str,
        capabilities: list[str] | None = None,
        role_ids: list[str] | None = None,
    ) -> None:
        self.id = employee_id
        self.name = f"Employee {employee_id}"
        self.capabilities = list(capabilities or [])
        self.role_ids = list(role_ids or [])


class _Analyzer:
    """ExperienceAnalyzer mock (记录 record_experience kwargs)。"""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def record_experience(self, **kwargs):
        self.calls.append(kwargs)
        return {"recorded": True}


def _bug_project(tmp_path: Path) -> Path:
    """最小 Python 项目 (与 git_diff_text before 逐字一致, 沙箱 apply 可应用)。"""
    proj = tmp_path / "bug-project"
    write_files(proj, {"calc.py": CALC_BEFORE, "README.md": "# demo\n"})
    return proj


def _patch_provider(tmp_path: Path) -> FakeProvider:
    """返回合法 unified diff 的 FakeProvider (DeveloperAgent 解析 <patch>)。"""
    patch = git_diff_text(tmp_path, {"calc.py": CALC_BEFORE}, {"calc.py": CALC_AFTER})
    return FakeProvider(
        content=f"fixed the sub bug\n<patch>\n{patch}\n</patch>",
        usage={"input_tokens": 12, "output_tokens": 6, "estimated_cost_usd": 0.01},
    )


class TestStageMapping:
    def test_known_stage_to_role(self):
        for stage, role_id in {
            "product": "product-manager",
            "ux_ui": "ui-designer",
            "architecture": "architect",
            "development": "developer",
            "testing": "tester",
            "release": "devops",
        }.items():
            assert EmployeeExecutor._role_for_stage(stage) == role_id

    def test_unknown_stage_raises(self):
        """未映射阶段 → EmployeeExecutorError 响亮 (声明缺失暴露, 不静默)。"""
        with pytest.raises(EmployeeExecutorError, match="no role mapped"):
            EmployeeExecutor._role_for_stage("no-such-stage")


class TestCapabilityResolution:
    def _executor(self, provider: FakeProvider | None = None) -> EmployeeExecutor:
        return EmployeeExecutor(provider or FakeProvider())

    def test_employee_caps_plus_role_caps_dedup(self):
        emp = _Employee("E-1", capabilities=["python", "coding"])
        caps = self._executor()._resolve_capabilities(emp, "developer")
        # 员工能力 ∪ developer 角色能力 (去重保序)
        assert caps == ["python", "coding", "debugging"]

    def test_no_role_only_employee_caps(self):
        emp = _Employee("E-1", capabilities=["python"])
        assert self._executor()._resolve_capabilities(emp, None) == ["python"]

    def test_unknown_role_raises(self):
        with pytest.raises(RoleError, match="unknown role"):
            self._executor()._resolve_capabilities(_Employee("E-1"), "no-such-role")


class TestRequestBuilding:
    def test_role_prompt_prefix_and_capabilities(self):
        emp = _Employee("E-9", capabilities=["python"])
        executor = EmployeeExecutor(FakeProvider())
        request = executor._build_request(
            employee=emp,
            task_id="T-6",
            objective="fix bug",
            project_dir="/tmp/proj",
            requirement="make it work",
            role_id="developer",
        )
        # 角色 prompt 模板前缀 + 原始 requirement
        assert "Developer" in request.requirement
        assert "make it work" in request.requirement
        # 能力合并进 input.capabilities
        assert request.input["capabilities"] == ["python", "coding", "debugging"]
        assert request.input["role_id"] == "developer"
        assert request.input["employee_id"] == "E-9"
        assert request.task_id == "T-6"


class TestExecute:
    def test_execute_full_chain_with_experience(
        self, tmp_path: Path, exec_store, logger
    ):
        """任务 → 角色/能力 → AgentRuntime → 结果 → 经验 (10A-4 + 上下文经验)。"""
        project = _bug_project(tmp_path)
        provider = _patch_provider(tmp_path)
        analyzer = _Analyzer()
        ctx_store_root = tmp_path / "ctx-exp"
        executor = EmployeeExecutor(
            provider,
            store=exec_store,
            logger=logger,
            experience_analyzer=analyzer,
            experience_store=ctx_store_root,
        )
        emp = _Employee("E-6", capabilities=["python"], role_ids=[DEFAULT_ROLE_ID])

        result = executor.execute(
            emp,
            task_id="T-6-1",
            objective="fix the add function bug",
            project_dir=project,
            requirement="return abs(a + b)",
        )

        # 结果: 成功 + 三产物
        assert result.is_success
        assert result.status is ExecutionStatus.SUCCESS
        assert [a.type for a in result.artifacts] == [
            ArtifactType.PATCH,
            ArtifactType.TEST_RESULT,
            ArtifactType.REPORT,
        ]
        # 沙箱零接触原项目
        assert (project / "calc.py").read_text() == CALC_BEFORE

        # 经验 1: 10A-4 记录 (成功正信号, subject_id = employee.id)
        assert len(analyzer.calls) == 1
        call = analyzer.calls[0]
        assert call["subject_id"] == "E-6"
        assert call["result"] == "success"
        assert call["task_type"] == "T-6-1"
        assert "python" in call["capability"]

        # 经验 2: 上下文经验落库 (ContextExperienceStore)
        from exec.experience_ctx import ContextExperienceStore

        ctx_store = ContextExperienceStore(ctx_store_root)
        assert ctx_store.count() == 1
        record = ctx_store.list_all()[0]
        assert record.task_type == "T-6-1"
        # employee_id 在 execution_result 明细 (ContextExperienceRecord 无顶层字段)
        assert record.execution_result["employee_id"] == "E-6"

    def test_execute_default_role_binding(self, tmp_path: Path):
        """员工绑定角色 (role_ids 非空) → 默认 developer 角色 (prompt 前缀)。"""
        project = _bug_project(tmp_path)
        provider = _patch_provider(tmp_path)
        executor = EmployeeExecutor(provider)
        emp = _Employee("E-7", capabilities=["python"], role_ids=["developer"])

        result = executor.execute(
            emp,
            task_id="T-6-2",
            objective="fix add",
            project_dir=project,
        )
        assert result.is_success
        # Developer 角色 prompt 模板前缀进了 requirement (角色选择生效)
        assert "你是一名 Developer" in provider.calls[0].task_context

    def test_execute_no_role_no_prompt(self, tmp_path: Path):
        """员工未绑定角色 → 无角色 prompt (最小语义, 不臆造角色)。"""
        project = _bug_project(tmp_path)
        provider = _patch_provider(tmp_path)
        executor = EmployeeExecutor(provider)
        emp = _Employee("E-8", capabilities=["python"])

        result = executor.execute(
            emp, task_id="T-6-3", objective="fix add", project_dir=project
        )
        assert result.is_success
        # 基础 DeveloperAgent conventions 是英文 (含 "Developer Agent"),
        # 但角色 prompt 模板前缀 (中文「你是一名 Developer」) 不应出现
        assert "你是一名 Developer" not in provider.calls[0].task_context

    def test_execute_provider_error_failed_safe(self, tmp_path: Path):
        """Provider 错误 → failed 结果 (失败安全, 不抛未处理异常)。"""
        project = _bug_project(tmp_path)
        provider = FakeProvider(error="provider error: openai api key missing")
        executor = EmployeeExecutor(provider, experience_analyzer=_Analyzer())
        emp = _Employee("E-10", capabilities=["python"], role_ids=[DEFAULT_ROLE_ID])

        result = executor.execute(
            emp, task_id="T-6-4", objective="fix add", project_dir=project
        )
        assert not result.is_success
        assert result.status is ExecutionStatus.FAILED
        assert "provider error" in result.error

    def test_execute_for_workflow_stage_dispatch(self, tmp_path: Path):
        """execute_for_workflow: 阶段 → 角色 → 执行 (验收演示拆解路径)。"""
        project = _bug_project(tmp_path)
        provider = _patch_provider(tmp_path)
        executor = EmployeeExecutor(provider)
        emp = _Employee("E-11", capabilities=["python"], role_ids=[DEFAULT_ROLE_ID])

        result = executor.execute_for_workflow(
            emp,
            stage_id="development",
            task_id="T-6-5",
            objective="fix add",
            project_dir=project,
        )
        assert result.is_success
        assert "你是一名 Developer" in provider.calls[0].task_context

    def test_execute_for_workflow_unknown_stage(self, tmp_path: Path):
        executor = EmployeeExecutor(FakeProvider())
        with pytest.raises(EmployeeExecutorError, match="no role mapped"):
            executor.execute_for_workflow(
                _Employee("E-12"),
                stage_id="bogus",
                task_id="T-6-6",
                objective="x",
                project_dir=_bug_project(tmp_path),
            )

    def test_execute_experience_failure_safe(self, tmp_path: Path):
        """经验记录异常 → 静默 (失败安全, 不破坏执行链)。"""
        project = _bug_project(tmp_path)
        provider = _patch_provider(tmp_path)

        class _BrokenAnalyzer:
            def record_experience(self, **kwargs):
                raise RuntimeError("intelligence down")

        executor = EmployeeExecutor(
            provider,
            experience_analyzer=_BrokenAnalyzer(),
            experience_store=tmp_path / "ctx",
        )
        result = executor.execute(
            _Employee("E-13", capabilities=["python"]),
            task_id="T-6-7",
            objective="fix add",
            project_dir=project,
        )
        assert result.is_success

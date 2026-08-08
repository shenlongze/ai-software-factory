"""tests/s7/test_s7_full_chain_demo.py — S7-005 Full Chain Demo 集成验证。

覆盖 (任务清单: Demo 建链 / Artifact 链断言 / Runner 推进 / Tester Loop
失败→修复→成功 ≤2 轮 / 诚实标注):
- Demo 建链: build_demo_workflow 5 阶段 (Product→Architecture→Development→
  Testing→Release) + depends_on 链 + input_artifacts 预定义 (前输出引用)
  + DAG 拓扑序; loop 变体 (Development→Testing→Release)
- Mock executor 契约: prd/design/code/release 全经 validate_artifact;
  dev 真实写文件 + 轮次版本轨迹
- Artifact 链断言: 每 stage 输入 = 前 stage 输出 (id 引用 + VALIDATED)
- Runner 推进: 全链 COMPLETED + 状态转换事件 (stage_ready/started/
  completed) + org.workflow.* 事件闭环 + 幂等重跑
- Tester Loop: buggy code → Tester 失败 → bug_report → repair → 修 →
  retest 通过 → Release 推进 (≤2 轮, 零伪造)
- 诚实标注: PM/Architect/DevOps mock (execution_kind=planning), 零 LLM
  调用 (通过不调 provider), 未知角色响亮失败

执行: 真实 pytest 子进程 (确定性, 不靠 LLM 猜); 失败分析 mock provider
(v4-pro 契约 — 不调真实 LLM)。依赖: 本目录 conftest + org.demo (S7-005)。

约束: 只组合 (WorkflowLifecycle/WorkflowRunner/DevTestLoopRunner/
TesterAgent/build_tester_executor/make_workflow_executor), 零重写; 不实现
PM/Architect/Release Agent 自动化 (Sprint 8)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from exec.provider import ProviderResponse
from exec.roles import require_role
from exec.tester import (
    TesterAgent,
    TesterError,
    build_tester_executor,
    make_workflow_executor,
)
from org import demo
from org.artifact import validate_artifact
from org.projects import ArtifactStatus, ProjectLifecycle, StageStatus
from org.workflow import (
    DEFAULT_MAX_REPAIR_ROUNDS,
    DevTestLoopRunner,
    WorkflowLifecycle,
    WorkflowRunner,
    WorkflowStatus,
)

from s7_helpers import event_sequence

PYTEST_CMD = f"{sys.executable} -m pytest -q"

TEST_CALC = (
    "from calc import add, sub, mul\n"
    "\n"
    "def test_add():\n"
    "    assert add(1, 2) == 3\n"
    "\n"
    "def test_sub():\n"
    "    assert sub(5, 3) == 2\n"
    "\n"
    "def test_mul():\n"
    "    assert mul(2, 3) == 6\n"
)

#: 两版代码: 1 缺陷 → 全通过 (确定性修复轨迹, Tester Loop ≤2 轮)
CALC_BUGGY = (
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "def sub(a, b):\n"
    "    return a + b\n"      # bug: 应为 a - b
    "\n"
    "def mul(a, b):\n"
    "    return a * b\n"
)
CALC_FIXED = (
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "def sub(a, b):\n"
    "    return a - b\n"      # 已修复
    "\n"
    "def mul(a, b):\n"
    "    return a * b\n"
)

V0_BUGGY = {"calc.py": CALC_BUGGY, "test_calc.py": TEST_CALC}
V1_FIXED = {"calc.py": CALC_FIXED, "test_calc.py": TEST_CALC}


def _bug(location: str, severity: str = "high") -> dict:
    return {
        "location": location,
        "repro": "运行 pytest",
        "expected": "expected",
        "actual": "actual",
        "root_cause": "root cause",
        "severity": severity,
    }


def bug_json(*locations: str) -> str:
    return json.dumps([_bug(loc) for loc in locations])


class SeqProvider:
    """按调用顺序返回固定 JSON 的 mock provider (v4-pro 契约; 耗尽后重复末条)。"""

    provider_id = "mock"

    def __init__(self, contents: list[str]) -> None:
        self._contents = list(contents)
        self._last = ""
        self.calls: list = []

    def generate(self, request) -> ProviderResponse:
        self.calls.append(request)
        if self._contents:
            self._last = self._contents.pop(0)
        if not self._last:
            return ProviderResponse(content="[]", usage={})
        return ProviderResponse(content=self._last, usage={})


@pytest.fixture
def wlife(project_store, logger) -> WorkflowLifecycle:
    return WorkflowLifecycle(project_store, logger=logger)


@pytest.fixture
def project_id(wlife) -> str:
    ProjectLifecycle(wlife.store).create_project("Demo App", project_id="P-1")
    return "P-1"


@pytest.fixture
def demo_proj(tmp_path: Path) -> Path:
    return tmp_path / "demo_proj"


def make_tester(provider) -> TesterAgent:
    return TesterAgent(provider, test_command=PYTEST_CMD)


def make_chain_executors(
    project_dir: Path,
    versions: list[dict],
    provider,
    *,
    capture: dict | None = None,
) -> dict:
    """Demo 全链 executors (mock PM/Arch/Dev/DevOps + 真实 TesterAgent 组合)。

    capture: {role_id: [[(input_id, input_status), ...], ...]} — 每 stage 执行
    时记录 context["inputs"] (Artifact 链断言)。
    """

    def capture_wrap(role_id: str, fn):
        def run(stage, context):
            if capture is not None:
                capture.setdefault(stage.role_id, []).append(
                    [(i.get("id"), i.get("status")) for i in context.get("inputs", [])]
                )
            return fn(stage, context)

        return run

    return {
        "product-manager": demo.pm_executor(),
        "architect": capture_wrap("architect", demo.arch_executor()),
        "developer": capture_wrap(
            "developer", demo.dev_executor(project_dir, versions)
        ),
        "tester": capture_wrap(
            "tester", demo.make_tester_executor(build_tester_executor(make_tester(provider)))
        ),
        "devops": capture_wrap("devops", demo.devops_executor()),
    }


# ================================================================== Demo 建链


class TestDemoWorkflowDefinition:
    """Demo workflow 构造 (5 阶段链 / loop 变体 / DAG / 角色注册)。"""

    def test_build_demo_workflow_five_stages(self, wlife, project_id):
        wf = demo.build_demo_workflow(wlife, project_id, workflow_id="WF-1")
        stages = wlife.list_stages("WF-1")
        assert wf.status is WorkflowStatus.DRAFT
        assert [s.name for s in stages] == [
            "Product", "Architecture", "Development", "Testing", "Release",
        ]
        assert [s.role_id for s in stages] == [
            "product-manager", "architect", "developer", "tester", "devops",
        ]

    def test_depends_on_chain_linear(self, wlife, project_id):
        demo.build_demo_workflow(wlife, project_id, workflow_id="WF-1")
        stages = wlife.list_stages("WF-1")
        for i, stage in enumerate(stages):
            if i == 0:
                assert stage.depends_on == []
            else:
                assert stage.depends_on == [stages[i - 1].id]

    def test_input_artifacts_prewired_to_prev_output(self, wlife, project_id):
        """Artifact 链预定义: 每 stage 输入 = 前 stage 输出 id (前输出→后输入)。"""
        demo.build_demo_workflow(wlife, project_id, workflow_id="WF-1")
        stages = wlife.list_stages("WF-1")
        expected = [None, "A-DEMO-PRD", "A-DEMO-DESIGN", "A-DEMO-CODE", "A-DEMO-TEST"]
        for stage, exp in zip(stages, expected):
            assert stage.input_artifacts == ([exp] if exp else [])

    def test_demo_artifact_ids_unique(self):
        ids = list(demo.DEMO_ARTIFACT_IDS.values())
        assert len(ids) == len(set(ids)) == 5
        assert all(i.startswith("A-DEMO-") for i in ids)
        assert all(i for i in ids)

    def test_dag_topological_order(self, wlife, project_id):
        wf = demo.build_demo_workflow(wlife, project_id, workflow_id="WF-1")
        stages = wlife.list_stages("WF-1")
        assert wlife.validate_dag(wf.id) == [s.id for s in stages]

    def test_build_demo_loop_workflow_three_stages(self, wlife, project_id):
        wf = demo.build_demo_loop_workflow(wlife, project_id, workflow_id="WF-L")
        stages = wlife.list_stages("WF-L")
        assert wf.status is WorkflowStatus.DRAFT
        assert [s.role_id for s in stages] == ["developer", "tester", "devops"]
        assert [s.name for s in stages] == ["Development", "Testing", "Release"]

    def test_loop_workflow_release_input_wired(self, wlife, project_id):
        demo.build_demo_loop_workflow(wlife, project_id, workflow_id="WF-L")
        stages = wlife.list_stages("WF-L")
        release = stages[-1]
        assert release.input_artifacts == ["A-DEMO-TEST"]
        assert release.depends_on == [stages[1].id]
        assert stages[1].depends_on == [stages[0].id]

    def test_demo_stage_roles_registered(self):
        """全部 Demo stage role_id 经 exec 注册表 (创建成功即证明; 显式复验)。"""
        for spec in demo.DEMO_STAGES:
            assert require_role(spec["role_id"]).role_id == spec["role_id"]


# ================================================================== Mock executors


class TestMockExecutors:
    """Mock executor 契约 (非 LLM 占位语义; 产物全经 validate_artifact)。"""

    def test_pm_executor_prd_contract(self):
        result = demo.pm_executor()(None, {})
        assert result["artifact_type"] == "prd"
        assert result["artifact_id"] == "A-DEMO-PRD"
        validation = validate_artifact("prd", result["metadata"])
        assert validation.ok, f"missing={validation.missing} errors={validation.errors}"

    def test_arch_executor_design_contract(self):
        result = demo.arch_executor()(None, {})
        assert result["artifact_type"] == "design"
        assert result["artifact_id"] == "A-DEMO-DESIGN"
        validation = validate_artifact("design", result["metadata"])
        assert validation.ok, f"missing={validation.missing} errors={validation.errors}"

    def test_dev_executor_writes_files_and_code_contract(
        self, demo_proj: Path
    ):
        class _DevStage:
            name = "Development"

        dev = demo.dev_executor(demo_proj, [V1_FIXED])
        result = dev(_DevStage(), {})
        assert (demo_proj / "calc.py").exists()
        assert (demo_proj / "test_calc.py").exists()
        assert result["artifact_type"] == "code"
        assert result["artifact_id"] == "A-DEMO-CODE"  # 初始 Development 固定 id
        assert result["metadata"]["project_dir"] == str(demo_proj.resolve())
        validation = validate_artifact("code", result["metadata"])
        assert validation.ok, f"missing={validation.missing} errors={validation.errors}"

    def test_dev_executor_round_tracking(self, demo_proj: Path):
        """版本轨迹: 第 0 轮 buggy → 第 1 轮 fixed (Tester Loop 修复轮依据)。"""
        class _DevStage:
            name = "Development"

        dev = demo.dev_executor(demo_proj, [V0_BUGGY, V1_FIXED])
        dev(_DevStage(), {})
        assert "return a + b" in (demo_proj / "calc.py").read_text()  # sub bug
        dev(None, {})  # 修复轮
        assert "return a - b" in (demo_proj / "calc.py").read_text()  # sub 已修复

    def test_devops_executor_release_contract(self):
        result = demo.devops_executor()(None, {})
        assert result["artifact_type"] == "release"
        assert result["artifact_id"] == "A-DEMO-RELEASE"
        validation = validate_artifact("release", result["metadata"])
        assert validation.ok, f"missing={validation.missing} errors={validation.errors}"

    def test_make_tester_executor_pins_initial_test_id(self):
        """组合适配: 初始 Testing 阶段 test 产物固定 id; retest 轮自动 id。"""

        def fake_tester(stage, context):
            return {
                "artifacts": [
                    {"type": "test", "ref": "file:///test_result.json",
                     "metadata": {"results": {"passed": True}, "bugs": []}},
                ]
            }

        class _Stage:
            name = "Testing"

        class _Retest:
            name = "retest 1"

        wrapped = demo.make_tester_executor(fake_tester)
        first = wrapped(_Stage(), {})
        assert first["artifacts"][0]["id"] == "A-DEMO-TEST"
        retest = wrapped(_Retest(), {})
        assert "id" not in retest["artifacts"][0]  # 自动 id, 防重复注册


# ================================================================== Runner 推进 (happy path)


class TestFullChainRunner:
    """全链自动推进: 5 阶段 → COMPLETED + Artifact 链 + 状态/事件审计。"""

    def _run(self, wlife, project_id, project_dir, *, provider, capture=None):
        demo.build_demo_workflow(wlife, project_id, workflow_id="WF-1")
        executors = make_chain_executors(
            project_dir, [V1_FIXED], provider, capture=capture
        )
        runner = WorkflowRunner(wlife, executor=make_workflow_executor(executors))
        return runner.run("WF-1")

    def test_full_chain_completes(
        self, wlife, project_id, demo_proj: Path
    ):
        wf = self._run(wlife, project_id, demo_proj, provider=SeqProvider([]))
        assert wf.status is WorkflowStatus.COMPLETED
        assert wf.completed_at is not None
        assert all(s.status is StageStatus.COMPLETED for s in wlife.list_stages("WF-1"))
        artifacts = wlife.registry.list()
        assert sorted(a.type.value for a in artifacts) == [
            "code", "design", "prd", "release", "test",
        ]
        assert all(a.status is ArtifactStatus.VALIDATED for a in artifacts)

    def test_artifact_chain_input_equals_prev_output(
        self, wlife, project_id, demo_proj: Path
    ):
        """Artifact 链断言: 每 stage 输入 = 前 stage 输出 (id 引用 + VALIDATED)。"""
        capture: dict = {}
        self._run(
            wlife, project_id, demo_proj,
            provider=SeqProvider([]), capture=capture,
        )
        assert capture["architect"] == [[("A-DEMO-PRD", "validated")]]
        assert capture["developer"] == [[("A-DEMO-DESIGN", "validated")]]
        assert capture["tester"] == [[("A-DEMO-CODE", "validated")]]
        assert capture["devops"] == [[("A-DEMO-TEST", "validated")]]

    def test_stage_transition_events(self, wlife, project_id, demo_proj: Path, event_store):
        self._run(wlife, project_id, demo_proj, provider=SeqProvider([]))
        seq = event_sequence(event_store)
        assert seq.count("org.workflow.stage_ready") == 5
        assert seq.count("org.workflow.stage_started") == 5
        assert seq.count("org.workflow.stage_completed") == 5

    def test_workflow_event_sequence(self, wlife, project_id, demo_proj: Path, event_store):
        self._run(wlife, project_id, demo_proj, provider=SeqProvider([]))
        seq = event_sequence(event_store)
        assert "org.workflow.started" in seq
        assert "org.workflow.completed" in seq
        assert "org.workflow.failed" not in seq
        assert seq.count("org.artifact.validated") == 5

    def test_chain_artifacts_producer_and_project(
        self, wlife, project_id, demo_proj: Path
    ):
        self._run(wlife, project_id, demo_proj, provider=SeqProvider([]))
        expected_producer = {
            "prd": "product-manager",
            "design": "architect",
            "code": "developer",
            "test": "tester",
            "release": "devops",
        }
        for type_, aid in demo.DEMO_ARTIFACT_IDS.items():
            artifact = wlife.registry.get(aid)
            assert artifact.status is ArtifactStatus.VALIDATED
            assert artifact.project_id == "P-1"
            assert artifact.producer_role == expected_producer[type_]

    def test_tester_runs_real_pytest(self, wlife, project_id, demo_proj: Path):
        """Testing 阶段真实确定性测试执行 (不靠 LLM 猜): 3 用例全通过。"""
        self._run(wlife, project_id, demo_proj, provider=SeqProvider([]))
        test_artifact = wlife.registry.get("A-DEMO-TEST")
        assert test_artifact.metadata["results"]["passed"] is True
        assert test_artifact.metadata["results"]["total"] == 3
        assert test_artifact.metadata["bugs"] == []

    def test_rerun_idempotent(self, wlife, project_id, demo_proj: Path):
        """COMPLETED 重跑幂等 (不重复执行, 产物数不变)。"""
        demo.build_demo_workflow(wlife, project_id, workflow_id="WF-1")
        executors = make_chain_executors(demo_proj, [V1_FIXED], SeqProvider([]))
        runner = WorkflowRunner(wlife, executor=make_workflow_executor(executors))
        assert runner.run("WF-1").status is WorkflowStatus.COMPLETED
        assert runner.run("WF-1").status is WorkflowStatus.COMPLETED
        assert len(wlife.registry.list()) == 5


# ================================================================== Tester Loop (失败→修复→成功)


class TestTesterLoopDemo:
    """Tester Loop: buggy code → 失败 → bug_report → repair → 修 → retest 通过
    → Release 推进 (≤2 轮, 零伪造)。"""

    def _run(self, wlife, project_id, project_dir, *, provider):
        demo.build_demo_loop_workflow(wlife, project_id, workflow_id="WF-L")
        executors = {
            "developer": demo.dev_executor(project_dir, [V0_BUGGY, V1_FIXED]),
            "tester": demo.make_tester_executor(
                build_tester_executor(make_tester(provider))
            ),
            "devops": demo.devops_executor(),
        }
        loop = DevTestLoopRunner(
            wlife, executor=make_workflow_executor(executors)
        )
        return loop.run("WF-L")

    def test_loop_failure_repair_retest_success(
        self, wlife, project_id, demo_proj: Path
    ):
        """核心: dev(bug) → test(失败) → bug_report → repair → dev(修) →
        retest(通过) → Release → COMPLETED; 恰好 1 次 LLM 分析 (仅失败轮)。"""
        provider = SeqProvider([bug_json("calc.py:6 (sub)")])
        wf = self._run(wlife, project_id, demo_proj, provider=provider)
        assert wf.status is WorkflowStatus.COMPLETED
        by_name = {s.name: s for s in wlife.list_stages("WF-L")}
        # list_stages 按 (order, id) 排序 — 动态 repair/retest order 追加在
        # 初始 Release 之后; 按 name 断言结构 (执行序由 depends_on 决定)
        assert set(by_name) == {
            "Development", "Testing", "repair 1", "retest 1", "Release",
        }
        assert all(s.status is StageStatus.COMPLETED for s in by_name.values())
        assert len(provider.calls) == 1  # 仅失败轮调 LLM 失败分析

    def test_bug_report_artifact_created(
        self, wlife, project_id, demo_proj: Path
    ):
        provider = SeqProvider([bug_json("calc.py:6 (sub)")])
        self._run(wlife, project_id, demo_proj, provider=provider)
        bug_reports = [
            a for a in wlife.registry.list() if a.type.value == "bug_report"
        ]
        assert len(bug_reports) == 1
        assert bug_reports[0].status is ArtifactStatus.VALIDATED
        meta = bug_reports[0].metadata
        for field in ("location", "repro", "expected", "actual", "root_cause", "severity"):
            assert str(meta.get(field) or "").strip(), f"bug_report 缺字段 {field}"

    def test_repair_round_recorded(self, wlife, project_id, demo_proj: Path):
        """repair 轮次落库可审计: repair 输入接线 bug_report, retest 依赖 repair。"""
        provider = SeqProvider([bug_json("calc.py:6 (sub)")])
        self._run(wlife, project_id, demo_proj, provider=provider)
        stages = wlife.list_stages("WF-L")
        repair = next(s for s in stages if s.name == "repair 1")
        retest = next(s for s in stages if s.name == "retest 1")
        assert repair.role_id == "developer"
        assert repair.input_artifacts, "repair 阶段应接线 bug_report 输入"
        bug = wlife.registry.get(repair.input_artifacts[0])
        assert bug.type.value == "bug_report"
        assert retest.role_id == "tester"
        assert retest.depends_on == [repair.id]

    def test_loop_release_proceeds_after_pass(
        self, wlife, project_id, demo_proj: Path
    ):
        """重测成功 → 下一 stage (Release) 推进: release 产物 VALIDATED。"""
        provider = SeqProvider([bug_json("calc.py:6 (sub)")])
        self._run(wlife, project_id, demo_proj, provider=provider)
        release = wlife.registry.get("A-DEMO-RELEASE")
        assert release.status is ArtifactStatus.VALIDATED
        assert release.metadata["version"] == "1.0.0"

    def test_loop_within_two_repair_rounds(
        self, wlife, project_id, demo_proj: Path
    ):
        """计数保护: 修复轮 ≤2 (DEFAULT_MAX_REPAIR_ROUNDS=2); Demo 实际 1 轮。"""
        assert DEFAULT_MAX_REPAIR_ROUNDS == 2
        provider = SeqProvider([bug_json("calc.py:6 (sub)")])
        self._run(wlife, project_id, demo_proj, provider=provider)
        stages = wlife.list_stages("WF-L")
        repair_count = sum(1 for s in stages if s.name.startswith("repair"))
        assert repair_count == 1
        assert repair_count <= DEFAULT_MAX_REPAIR_ROUNDS

    def test_loop_final_test_passed(self, wlife, project_id, demo_proj: Path):
        """末轮 retest 产物: bugs=[] + passed=True (质量门禁通过)。"""
        provider = SeqProvider([bug_json("calc.py:6 (sub)")])
        self._run(wlife, project_id, demo_proj, provider=provider)
        stages = wlife.list_stages("WF-L")
        last_tester = [s for s in stages if s.role_id == "tester"][-1]
        last_test = [
            a for a in wlife.stage_artifacts(last_tester.id)
            if a.type.value == "test"
        ][-1]
        assert last_test.metadata["bugs"] == []
        assert last_test.metadata["results"]["passed"] is True


# ================================================================== 诚实标注 / 边界


class TestDemoLimits:
    """诚实标注: mock 角色 (planning) / 零 LLM / 未映射角色响亮失败。"""

    def test_planning_roles_are_mocked(self):
        """S8-003 后 architect 已 executable (注册表), S8-004 后 devops 也已
        executable, 但 S7-005 Demo 仍注入 mock 占位 (Demo 零 LLM, 不随注册表
        升级); Developer/Tester/ProductManager executable (能力已由
        S7-004/S8-001/Sprint 6.5 证明 — mock 与角色 execution_kind 分离)。"""
        assert require_role("architect").execution_kind == "executable"
        assert require_role("devops").execution_kind == "executable"
        assert require_role("developer").execution_kind == "executable"
        assert require_role("tester").execution_kind == "executable"
        assert require_role("product-manager").execution_kind == "executable"

    def test_happy_path_zero_llm_calls(
        self, wlife, project_id, demo_proj: Path
    ):
        """通过路径零 LLM 调用 (测试结果确定性; 诚实: 不假装分析)。"""
        provider = SeqProvider([])
        demo.build_demo_workflow(wlife, project_id, workflow_id="WF-1")
        executors = make_chain_executors(demo_proj, [V1_FIXED], provider)
        runner = WorkflowRunner(wlife, executor=make_workflow_executor(executors))
        assert runner.run("WF-1").status is WorkflowStatus.COMPLETED
        assert provider.calls == []

    def test_unknown_role_fails_loudly(self, demo_proj: Path):
        """未映射角色 → 响亮失败 (不假装执行, 编排壳诚实边界)。"""
        executor = make_workflow_executor(
            {"developer": demo.dev_executor(demo_proj, [V1_FIXED])}
        )

        class _Stage:
            role_id = "product-manager"
            id = "STG-X"

        with pytest.raises(TesterError, match="no executor mapped"):
            executor(_Stage(), {})

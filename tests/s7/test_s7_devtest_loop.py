"""tests/s7/test_s7_devtest_loop.py — Dev↔Tester Loop 集成 (Integration, S7-004)。

覆盖 (任务清单: Dev→Test→bug→repair→retest 全链 ≤2 轮 / 3 轮停止 / 通过即
release 前置 / 计数保护):
- build_dev_test_workflow: 初始对 (developer stage → tester stage)
- 通过即完成: 首轮通过 → COMPLETED (零修复轮, 零 LLM 分析调用)
- 通过即 release 前置: 通过后剩余 release 阶段交回 base Runner 推进
- 全链 ≤2 轮: dev→test→bug_report→repair→retest→…→通过 → COMPLETED
  (动态 repair/retest 阶段 + bug_report 输入接线)
- 3 轮停止: 修复轮耗尽仍有缺陷 → workflow FAILED (质量门禁, 计数保护,
  恰好 3 次测试执行, 无第 4 轮)
- 计数保护: max_repair_rounds=0/1 配置语义
- 诚实路径: dev 未产出 code 产物 → test BLOCKED → ACTIVE (不假装完成);
  中断重跑 (失败 stage 重置 + failed→paused→active 恢复)
- 幂等: COMPLETED 重跑 / FAILED 重跑响亮拒绝
- 事件审计: 动态阶段 org.stage.created 全量可审计

执行: 真实 pytest 子进程 (确定性, 不靠 LLM 猜); 失败分析 mock provider
(v4-pro 契约 — 不调真实 LLM)。依赖: 本目录 conftest。

"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from exec.provider import ProviderResponse
from exec.tester import TesterAgent, build_tester_executor, make_workflow_executor
from org.projects import ArtifactStatus, ProjectLifecycle, StageStatus
from org.workflow import (
    DEFAULT_MAX_REPAIR_ROUNDS,
    DevTestLoopRunner,
    WorkflowLifecycle,
    WorkflowStateError,
    WorkflowStatus,
    build_dev_test_workflow,
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

#: 三版代码: 2 缺陷 → 1 缺陷 → 全通过 (确定性修复轨迹)
CALC_BUGGY = (
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "def sub(a, b):\n"
    "    return a + b\n"      # bug 1: 应为 a - b
    "\n"
    "def mul(a, b):\n"
    "    return a + b\n"      # bug 2: 应为 a * b
)
CALC_PARTIAL = (
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "def sub(a, b):\n"
    "    return a - b\n"      # 已修复
    "\n"
    "def mul(a, b):\n"
    "    return a + b\n"      # bug 仍存
)
CALC_FIXED = (
    "def add(a, b):\n"
    "    return a + b\n"
    "\n"
    "def sub(a, b):\n"
    "    return a - b\n"
    "\n"
    "def mul(a, b):\n"
    "    return a * b\n"
)

V0_BUGGY = {"calc.py": CALC_BUGGY, "test_calc.py": TEST_CALC}
V1_PARTIAL = {"calc.py": CALC_PARTIAL, "test_calc.py": TEST_CALC}
V2_FIXED = {"calc.py": CALC_FIXED, "test_calc.py": TEST_CALC}


def write_files(base: Path, files: dict[str, str]) -> None:
    base.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (base / name).write_text(content, encoding="utf-8")
    # 确定性: 清空 __pycache__ — pytest 子进程会复用同尺寸+同秒 mtime 的
    # 陈旧字节码 (重写 calc.py 各版同尺寸), 不 purge 则轮次间读到旧模块
    shutil.rmtree(base / "__pycache__", ignore_errors=True)


def _bug(location: str, severity: str = "high") -> dict:
    return {
        "location": location,
        "repro": "运行 pytest",
        "expected": "e",
        "actual": "a",
        "root_cause": "rc",
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


def make_dev_executor(project_dir: Path, versions: list[dict], *, captured=None):
    """按轮次写代码版本; 返回 code 产物 (metadata 带 project_dir 契约)。"""
    state = {"round": 0}

    def dev_executor(stage, context):
        if captured is not None and stage.name.startswith("repair"):
            captured.append(
                [i.get("metadata") for i in context.get("inputs", [])]
            )
        idx = min(state["round"], len(versions) - 1)
        state["round"] += 1
        files = versions[idx]
        write_files(project_dir, files)
        return {
            "artifact_type": "code",
            "ref": "file:///src",
            "metadata": {
                "files": list(files),
                "changes": "impl",
                "project_dir": str(project_dir),
            },
        }

    return dev_executor


def make_tester(provider) -> TesterAgent:
    return TesterAgent(provider, test_command=PYTEST_CMD)


@pytest.fixture
def wlife(project_store, logger) -> WorkflowLifecycle:
    return WorkflowLifecycle(project_store, logger=logger)


@pytest.fixture
def project_id(wlife) -> str:
    ProjectLifecycle(wlife.store).create_project("Build App", project_id="P-1")
    return "P-1"


@pytest.fixture
def loop_project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    write_files(proj, V0_BUGGY)
    return proj


def make_loop(wlife, executors, **kw) -> DevTestLoopRunner:
    return DevTestLoopRunner(wlife, executor=make_workflow_executor(executors), **kw)


class TestBuildWorkflow:
    def test_default_max_repair_rounds(self):
        assert DEFAULT_MAX_REPAIR_ROUNDS == 2

    def test_build_initial_pair(self, wlife, project_id):
        """初始对: developer stage (develop) → tester stage (test)。"""
        wf = build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")
        stages = wlife.list_stages("WF-1")
        assert [s.role_id for s in stages] == ["developer", "tester"]
        assert [s.name for s in stages] == ["develop", "test"]
        assert stages[1].depends_on == [stages[0].id]
        assert wf.status is WorkflowStatus.DRAFT


class TestPassPath:
    def test_pass_on_first_round_no_repair(self, wlife, project_id, loop_project):
        """首轮通过 → COMPLETED, 零修复轮, 零 LLM 分析调用。"""
        build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")
        provider = SeqProvider([])
        loop = make_loop(wlife, {
            "developer": make_dev_executor(loop_project, [V2_FIXED]),
            "tester": build_tester_executor(make_tester(provider)),
        })
        wf = loop.run("WF-1")
        assert wf.status is WorkflowStatus.COMPLETED
        assert len(wlife.list_stages("WF-1")) == 2  # 无修复轮
        assert provider.calls == []                 # 通过不调 LLM
        test_artifacts = [a for a in wlife.registry.list() if a.type.value == "test"]
        assert len(test_artifacts) == 1
        assert test_artifacts[0].metadata["bugs"] == []
        assert test_artifacts[0].status is ArtifactStatus.VALIDATED

    def test_pass_then_release_stage_proceeds(self, wlife, project_id, loop_project):
        """通过即 release 前置: 通过后剩余阶段 (release) 交回 base Runner 推进。"""
        wf = build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")
        test_stage = wlife.list_stages("WF-1")[1]
        wlife.create_stage("WF-1", "devops", name="release",
                           depends_on=[test_stage.id])
        provider = SeqProvider([])

        def release_stub(stage, context):  # noqa: ARG001 — executor 契约签名
            return {"artifact_type": "release",
                    "ref": "file:///dist/release.json",
                    "metadata": {
                        "build_result": {"status": "success", "command": "python -m build"},
                        "version": "1.0.0",
                        "package": {"name": "app", "type": "tar.gz",
                                    "files": ["dist/app-1.0.0.tar.gz"]},
                        "release_notes": "通过测试后的发布",
                        "deployment": "解压发布包并启动服务",
                    }}

        loop = make_loop(wlife, {
            "developer": make_dev_executor(loop_project, [V2_FIXED]),
            "tester": build_tester_executor(make_tester(provider)),
            "devops": release_stub,
        })
        wf = loop.run("WF-1")
        assert wf.status is WorkflowStatus.COMPLETED
        by_name = {s.name: s.status for s in wlife.list_stages("WF-1")}
        assert by_name["release"] is StageStatus.COMPLETED
        release_artifacts = [a for a in wlife.registry.list() if a.type.value == "release"]
        assert len(release_artifacts) == 1
        assert release_artifacts[0].status is ArtifactStatus.VALIDATED


class TestRepairLoop:
    def test_full_chain_two_repair_rounds(self, wlife, project_id, loop_project):
        """全链 ≤2 轮: dev→test→bug→repair→retest→…→通过 → COMPLETED。"""
        build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")
        provider = SeqProvider([
            bug_json("calc.py:6 (sub)", "calc.py:9 (mul)"),
            bug_json("calc.py:9 (mul)"),
        ])
        loop = make_loop(wlife, {
            "developer": make_dev_executor(loop_project, [V0_BUGGY, V1_PARTIAL, V2_FIXED]),
            "tester": build_tester_executor(make_tester(provider)),
        })
        wf = loop.run("WF-1")
        assert wf.status is WorkflowStatus.COMPLETED
        stages = wlife.list_stages("WF-1")
        assert [s.role_id for s in stages] == [
            "developer", "tester", "developer", "tester", "developer", "tester",
        ]
        assert all(s.status is StageStatus.COMPLETED for s in stages)
        assert len(provider.calls) == 2  # 仅失败轮次调 LLM 分析
        # 缺陷产物: 2 (round 0) + 1 (round 1) = 3 条 bug_report 全 VALIDATED
        bug_reports = [a for a in wlife.registry.list() if a.type.value == "bug_report"]
        assert len(bug_reports) == 3
        assert all(a.status is ArtifactStatus.VALIDATED for a in bug_reports)
        # 末轮 test 产物 bugs=[] (质量门禁通过; registry.list 按 id 排序,
        # 取末轮 tester stage 的产物而非列表末位)
        last_tester = [s for s in stages if s.role_id == "tester"][-1]
        last_test = [a for a in wlife.stage_artifacts(last_tester.id)
                     if a.type.value == "test"][-1]
        assert last_test.metadata["bugs"] == []
        assert last_test.metadata["results"]["passed"] is True

    def test_repair_stage_receives_bug_report_inputs(self, wlife, project_id, loop_project):
        """修复轮输入接线: repair stage 收到前序 test 的 bug_report 产物。"""
        build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")
        provider = SeqProvider([bug_json("calc.py:6 (sub)"), bug_json("calc.py:6 (sub)")])
        captured: list = []
        loop = make_loop(wlife, {
            "developer": make_dev_executor(loop_project, [V0_BUGGY, V2_FIXED],
                                           captured=captured),
            "tester": build_tester_executor(make_tester(provider)),
        })
        wf = loop.run("WF-1")
        assert wf.status is WorkflowStatus.COMPLETED
        assert captured, "repair 阶段应收到 bug_report 输入"
        meta = captured[0][0]
        assert meta["location"] == "calc.py:6 (sub)"
        # repair stage 的 input_artifacts 接线落库 (可审计)
        repair = [s for s in wlife.list_stages("WF-1") if s.name == "repair 1"][0]
        assert repair.input_artifacts, "repair 阶段 input_artifacts 应接线"
        assert repair.depends_on[0] == [s for s in wlife.list_stages("WF-1")
                                        if s.name == "test"][0].id

    def test_test_stage_input_wired_to_code_artifact(self, wlife, project_id, loop_project):
        """test 阶段输入接线: 输入 = 本轮 dev 的 code 产物 (自动回查)。"""
        build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")
        loop = make_loop(wlife, {
            "developer": make_dev_executor(loop_project, [V2_FIXED]),
            "tester": build_tester_executor(make_tester(SeqProvider([]))),
        })
        loop.run("WF-1")
        test = [s for s in wlife.list_stages("WF-1") if s.role_id == "tester"][0]
        assert test.input_artifacts
        code = wlife.registry.get(test.input_artifacts[0])
        assert code.type.value == "code"
        assert code.status is ArtifactStatus.VALIDATED

    def test_three_rounds_stop_failed(self, wlife, project_id, loop_project, event_store):
        """3 轮停止: 修复轮耗尽仍有缺陷 → FAILED (恰好 3 次测试, 无第 4 轮)。"""
        build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")
        provider = SeqProvider([bug_json("calc.py:6 (sub)", "calc.py:9 (mul)")])
        loop = make_loop(wlife, {
            "developer": make_dev_executor(loop_project, [V0_BUGGY, V0_BUGGY, V0_BUGGY]),
            "tester": build_tester_executor(make_tester(provider)),
        })
        wf = loop.run("WF-1")
        assert wf.status is WorkflowStatus.FAILED
        assert "test loop exhausted after 3 rounds" in wf.failed_reason
        assert "2 bug(s) remaining" in wf.failed_reason
        assert len(provider.calls) == 3  # 初始 + 2 修复轮, 禁无限
        assert len(wlife.list_stages("WF-1")) == 6  # 2 初始 + 2×2 动态
        # 失败事件带 stage_id 定位 (审计)
        from s7_helpers import payload_of

        payload = payload_of(event_store, "org.workflow.failed")
        assert payload["stage_id"]
        assert payload["status"] == "failed"


class TestRoundCap:
    def test_max_repair_rounds_zero(self, wlife, project_id, loop_project):
        """max_repair_rounds=0: 首轮失败即停止, 零修复轮。"""
        build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")
        provider = SeqProvider([bug_json("calc.py:6 (sub)")])
        loop = make_loop(wlife, {
            "developer": make_dev_executor(loop_project, [V0_BUGGY]),
            "tester": build_tester_executor(make_tester(provider)),
        }, max_repair_rounds=0)
        assert loop.max_repair_rounds == 0
        wf = loop.run("WF-1")
        assert wf.status is WorkflowStatus.FAILED
        assert len(provider.calls) == 1
        assert len(wlife.list_stages("WF-1")) == 2  # 无动态阶段

    def test_max_repair_rounds_one(self, wlife, project_id, loop_project):
        """max_repair_rounds=1: 最多 2 次测试轮次。"""
        build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")
        provider = SeqProvider([bug_json("calc.py:6 (sub)"), bug_json("calc.py:6 (sub)")])
        loop = make_loop(wlife, {
            "developer": make_dev_executor(loop_project, [V0_BUGGY, V0_BUGGY]),
            "tester": build_tester_executor(make_tester(provider)),
        }, max_repair_rounds=1)
        wf = loop.run("WF-1")
        assert wf.status is WorkflowStatus.FAILED
        assert len(provider.calls) == 2
        assert len(wlife.list_stages("WF-1")) == 4  # 2 初始 + 1×2 动态


class TestTerminalSemantics:
    def test_completed_rerun_idempotent(self, wlife, project_id, loop_project):
        build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")
        loop = make_loop(wlife, {
            "developer": make_dev_executor(loop_project, [V2_FIXED]),
            "tester": build_tester_executor(make_tester(SeqProvider([]))),
        })
        assert loop.run("WF-1").status is WorkflowStatus.COMPLETED
        # 重跑幂等: 不重复执行 (产物数不变 — 未新增执行)
        assert loop.run("WF-1").status is WorkflowStatus.COMPLETED
        assert len(wlife.registry.list()) == 2  # code + test (首轮通过产物)
        assert len([a for a in wlife.registry.list() if a.type.value == "code"]) == 1

    def test_failed_rerun_raises(self, wlife, project_id, loop_project):
        """FAILED 终态 run → WorkflowStateError (须 pause 人工介入)。"""
        build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")
        provider = SeqProvider([bug_json("calc.py:6 (sub)")])
        loop = make_loop(wlife, {
            "developer": make_dev_executor(loop_project, [V0_BUGGY]),
            "tester": build_tester_executor(make_tester(provider)),
        }, max_repair_rounds=0)
        assert loop.run("WF-1").status is WorkflowStatus.FAILED
        with pytest.raises(WorkflowStateError, match="failed workflow cannot run"):
            loop.run("WF-1")

    def test_draft_auto_activates(self, wlife, project_id, loop_project, event_store):
        build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")
        loop = make_loop(wlife, {
            "developer": make_dev_executor(loop_project, [V2_FIXED]),
            "tester": build_tester_executor(make_tester(SeqProvider([]))),
        })
        assert loop.run("WF-1").status is WorkflowStatus.COMPLETED
        assert "org.workflow.started" in event_sequence(event_store)


class TestHonestBoundaries:
    def test_dev_no_code_artifact_blocks(self, wlife, project_id):
        """dev 未产出 code 产物 → test BLOCKED → ACTIVE (不假装完成)。"""
        build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")

        def weird_dev(stage, context):
            return {"artifact_type": "test",
                    "metadata": {"results": {"passed": True}, "bugs": []}}

        loop = make_loop(wlife, {
            "developer": weird_dev,
            "tester": build_tester_executor(make_tester(SeqProvider([]))),
        })
        wf = loop.run("WF-1")
        assert wf.status is WorkflowStatus.ACTIVE
        by_name = {s.name: s.status for s in wlife.list_stages("WF-1")}
        assert by_name["develop"] is StageStatus.COMPLETED
        assert by_name["test"] is StageStatus.BLOCKED

    def test_interrupted_round_resume_after_reset(self, wlife, project_id, loop_project):
        """中断重跑: repair 阶段失败 → 人工重置 + failed→paused→active 恢复。"""
        build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")
        state = {"round": 0, "repair1_calls": 0}
        provider = SeqProvider([bug_json("calc.py:6 (sub)"), bug_json("calc.py:6 (sub)")])

        def dev_executor(stage, context):
            if stage.name == "repair 1":
                state["repair1_calls"] += 1
                if state["repair1_calls"] == 1:
                    raise RuntimeError("interrupted mid-repair")
            idx = min(state["round"], 1)  # V0 → FIXED
            state["round"] += 1
            files = [V0_BUGGY, V2_FIXED][idx]
            write_files(loop_project, files)
            return {"artifact_type": "code", "ref": "file:///src",
                    "metadata": {"files": list(files), "changes": "impl",
                                 "project_dir": str(loop_project)}}

        loop = make_loop(wlife, {
            "developer": dev_executor,
            "tester": build_tester_executor(make_tester(provider)),
        })
        wf1 = loop.run("WF-1")
        assert wf1.status is WorkflowStatus.FAILED
        assert "interrupted mid-repair" in wf1.failed_reason
        repair = [s for s in wlife.list_stages("WF-1") if s.name == "repair 1"][0]
        assert repair.status is StageStatus.FAILED
        # 人工介入: 重置失败 stage (failed→pending) + workflow 恢复
        wlife.transition_stage(repair.id, StageStatus.PENDING)
        wlife.pause("WF-1")
        wf2 = loop.run("WF-1")
        assert wf2.status is WorkflowStatus.COMPLETED


class TestAudit:
    def test_dynamic_stages_audited(self, wlife, project_id, loop_project, event_store):
        """动态修复轮全部经 org.stage.created 审计 (阶段可追踪)。"""
        build_dev_test_workflow(wlife, project_id, "Loop", workflow_id="WF-1")
        provider = SeqProvider([
            bug_json("calc.py:6 (sub)"),
            bug_json("calc.py:6 (sub)"),
        ])
        loop = make_loop(wlife, {
            "developer": make_dev_executor(loop_project, [V0_BUGGY, V1_PARTIAL, V2_FIXED]),
            "tester": build_tester_executor(make_tester(provider)),
        })
        loop.run("WF-1")
        seq = event_sequence(event_store)
        assert seq.count("org.stage.created") == 6  # 2 初始 + 4 动态
        assert "org.workflow.completed" in seq
        assert seq.count("org.artifact.validated") >= 4  # code×3 + test×3 (+bug_report×3)

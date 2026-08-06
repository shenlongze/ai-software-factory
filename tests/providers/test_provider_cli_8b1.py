"""test_provider_cli_8b1.py — CLI: execution run --provider / 项目配置 provider /
workflow run --auto Provider 集成 (Phase 8B-1, ADR-0023)。

覆盖:
- execution run --provider <id> 显式: provider.selected (payload execution_id/source=
  explicit) → provider.execution.started → completed|failed; input 持久化 provider_id;
  未注册 → rc 7 (执行保持 PENDING); 未找到执行 → rc 7; 状态冲突重跑 → rc 1 无新事件
- 项目配置 (workspace/projects/<id>/project.yaml runtime_preferences.<task_type>.provider)
  → source=project; 任务类型不匹配 / provider DISABLED / 配置损坏 → 降级旧链路
- 注册表默认 (providers/catalog.json default) → source=default
- 无配置 → 旧链路: 零 provider 事件, input 零注入
- workflow run --auto: 项目配置 → provider.* 事件含 execution_id; 无配置 → 逐位不变

种子模式同 tests/execution/test_cli_execution_run.py (engine.execute_step 落
pending 执行); project.yaml 种子经 workspace/projects 目录 (load_project_definition)。
"""

from __future__ import annotations

import json

from cli_helpers import event_types, open_events, run_cli
from events.store import EventStore
from runtime.models import ExecutionStatus
from runtime.store import RuntimeStore
from tasks.store import TaskStore
from workflows.engine import WorkflowEngine
from workflows.store import WorkflowStore

from providers.models import ProviderStatus
from providers.store import ProviderStore

from providers_helpers import make_definition


def _seed_cli_execution(
    capsys, cli_root, *, task_id: str = "T-001", steps: str = "s1",
    runtime: bool = True, input: dict | None = None, project: str | None = None,
) -> str:
    """CLI 装配 workflow/task/run (+ runtime 身份), 经引擎 execute_step 落 pending 执行。

    - project: 任务归属项目 (project.yaml provider 配置生效的前提)。
    - input: 覆盖执行请求输入 (测 Echo fail 分支)。
    """
    run_cli(capsys, cli_root, "workflow", "add", "--id", "wf-test", "--steps", steps)
    argv = ["task", "create", "--id", task_id, "--title", "任务", "--workflow", "wf-test"]
    if project is not None:
        argv += ["--project", project]
    run_cli(capsys, cli_root, *argv)
    run_cli(capsys, cli_root, "workflow", "run", task_id)
    if runtime:
        run_cli(capsys, cli_root, "runtime", "add", "--id", "echo", "--type", "mock")
    engine = WorkflowEngine(
        WorkflowStore(cli_root / "workflows"),
        task_store=TaskStore(cli_root / "tasks"),
        runtime_store=RuntimeStore(cli_root / "runtimes"),
        logger=None,
    )
    req, _ = engine.execute_step(task_id, steps.split(",")[0])
    if input is not None:
        req = req.model_copy(update={"input": input})
        RuntimeStore(cli_root / "runtimes").save_execution(req)
    return req.id


def _write_project(
    cli_root, project_id: str = "markpad", *,
    provider: str | None = None, task_type: str = "feature",
    runtime: str | None = None, corrupt: bool = False,
) -> None:
    """写 workspace/projects/<id>/project.yaml (runtime_preferences.<task_type>)。"""
    d = cli_root / "workspace" / "projects" / project_id
    d.mkdir(parents=True, exist_ok=True)
    if corrupt:
        (d / "project.yaml").write_text("name: [broken\n  -yaml::", encoding="utf-8")
        return
    lines = [
        f"name: {project_id}",
        "language: python",
        "repository: /Users/Shared/work/dummy",
        "description: \"provider test project\"",
        "tech_stack: [python]",
    ]
    if provider is not None or runtime is not None:
        lines.append("runtime_preferences:")
        lines.append(f"  {task_type}:")
        if provider is not None:
            lines.append(f"    provider: {provider}")
        if runtime is not None:
            lines.append(f"    runtime: {runtime}")
    (d / "project.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _register_provider(cli_root, provider_id: str, *, status=ProviderStatus.ACTIVE):
    """直接落盘 Provider 定义 (register 冲突默认 id 保留, 用 store upsert)。"""
    store = ProviderStore(cli_root / "providers")
    store.save_definition(make_definition(provider_id, status=status))
    return store


def _provider_events(store: EventStore) -> list:
    return [e for e in store.query() if e.type.value.startswith("provider.")]


class TestExecutionRunExplicit:
    def test_run_with_provider_rc0(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        assert rc == 0, err
        assert "SUCCESS" in out

    def test_emits_provider_selected(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        with open_events(cli_root) as store:
            evs = _provider_events(store)
            assert evs[0].type.value == "provider.selected"

    def test_selected_payload_execution_id(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        with open_events(cli_root) as store:
            ev = _provider_events(store)[0]
            assert ev.payload["execution_id"] == exec_id

    def test_selected_payload_source_explicit(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        with open_events(cli_root) as store:
            ev = _provider_events(store)[0]
            assert ev.payload["source"] == "explicit"

    def test_selected_payload_provider_id(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        with open_events(cli_root) as store:
            assert _provider_events(store)[0].payload["provider_id"] == "hermes"

    def test_provider_event_chain(self, capsys, cli_root):
        """成功链路: execution.started → selected → started → completed → execution.completed。"""
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        with open_events(cli_root) as store:
            types = event_types(store)
            assert types[-7:] == [
                "execution.started", "provider.selected", "provider.execution.started",
                "provider.execution.completed", "execution.completed",
                "workflow.step.completed", "workflow.completed",
            ]

    def test_all_provider_events_carry_execution_id(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        with open_events(cli_root) as store:
            assert all(
                ev.payload.get("execution_id") == exec_id
                for ev in _provider_events(store)
            )

    def test_provider_events_source_cli(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        with open_events(cli_root) as store:
            assert all(ev.source == "cli" for ev in _provider_events(store))

    def test_input_persisted_with_provider_id(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        request = RuntimeStore(cli_root / "runtimes").get_execution(exec_id)
        assert request.input["provider_id"] == "hermes"

    def test_json_output_input_has_provider_id(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "--json", "execution", "run", exec_id,
                               "--provider", "hermes")
        assert rc == 0, err
        data = json.loads(out)
        assert data["execution"]["input"]["provider_id"] == "hermes"
        assert data["status"] == "SUCCESS"

    def test_run_result_echo_unaffected(self, capsys, cli_root):
        """载波不改变 Runtime 执行结果 (echo 仍回显, 未知键被忽略)。"""
        exec_id = _seed_cli_execution(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "--json", "execution", "run", exec_id,
                               "--provider", "hermes")
        data = json.loads(out)
        assert data["result"]["output"]["runtime_id"] == "echo"

    def test_failed_run_emits_provider_failed(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root, input={"fail": "boom"})
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        assert rc == 0  # run 命令本身成功; 业务结果 FAILED
        with open_events(cli_root) as store:
            types = event_types(store)
            assert types[-6:] == [
                "execution.started", "provider.selected", "provider.execution.started",
                "provider.execution.failed", "execution.failed", "workflow.failed",
            ]

    def test_failed_payload_error(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root, input={"fail": "boom"})
        run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        with open_events(cli_root) as store:
            failed = [e for e in _provider_events(store)
                      if e.type.value == "provider.execution.failed"][0]
            assert failed.payload["error"] == "boom"
            assert failed.payload["execution_id"] == exec_id

    def test_unregistered_provider_rc7(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "NO-SUCH")
        assert rc == 7
        assert "NO-SUCH" in err

    def test_unregistered_provider_keeps_execution_pending(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "NO-SUCH")
        request = RuntimeStore(cli_root / "runtimes").get_execution(exec_id)
        assert request.status is ExecutionStatus.PENDING
        assert "provider_id" not in request.input

    def test_unregistered_provider_emits_no_provider_events(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "NO-SUCH")
        with open_events(cli_root) as store:
            assert _provider_events(store) == []

    def test_not_found_execution_rc7_with_provider(self, capsys, cli_root):
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", "EX-999", "--provider", "hermes")
        assert rc == 7
        assert "not found" in err

    def test_whitespace_provider_falls_to_old_chain(self, capsys, cli_root):
        """--provider \"  \" → 显式层视为缺失 → 无配置 → 旧链路零 provider 事件。"""
        exec_id = _seed_cli_execution(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "   ")
        assert rc == 0, err
        with open_events(cli_root) as store:
            assert _provider_events(store) == []

    def test_rerun_state_conflict_no_new_provider_events(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        assert rc == 1
        assert "expected PENDING" in err
        with open_events(cli_root) as store:
            assert len(_provider_events(store)) == 3  # 仅首次派发点的事件

    def test_explicit_wins_over_registry_default(self, capsys, cli_root):
        """默认层已设置 hermes 时, 显式 --provider 仍标 source=explicit。"""
        ProviderStore(cli_root / "providers").save_default("hermes")
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        with open_events(cli_root) as store:
            assert _provider_events(store)[0].payload["source"] == "explicit"


class TestExecutionRunProjectConfig:
    def test_project_config_source_project(self, capsys, cli_root):
        _write_project(cli_root, provider="hermes")
        exec_id = _seed_cli_execution(capsys, cli_root, project="markpad")
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id)
        assert rc == 0, err
        with open_events(cli_root) as store:
            ev = _provider_events(store)[0]
            assert ev.payload["source"] == "project"
            assert ev.payload["provider_id"] == "hermes"
            assert ev.payload["execution_id"] == exec_id

    def test_project_config_provider_chain(self, capsys, cli_root):
        _write_project(cli_root, provider="hermes")
        exec_id = _seed_cli_execution(capsys, cli_root, project="markpad")
        run_cli(capsys, cli_root, "execution", "run", exec_id)
        with open_events(cli_root) as store:
            types = [e.type.value for e in _provider_events(store)]
            assert types == [
                "provider.selected", "provider.execution.started",
                "provider.execution.completed",
            ]

    def test_project_config_input_persisted(self, capsys, cli_root):
        _write_project(cli_root, provider="hermes")
        exec_id = _seed_cli_execution(capsys, cli_root, project="markpad")
        run_cli(capsys, cli_root, "execution", "run", exec_id)
        request = RuntimeStore(cli_root / "runtimes").get_execution(exec_id)
        assert request.input["provider_id"] == "hermes"

    def test_project_config_custom_task_type(self, capsys, cli_root):
        """任务 --type local → 命中 runtime_preferences.local.provider。"""
        _write_project(cli_root, provider="hermes", task_type="local")
        run_cli(capsys, cli_root, "workflow", "add", "--id", "wf-test", "--steps", "s1")
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "x",
                "--workflow", "wf-test", "--type", "local", "--project", "markpad")
        run_cli(capsys, cli_root, "workflow", "run", "T-001")
        run_cli(capsys, cli_root, "runtime", "add", "--id", "echo", "--type", "mock")
        store = EventStore(cli_root / "factory.db")
        try:
            engine = WorkflowEngine(
                WorkflowStore(cli_root / "workflows"),
                task_store=TaskStore(cli_root / "tasks"),
                runtime_store=RuntimeStore(cli_root / "runtimes"),
                logger=None,
            )
            req, _ = engine.execute_step("T-001", "s1")
        finally:
            store.close()
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", req.id)
        assert rc == 0, err
        with open_events(cli_root) as store:
            ev = _provider_events(store)[0]
            assert ev.payload["source"] == "project"

    def test_project_config_task_type_mismatch_old_chain(self, capsys, cli_root):
        """prefs 只有 local 条目, 任务 feature → 不命中 → 零 provider 事件。"""
        _write_project(cli_root, provider="hermes", task_type="local")
        exec_id = _seed_cli_execution(capsys, cli_root, project="markpad")
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id)
        assert rc == 0, err
        with open_events(cli_root) as store:
            assert _provider_events(store) == []

    def test_project_config_disabled_provider_downgrades(self, capsys, cli_root):
        """provider DISABLED → 项目层缺失 → 无默认 → 旧链路。"""
        _write_project(cli_root, provider="openai")
        _register_provider(cli_root, "openai", status=ProviderStatus.DISABLED)
        exec_id = _seed_cli_execution(capsys, cli_root, project="markpad")
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id)
        assert rc == 0, err
        with open_events(cli_root) as store:
            assert _provider_events(store) == []

    def test_project_config_corrupt_yaml_old_chain(self, capsys, cli_root):
        _write_project(cli_root, provider="hermes", corrupt=True)
        exec_id = _seed_cli_execution(capsys, cli_root, project="markpad")
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id)
        assert rc == 0, err  # 配置损坏 → 降级, 不破坏执行
        with open_events(cli_root) as store:
            assert _provider_events(store) == []

    def test_explicit_overrides_project_config(self, capsys, cli_root):
        """项目配置 openai + --provider hermes → 显式层胜出 (source=explicit)。"""
        _write_project(cli_root, provider="openai")
        _register_provider(cli_root, "openai")
        exec_id = _seed_cli_execution(capsys, cli_root, project="markpad")
        run_cli(capsys, cli_root, "execution", "run", exec_id, "--provider", "hermes")
        with open_events(cli_root) as store:
            ev = _provider_events(store)[0]
            assert ev.payload["provider_id"] == "hermes"
            assert ev.payload["source"] == "explicit"

    def test_project_without_yaml_old_chain(self, capsys, cli_root):
        """任务归属项目但无 project.yaml → None → 旧链路。"""
        exec_id = _seed_cli_execution(capsys, cli_root, project="ghost")
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id)
        assert rc == 0, err
        with open_events(cli_root) as store:
            assert _provider_events(store) == []


class TestExecutionRunDefaultLayer:
    def test_registry_default_source_default(self, capsys, cli_root):
        ProviderStore(cli_root / "providers").save_default("hermes")
        exec_id = _seed_cli_execution(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id)
        assert rc == 0, err
        with open_events(cli_root) as store:
            ev = _provider_events(store)[0]
            assert ev.payload["source"] == "default"
            assert ev.payload["provider_id"] == "hermes"

    def test_registry_default_chain(self, capsys, cli_root):
        ProviderStore(cli_root / "providers").save_default("hermes")
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id)
        with open_events(cli_root) as store:
            assert len(_provider_events(store)) == 3

    def test_project_config_wins_over_default(self, capsys, cli_root):
        """项目层 > 默认层 (source=project)。"""
        ProviderStore(cli_root / "providers").save_default("hermes")
        _write_project(cli_root, provider="hermes")
        exec_id = _seed_cli_execution(capsys, cli_root, project="markpad")
        run_cli(capsys, cli_root, "execution", "run", exec_id)
        with open_events(cli_root) as store:
            assert _provider_events(store)[0].payload["source"] == "project"


class TestNoConfigOldChain:
    def test_no_config_zero_provider_events(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "execution", "run", exec_id)
        assert rc == 0, err
        with open_events(cli_root) as store:
            assert _provider_events(store) == []

    def test_no_config_event_chain_unchanged(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id)
        with open_events(cli_root) as store:
            types = event_types(store)
            assert types[-4:] == [
                "execution.started", "execution.completed",
                "workflow.step.completed", "workflow.completed",
            ]

    def test_no_config_input_has_no_provider_id(self, capsys, cli_root):
        exec_id = _seed_cli_execution(capsys, cli_root)
        run_cli(capsys, cli_root, "execution", "run", exec_id)
        request = RuntimeStore(cli_root / "runtimes").get_execution(exec_id)
        assert "provider_id" not in request.input

    def test_no_config_pending_input_not_rewritten(self, capsys, cli_root):
        """选择为 None → 不触碰已落盘请求 (input 原样)。"""
        exec_id = _seed_cli_execution(capsys, cli_root, input={"keep": 1})
        run_cli(capsys, cli_root, "execution", "run", exec_id)
        request = RuntimeStore(cli_root / "runtimes").get_execution(exec_id)
        assert request.input == {"keep": 1}


class TestWorkflowRunAuto:
    def _seed_auto(self, capsys, cli_root, *, project: str | None = None) -> None:
        if project is not None:
            _write_project(cli_root, provider="hermes")
        run_cli(capsys, cli_root, "workflow", "add", "--id", "wf-a", "--steps", "s1")
        run_cli(capsys, cli_root, "task", "create", "--id", "T-001", "--title", "x",
                "--workflow", "wf-a", "--project", project or "noproj")
        run_cli(capsys, cli_root, "agent", "add", "--id", "A-001", "--role", "backend-developer",
                "--skills", "dev")
        run_cli(capsys, cli_root, "runtime", "add", "--id", "echo", "--type", "mock")

    def test_auto_with_project_provider_rc0(self, capsys, cli_root):
        self._seed_auto(capsys, cli_root, project="markpad")
        rc, out, err = run_cli(capsys, cli_root, "workflow", "run", "T-001", "--auto")
        assert rc == 0, err
        assert "COMPLETED" in out

    def test_auto_emits_provider_selected_with_execution_id(self, capsys, cli_root):
        self._seed_auto(capsys, cli_root, project="markpad")
        run_cli(capsys, cli_root, "workflow", "run", "T-001", "--auto")
        with open_events(cli_root) as store:
            evs = _provider_events(store)
            assert evs[0].type.value == "provider.selected"
            assert evs[0].payload["source"] == "project"
            assert evs[0].payload["execution_id"]

    def test_auto_provider_chain_completed(self, capsys, cli_root):
        self._seed_auto(capsys, cli_root, project="markpad")
        run_cli(capsys, cli_root, "workflow", "run", "T-001", "--auto")
        with open_events(cli_root) as store:
            types = [e.type.value for e in _provider_events(store)]
            assert types == [
                "provider.selected", "provider.execution.started",
                "provider.execution.completed",
            ]

    def test_auto_all_provider_events_have_execution_id(self, capsys, cli_root):
        self._seed_auto(capsys, cli_root, project="markpad")
        run_cli(capsys, cli_root, "workflow", "run", "T-001", "--auto")
        with open_events(cli_root) as store:
            assert all(ev.payload.get("execution_id") for ev in _provider_events(store))

    def test_auto_without_config_zero_provider_events(self, capsys, cli_root):
        self._seed_auto(capsys, cli_root)
        rc, out, err = run_cli(capsys, cli_root, "workflow", "run", "T-001", "--auto")
        assert rc == 0, err
        assert "COMPLETED" in out
        with open_events(cli_root) as store:
            assert _provider_events(store) == []

    def test_auto_without_config_unchanged(self, capsys, cli_root):
        """无配置 → --auto 旧链路逐位不变 (无 provider.selected 事件)。

        workflow run --auto 走 orchestration pipeline, 终态事件是
        orchestration.completed (既有正确行为, ADR-0010); 本测试只验证
        provider 集成零侵入: 核心断言是 "provider.selected" not in types。
        """
        self._seed_auto(capsys, cli_root)
        run_cli(capsys, cli_root, "workflow", "run", "T-001", "--auto")
        with open_events(cli_root) as store:
            types = event_types(store)
            assert "provider.selected" not in types
            assert types[-1] == "orchestration.completed"

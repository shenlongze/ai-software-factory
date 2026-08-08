"""tests/s9/s9_helpers.py — S9-001 测试构造/断言 helper (唯一名)。

所有 executor 产物 metadata 与 factory-org/org/artifact.py CONTRACTS **同源**
(S9-001 冒烟阻断: executor metadata 曾用 prd/code 字段不符合契约 — 本文件
按 CONTRACTS required_fields/validation_rules 逐字段构造, 供冒烟/全链测试):

- prd_payload_ok: 合法 prd 契约载荷 (problem/user/features — CONTRACTS prd)
- design_payload_ok: 合法 design 契约载荷 (7 节; api_design 必含 endpoints,
  task_breakdown 每项含 module/task/api_contract/ui_guidance)
- code_payload_ok: 合法 code 契约载荷 (files/changes)
- qa_payload_ok: 合法 test 契约载荷 (results 含 passed + bugs — VALIDATED
  语义; 命名避开 test_* 前缀防 pytest 误收集, 同 s8 helpers)
- release_payload_ok: 合法 release 契约载荷 (5 节; build_result 必含
  status/command; package 必含 name/type/files)
- make_*_artifact: executor context inputs 产物 dict (type + metadata)
- approval_chain_executor: 全链 mock executor (role → 契约合法产物; 非 LLM
  占位语义, 同 demo.py 模式)
- build_approval_workflow: 5 阶段三挡板 workflow (pm/arch/devops 三
  approval_required 门 — P1 MVP / P2 架构 / P3 发布)
- event_sequence / payload_of: 事件库断言辅助 (org.approval.* /
  org.workflow.*)
"""

from __future__ import annotations

from typing import Any, Callable

from org.workflow import WorkflowLifecycle


# ------------------------------------------------------------------ 契约载荷
# 字段与 factory-org/org/artifact.py CONTRACTS 逐条对应 (同源, 冒烟阻断修复)。

def prd_payload_ok(*, feature_count: int = 2) -> dict[str, Any]:
    """合法 prd 契约载荷 (CONTRACTS prd: problem/user/features)。"""
    return {
        "problem": "人工审批缺失, 交付无人确认 (S9-001 冒烟)",
        "user": "工厂运营者 (human-in-the-loop)",
        "features": [f"审批功能 {i}" for i in range(1, feature_count + 1)],
    }


def design_payload_ok(*, endpoint_count: int = 1, task_count: int = 1) -> dict[str, Any]:
    """合法 design 契约载荷 (CONTRACTS design 7 节; api_design 必含
    endpoints; task_breakdown 每项含 module/task/api_contract/ui_guidance)。"""
    endpoints = [
        {
            "method": "POST",
            "path": f"/api/v1/approvals/{i}",
            "contract": f"审批接口 {i}: 请求/响应数据形状",
        }
        for i in range(1, endpoint_count + 1)
    ]
    tasks = [
        {
            "module": f"approval_{i}",
            "task": f"实现审批模块 {i} 核心逻辑",
            "api_contract": f"模块 {i} 依赖的 API 约定 (端点/数据形状)",
            "ui_guidance": f"模块 {i} 的 UI 实现指导 (依据 wireframe/spec)",
        }
        for i in range(1, task_count + 1)
    ]
    return {
        "system_architecture": "三层: CLI 审批命令 + ApprovalGate 状态机 + JSON 持久化",
        "technical_stack": {"language": "python", "runtime": "stdlib"},
        "database_design": {"storage": "org/approvals.json (原子写)"},
        "api_design": {"endpoints": endpoints},
        "frontend_architecture": "无前端 (CLI 优先, S9-005 Console 后接)",
        "backend_architecture": "approval.py 领域模型 + workflow.py 接线",
        "task_breakdown": tasks,
    }


def code_payload_ok(*, file_count: int = 1) -> dict[str, Any]:
    """合法 code 契约载荷 (CONTRACTS code: files/changes)。"""
    return {
        "files": [f"src/approval_{i}.py" for i in range(1, file_count + 1)],
        "changes": "实现 Approval Gate 状态机与持久化 (S9-001)",
    }


def qa_payload_ok(*, passed: Any = True, bug_count: int = 0) -> dict[str, Any]:
    """合法 test 契约载荷 (CONTRACTS test: results 含 passed + bugs —
    VALIDATED 语义: 通过 = passed 为真 + bugs 空)。"""
    return {
        "results": {"passed": passed, "total": 3, "failed": 0},
        "bugs": [{"location": f"b{i}"} for i in range(bug_count)],
    }


def release_payload_ok(*, build_status: str = "success") -> dict[str, Any]:
    """合法 release 契约载荷 (CONTRACTS release 5 节; build_result 必含
    status/command; package 必含 name/type/files)。"""
    return {
        "build_result": {"status": build_status, "command": "python -m build"},
        "version": "1.0.0",
        "package": {
            "name": "approval-demo",
            "type": "tar.gz",
            "files": ["dist/approval-demo-1.0.0.tar.gz"],
        },
        "release_notes": "S9-001 审批门全链冒烟发布 (mock executor 占位)",
        "deployment": "解压发布包 → 安装依赖 → 启动服务 → 健康检查",
    }


# ------------------------------------------------------------ executor 产物 dict

def make_prd_artifact(
    *, payload: dict[str, Any] | None = None, ref: str = "file:///docs/prd.json"
) -> dict[str, Any]:
    """prd 产物 dict (executor context inputs 契约: type == "prd")。"""
    return {"type": "prd", "ref": ref, "metadata": payload or prd_payload_ok()}


def make_design_artifact(
    *, payload: dict[str, Any] | None = None, ref: str = "file:///docs/design.json"
) -> dict[str, Any]:
    """design 产物 dict (executor context inputs 契约: type == "design")。"""
    return {"type": "design", "ref": ref, "metadata": payload or design_payload_ok()}


def make_code_artifact(
    *, payload: dict[str, Any] | None = None, ref: str = "file:///src"
) -> dict[str, Any]:
    """code 产物 dict (executor context inputs 契约: type == "code")。"""
    return {"type": "code", "ref": ref, "metadata": payload or code_payload_ok()}


def make_test_artifact(
    *, payload: dict[str, Any] | None = None, ref: str = "file:///test_result.json"
) -> dict[str, Any]:
    """test 产物 dict (executor context inputs 契约: type == "test")。"""
    return {"type": "test", "ref": ref, "metadata": payload or qa_payload_ok()}


def make_release_artifact(
    *, payload: dict[str, Any] | None = None, ref: str = "file:///dist/release.tar.gz"
) -> dict[str, Any]:
    """release 产物 dict (executor context inputs 契约: type == "release")。"""
    return {"type": "release", "ref": ref, "metadata": payload or release_payload_ok()}


# ------------------------------------------------------------ mock executors

#: role → 契约合法产物 (与 ROLE_OUTPUT_TYPES 同源; metadata 全 CONTRACTS 合法)
_ROLE_OUTPUT: dict[str, Callable[[], dict[str, Any]]] = {
    "product-manager": lambda: make_prd_artifact(),
    "architect": lambda: make_design_artifact(),
    "developer": lambda: make_code_artifact(),
    "tester": lambda: make_test_artifact(),
    "devops": lambda: make_release_artifact(),
}


def approval_chain_executor(
    stage: Any, context: dict[str, Any]
) -> dict[str, Any]:
    """全链 mock executor (非 LLM 占位语义; 按 role 产出契约合法产物)。

    冒烟阻断修复点: metadata 必须经 validate_artifact 校验通过 (与
    org CONTRACTS 同源 — 用 _ROLE_OUTPUT 单一来源, 禁止手写零散字段)。
    """
    make = _ROLE_OUTPUT.get(stage.role_id)
    if make is None:
        raise AssertionError(f"no mock output for role {stage.role_id!r}")
    return make()


# ------------------------------------------------------------ workflow 构造

def build_approval_workflow(
    lifecycle: WorkflowLifecycle,
    project_id: str,
    *,
    workflow_id: str | None = None,
    name: str = "Approval Gate Chain",
) -> Any:
    """5 阶段三挡板 workflow (S9-001 冒烟/生命周期测试基座):

    product-manager (P1 MVP 门) → architect (P2 架构门) → developer →
    tester → devops (P3 发布门)。线性 depends_on 链 (无 input_artifacts
    预接线 — Runner 自动注册输出, 就绪判定只依赖 depends_on)。
    """
    wf = lifecycle.create_workflow(project_id, name, workflow_id=workflow_id)
    prev: Any = None
    for role_id, gate in (
        ("product-manager", True),
        ("architect", True),
        ("developer", False),
        ("tester", False),
        ("devops", True),
    ):
        prev = lifecycle.create_stage(
            wf.id,
            role_id,
            name=f"{role_id} stage",
            depends_on=[prev.id] if prev is not None else None,
            approval_required=gate,
        )
    return wf


# ------------------------------------------------------------ 事件断言辅助

def event_sequence(store: Any) -> list[str]:
    return [e.type.value for e in store.query()]


def payload_of(store: Any, event_type: str) -> dict[str, Any]:
    for e in store.query():
        if e.type.value == event_type:
            return dict(e.payload)
    raise AssertionError(f"no event of type {event_type!r} found")

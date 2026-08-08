"""factory-org/org/demo.py — S7-005 Full Chain Demo 定义 (标准, 可复现)。

设计依据 (sprint7-architecture.md §1/§3 任务级 → 组织级):
```
User → Project → Workflow → Stage → Artifact:
  Product (product-manager) → Architecture (architect) → Development (developer)
  → Testing (tester) → Release (devops)
每阶段产物 = 下一阶段输入: PRD → Design → Code → Test → Release
```

本模块 = Demo 定义 + 构造 (KISS, 只组合不重写 — 约束 S7-005):
- build_demo_workflow: 5 阶段全链 (Product→Architecture→Development→
  Testing→Release), depends_on 链 + input_artifacts 预定义 (Artifact 链:
  每阶段输入 = 前阶段输出 id 引用)
- build_demo_loop_workflow: Tester Loop 变体 (Development→Testing→Release)
  — DevTestLoopRunner 语义 (dev/test 初始对 + 修复轮 + 通过即 release 前置)
- mock role executors (PM/Architect/Developer/DevOps): 非 LLM 占位语义
  (集成验证链正确性, 非能力证明; 能力已由 Sprint 6.5 证明, 本 Sprint 只
  组合既有注入点)
- make_tester_executor: 包装 exec.tester.build_tester_executor — 初始
  Testing 阶段 test 产物固定 id (Artifact 链预定义引用), retest/repair
  轮次自动 id (防重复注册)

诚实标注 (Demo 用 mock 处明确标注):
- Product/Architecture/Release: mock executor (占位语义, 非 LLM — 对应角色
  execution_kind=planning; PM/Architect/Release Agent 自动化 = Sprint 8,
  本 Sprint 不实现)
- Development: mock executor (产出 code artifact + 真实写文件 — Developer
  真实 LLM 能力由 Sprint 6.5 exec 引擎证明; Demo 注入确定性版本轨迹, 供
  Tester 真实确定性测试执行)
- Testing: 真实 TesterAgent (确定性测试执行 + LLM 失败分析 — 调用方注入;
  生产 = DeepSeek v4-pro, Demo 测试注入 mock provider)
- 约束: 零重写 (EmployeeExecutor/Workflow/Artifact/Tester 只组合); Demo
  零 LLM 调用; Core/Runtime/Desktop 冻结。
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Callable

from .projects import Stage
from .workflow import Workflow

# ------------------------------------------------------------------ Demo 定义

#: Demo 5 阶段链 (标准, 可复现): 阶段名 / role_id (exec 注册表单一事实源) /
#: 输出产物类型 (ROLE_OUTPUT_TYPES 同源)。阶段输入 = 前阶段输出 (Artifact 链)。
DEMO_STAGES: list[dict[str, str]] = [
    {"name": "Product", "role_id": "product-manager", "output_type": "prd"},
    {"name": "Architecture", "role_id": "architect", "output_type": "design"},
    {"name": "Development", "role_id": "developer", "output_type": "code"},
    {"name": "Testing", "role_id": "tester", "output_type": "test"},
    {"name": "Release", "role_id": "devops", "output_type": "release"},
]

#: Demo Artifact 链预定义 id (每阶段输入 = 前阶段输出; 唯一, 可复现断言)。
#: 前缀 A-DEMO- 唯一命名 (与既有 A-xxxx 自动 id 无冲突)。
DEMO_ARTIFACT_IDS: dict[str, str] = {
    "prd": "A-DEMO-PRD",
    "design": "A-DEMO-DESIGN",
    "code": "A-DEMO-CODE",
    "test": "A-DEMO-TEST",
    "release": "A-DEMO-RELEASE",
}

#: Demo mock 产物占位内容 (非 LLM — 占位语义; 契约经 validate_artifact 校验)
_DEMO_PRD_METADATA: dict[str, Any] = {
    "problem": "Demo 示例产品: 验证组织级全开发链 (集成验证)",
    "user": "示例用户 (demo mock)",
    "features": ["核心功能 (demo mock 占位)"],
}
_DEMO_DESIGN_METADATA: dict[str, Any] = {
    "architecture": "单模块纯函数 (demo mock 占位)",
    "api": "calc 模块 API (demo mock 占位)",
    "database": "无 (纯函数, demo mock 占位)",
}
_DEMO_RELEASE_METADATA: dict[str, Any] = {
    "version": "1.0.0",
    "notes": "Release 占位 (mock executor, 非 LLM — S7-005 集成验证)",
    "artifact_ref": "file:///dist/demo-1.0.0.tar.gz",
}


# ------------------------------------------------------------------ Workflow 构造

def build_demo_workflow(
    lifecycle: Any,
    project_id: str,
    *,
    workflow_id: str | None = None,
    name: str = "Full Chain Demo",
) -> Workflow:
    """创建 Demo 全链 workflow (5 阶段: Product→Architecture→Development→
    Testing→Release)。

    - depends_on: 线性链 (每阶段依赖前一阶段; 首个无依赖)
    - input_artifacts: 预定义 = 前阶段输出 id (Artifact 链: PRD→Design→
      Code→Test→Release; Runner 就绪判定要求 VALIDATED)
    - role_id 经 exec 注册表校验 (create_stage 内建, 未安装跳过)
    """
    wf = lifecycle.create_workflow(project_id, name, workflow_id=workflow_id)
    prev: Stage | None = None
    prev_output: str | None = None
    for spec in DEMO_STAGES:
        stage = lifecycle.create_stage(
            wf.id,
            spec["role_id"],
            name=spec["name"],
            depends_on=[prev.id] if prev is not None else None,
            input_artifacts=[DEMO_ARTIFACT_IDS[prev_output]] if prev_output else None,
        )
        prev, prev_output = stage, spec["output_type"]
    return wf


def build_demo_loop_workflow(
    lifecycle: Any,
    project_id: str,
    *,
    workflow_id: str | None = None,
    name: str = "Full Chain Demo (Tester Loop)",
) -> Workflow:
    """创建 Tester Loop 变体 workflow (3 阶段: Development→Testing→Release)。

    DevTestLoopRunner 语义 (S7-004): dev/test 初始对 (test 输入自动接线为
    本轮 dev 的 code 产物) → 失败动态创建 repair/retest (≤2 轮) → 通过后
    剩余 release 阶段交回 base Runner 推进。release 输入预定义 = 初始
    Testing 阶段 test 产物 (A-DEMO-TEST, 由 make_tester_executor 固定 id)。
    """
    wf = lifecycle.create_workflow(project_id, name, workflow_id=workflow_id)
    dev = lifecycle.create_stage(wf.id, "developer", name="Development")
    test = lifecycle.create_stage(
        wf.id, "tester", name="Testing", depends_on=[dev.id]
    )
    lifecycle.create_stage(
        wf.id,
        "devops",
        name="Release",
        depends_on=[test.id],
        input_artifacts=[DEMO_ARTIFACT_IDS["test"]],
    )
    return wf


# ------------------------------------------------------------------ Mock executors (非 LLM 占位语义)

def pm_executor() -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """Product mock executor (非 LLM 占位语义; execution_kind=planning,
    PM Agent 自动化 = Sprint 8)。产出 PRD artifact (契约: problem/user/features)。"""

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "artifact_type": "prd",
            "artifact_id": DEMO_ARTIFACT_IDS["prd"],
            "ref": "file:///docs/prd.md",
            "metadata": dict(_DEMO_PRD_METADATA),
        }

    return run


def arch_executor() -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """Architect mock executor (非 LLM 占位语义; execution_kind=planning,
    Architect Agent 自动化 = Sprint 8)。产出 Design artifact (契约:
    architecture/api/database)。"""

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "artifact_type": "design",
            "artifact_id": DEMO_ARTIFACT_IDS["design"],
            "ref": "file:///docs/design.md",
            "metadata": dict(_DEMO_DESIGN_METADATA),
        }

    return run


def dev_executor(
    project_dir: str | Path,
    versions: list[dict[str, str]],
) -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """Developer mock executor (非 LLM 占位语义 — Developer 真实 LLM 能力由
    Sprint 6.5 证明; Demo 注入确定性版本轨迹, 供 Tester 真实确定性测试)。

    - 按调用轮次写版本文件 (Tester Loop 修复轨迹: 第 0 轮 buggy → 修复轮正确)
    - 产出 code artifact (契约: files/changes + project_dir 供 Tester 解析)
    - 初始 Development 阶段固定 id (A-DEMO-CODE, Artifact 链预定义);
      repair 轮次自动 id (防重复注册)
    """

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        idx = min(_state["round"], len(versions) - 1)
        _state["round"] += 1
        files = versions[idx]
        write_project_files(project_dir, files)
        result: dict[str, Any] = {
            "artifact_type": "code",
            "ref": "file:///src",
            "metadata": {
                "files": list(files),
                "changes": "demo impl (mock, 非 LLM)",
                "project_dir": str(Path(project_dir).resolve()),
            },
        }
        if getattr(stage, "name", "") == "Development":
            result["artifact_id"] = DEMO_ARTIFACT_IDS["code"]
        return result

    _state: dict[str, int] = {"round": 0}
    return run


def devops_executor() -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """DevOps (Release) mock executor (非 LLM 占位语义; execution_kind=
    planning, Release Agent 自动化 = Sprint 8)。产出 Release artifact
    (契约: version/notes/artifact_ref)。"""

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "artifact_type": "release",
            "artifact_id": DEMO_ARTIFACT_IDS["release"],
            "ref": "file:///dist/demo-1.0.0.tar.gz",
            "metadata": dict(_DEMO_RELEASE_METADATA),
        }

    return run


# ------------------------------------------------------------------ 组合适配

def make_tester_executor(
    tester_executor_fn: Callable[[Any, dict[str, Any]], dict[str, Any]],
) -> Callable[[Any, dict[str, Any]], dict[str, Any]]:
    """Tester executor 组合适配 (包装 exec.tester.build_tester_executor)。

    - 初始 Testing 阶段: test 产物固定 id = A-DEMO-TEST (Artifact 链预定义
      引用, release 输入指向它 — 链结构: Testing 输出 → Release 输入)
    - retest/repair 轮次: 不动产物 id (自动生成, 防重复注册 DuplicateError)
    - 不重写 TesterAgent (只组合注入点)
    """

    def run(stage: Any, context: dict[str, Any]) -> dict[str, Any]:
        result = tester_executor_fn(stage, context)
        if stage.name == "Testing":
            for spec in result.get("artifacts", []):
                if isinstance(spec, dict) and spec.get("type") == "test":
                    spec["id"] = DEMO_ARTIFACT_IDS["test"]
        return result

    return run


def write_project_files(project_dir: str | Path, files: dict[str, str]) -> None:
    """写项目文件 (确定性; purge __pycache__ — pytest 子进程会复用同尺寸+
    同秒 mtime 的陈旧字节码, 不 purge 则轮次间读到旧模块, S7-004 已见陷阱)。"""
    base = Path(project_dir)
    base.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (base / name).write_text(content, encoding="utf-8")
    shutil.rmtree(base / "__pycache__", ignore_errors=True)

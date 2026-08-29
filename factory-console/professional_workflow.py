"""factory-console/professional_workflow.py — S10 Professional Workflow Assembly.

PM → Architect → Developer → QA 专业 AI 员工生产线。

- 预置 4 个专业 Agent (AgentEntity): product_manager / software_architect /
  software_developer / qa_engineer
- Professional Workflow: software-product-production (AgentRun 串行 + Handoff)
- LLM Decision Layer: agent executor 用 system_prompt + input_artifacts
  → llm_gateway.complete → 文本 → Artifact (LLM 输出 ≠ 事实, 经 Verification)
- 每 Agent 专业验收标准: PRD 段存在 / architecture 段存在 / code 语法 / pytest

核心原则 (S10):
- Agent 间只通过 Handoff (Artifact references, 无 hidden state)
- AgentRun 经 Production Kernel (复用 S1-S9, 不重造)
- LLM 输出必须经 Verification 才能成为生产 Artifact
"""
from __future__ import annotations

import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .session.agent_entity import AgentEntity
from .session.agent_registry import AgentRegistry
from .agent_kernel import (
    create_agent_run, run_agent, get_agent_run, create_handoff, AgentKernelError,
)
from .artifact_lifecycle import create_artifact

#: 专业 workflow id
PROFESSIONAL_WORKFLOW_ID = "software-product-production"

#: 4 专业 Agent 定义 (role → {name, prompt, skills})
PROFESSIONAL_ROLES: dict[str, dict[str, Any]] = {
    "product_manager": {
        "name": "产品经理",
        "system_prompt": (
            "你是资深产品经理。根据产品想法, 输出结构化 PRD (markdown):\n"
            "# 产品需求文档\n"
            "## Problem\n## Target Users\n## Goals\n## Functional Requirements\n"
            "## Non-Functional Requirements\n## Acceptance Criteria\n## Constraints\n"
            "必须包含所有章节, 每章节非空。"
        ),
        "skills": ["prd_writing"],
    },
    "software_architect": {
        "name": "软件架构师",
        "system_prompt": (
            "你是资深软件架构师。基于 PRD, 输出架构设计文档 (markdown):\n"
            "# 架构设计文档\n"
            "## System Architecture\n## Components\n## Interfaces\n## Data Model\n"
            "## Dependencies\n## Technology Decisions\n## Deployment\n## Engineering Constraints\n"
            "必须包含所有章节。"
        ),
        "skills": ["architecture_design"],
    },
    "software_developer": {
        "name": "软件开发者",
        "system_prompt": (
            "你是资深 Python 开发者。基于架构设计, 编写可运行代码。"
            "输出完整可运行的 Python 代码。"
        ),
        "skills": ["python_code_generation"],
    },
    "qa_engineer": {
        "name": "QA 工程师",
        "system_prompt": (
            "你是资深 QA 工程师。基于代码, 编写 pytest 测试。"
            "输出完整可运行的 pytest 测试代码。"
        ),
        "skills": ["pytest_execution"],
    },
    # S16: 扩展角色
    "market_analyst": {
        "name": "市场分析师",
        "system_prompt": "你是市场分析师。分析市场/竞品/用户需求, 输出市场分析文档。",
        "skills": ["market_research", "competitive_analysis"],
    },
    "ux_designer": {
        "name": "UX 设计师",
        "system_prompt": "你是 UX 设计师。基于 PRD 设计用户体验和界面结构, 输出设计文档。",
        "skills": ["design_ux"],
    },
    "release_engineer": {
        "name": "发布工程师",
        "system_prompt": "你是发布工程师。执行发布准备和发布验证, 不得绕过必要验证。",
        "skills": ["release_prepare", "release_verify"],
    },
}

#: 每 Agent 的 artifact 文件名 (由 executor 产出 → Artifact)
ROLE_TARGETS: dict[str, str] = {
    "product_manager": "prd.md",
    "software_architect": "architecture.md",
    "software_developer": "app.py",
    "qa_engineer": "test_app.py",
    # S16: 扩展角色
    "market_analyst": "market_analysis.md",
    "ux_designer": "ux_design.md",
    "release_engineer": "release_notes.md",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _reg(root: Path | str) -> AgentRegistry:
    return AgentRegistry(agents_file=Path(root) / "agents" / "factory_agents.json")


# ------------------------------------------------------------------ 预置 4 专业 Agent

def ensure_professional_agents(root: Path | str) -> list[AgentEntity]:
    """预置 4 个专业 Agent (幂等: 已存在则跳过)。"""
    reg = _reg(root)
    created = []
    for i, (role, cfg) in enumerate(PROFESSIONAL_ROLES.items(), start=1):
        aid = f"agt-it-{role}-1"
        if reg.get(aid) is None:
            agent = AgentEntity(id=aid, role=role, industry="it",
                                system_prompt=cfg["system_prompt"], skills=cfg["skills"])
            reg.add(agent)
            created.append(agent)
    return created


def list_professional_agents(root: Path | str) -> list[dict[str, Any]]:
    return [a.to_dict() for a in _reg(root).list()]


# ------------------------------------------------------------------ LLM Decision executor

def build_llm_executor_factory(root: Path | str):
    """专业 Agent 的 executor factory: system_prompt + input_artifacts → LLM → 文本。

    每 Agent 的 executor 契约 (与 Node 兼容):
      execute(input) → {ok, output, patch_text, error, artifact_type, verification}
    产出内容写入 target 文件 → 生成新文件 patch → Artifact。
    """
    from .workflow_runner import load_llm_key, has_llm_key
    from .config import get_config
    from .session.llm_gateway import complete as _llm_complete

    def _factory(agent_id: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        # agent_id 是 role (executor_name=node)
        role = agent_id.split("-")[-2] if "-" in agent_id else agent_id
        cfg = PROFESSIONAL_ROLES.get(role)
        system_prompt = cfg["system_prompt"] if cfg else "你是一个专业员工。"
        target = ROLE_TARGETS.get(role, f"{role}.md")

        def _fn(input_data: dict[str, Any]) -> dict[str, Any]:
            if not has_llm_key():
                return {"ok": False, "error": "LLM key 缺失", "artifact_type": "report",
                        "verification": {"result": "FAIL", "error": "no llm key"}}
            llm = get_config().get_llm()
            provider = str(llm.get("provider") or "deepseek")
            model = str(llm.get("model") or "deepseek-chat")
            api_key = load_llm_key()
            # 组装 messages: system_prompt + 输入 (显式来自 input_artifacts 内容)
            user_msg = f"产品想法: {input_data.get('idea') or input_data.get('prompt') or ''}\n"
            for key, val in (input_data.get("context") or {}).items():
                user_msg += f"\n[{key}]:\n{str(val)[:2000]}\n"
            try:
                resp = _llm_complete(
                    [{"role": "system", "content": system_prompt},
                     {"role": "user", "content": user_msg}],
                    None, provider_id=provider, model=model, api_key=api_key,
                    temperature=0.2, timeout=90,
                )
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "error": f"LLM 失败: {exc}", "artifact_type": "report",
                        "verification": {"result": "FAIL", "error": str(exc)[:200]}}
            content = (resp.get("content") or "").strip()
            if not content:
                return {"ok": False, "error": "LLM 空输出", "artifact_type": "report",
                        "verification": {"result": "FAIL", "error": "empty"}}
            # 生成新文件 patch (target 文件 = LLM 输出)
            import subprocess
            import tempfile

            with tempfile.TemporaryDirectory() as td:
                repo = Path(td)
                f = repo / target
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(content + "\n", encoding="utf-8")
                for c in (["init", "-q"], ["add", "-A"]):
                    subprocess.run(["git", "-C", str(repo), *c], capture_output=True, text=True, timeout=30)
                proc = subprocess.run(["git", "-C", str(repo), "diff", "--cached", "--no-color", "--", target],
                                      capture_output=True, text=True, timeout=30)
                patch = proc.stdout or ""
                if not patch:
                    subprocess.run(["git", "-C", str(repo), "-c", "user.email=f@l", "-c", "user.name=f",
                                    "commit", "-q", "-m", "base"], capture_output=True, text=True, timeout=30)
                    subprocess.run(["git", "-C", str(repo), "rm", "-q", "--cached", target],
                                   capture_output=True, text=True, timeout=30)
                    proc2 = subprocess.run(["git", "-C", str(repo), "diff", "--no-color", "--", target],
                                           capture_output=True, text=True, timeout=30)
                    patch = proc2.stdout or ""
            # 专业验收标准 (LLM 输出 ≠ 事实, 必须验证)
            verification = _verify_role_output(role, content)
            return {"ok": verification["result"] == "PASS",
                    "output": {"role": role, "content_tail": content[-500:]},
                    "patch_text": patch, "error": verification.get("error") or "",
                    "artifact_type": "document" if role in ("product_manager", "software_architect") else "code_change",
                    "verification": verification,
                    "content": content}

        return _fn

    return _factory


def _verify_role_output(role: str, content: str) -> dict[str, Any]:
    """每 Agent 专业验收标准 (真实验证, 非 LLM 自评)。

    章节标题宽松匹配 (大小写不敏感 + 中英文关键词) — LLM 输出格式可能漂移。
    """
    lowered = content.lower()

    def has_section(*keywords: str) -> bool:
        return any(k in lowered for k in keywords)

    if role == "product_manager":
        sections = [
            ("problem", "问题", "问题背景"),
            ("target users", "目标用户", "用户"),
            ("goals", "目标"),
            ("functional requirements", "功能需求", "功能要求"),
            ("acceptance criteria", "验收标准", "验收"),
        ]
        missing = [s[0] for s in sections if not has_section(*s)]
        return {"result": "PASS" if not missing else "FAIL",
                "error": f"缺章节: {missing}" if missing else "", "sections": [s[0] for s in sections]}
    if role == "software_architect":
        sections = [
            ("system architecture", "系统架构", "架构"),
            ("components", "组件"),
            ("interfaces", "接口", "界面"),
            ("data model", "数据模型", "数据"),
        ]
        missing = [s[0] for s in sections if not has_section(*s)]
        return {"result": "PASS" if not missing else "FAIL",
                "error": f"缺章节: {missing}" if missing else "", "sections": [s[0] for s in sections]}
    if role == "software_developer":
        # 语法验证 (真实 ast)
        try:
            compile(content, "<code>", "exec")
            return {"result": "PASS", "error": "", "checks": ["syntax"]}
        except SyntaxError as exc:
            return {"result": "FAIL", "error": f"语法错误: {exc}", "checks": ["syntax"]}
    if role == "qa_engineer":
        try:
            compile(content, "<test>", "exec")
            return {"result": "PASS", "error": "", "checks": ["syntax"]}
        except SyntaxError as exc:
            return {"result": "FAIL", "error": f"语法错误: {exc}", "checks": ["syntax"]}
    return {"result": "PASS", "error": "", "checks": []}


# ------------------------------------------------------------------ S12: Developer 自愈 (真实 pytest + 自动 Repair)

#: Developer 内置最小测试集 (验证 add/subtract/multiply/divide + 除零)
BUILTIN_CALC_TESTS = (
    "import app\n"
    "import pytest\n\n"
    "def test_add():\n    assert app.add(10, 20) == 30\n\n"
    "def test_subtract():\n    assert app.subtract(20, 5) == 15\n\n"
    "def test_multiply():\n    assert app.multiply(3, 4) == 12\n\n"
    "def test_divide():\n    assert app.divide(10, 2) == 5\n\n"
    "def test_divide_by_zero():\n    with pytest.raises(ValueError):\n        app.divide(1, 0)\n"
)


def build_developer_repair_fn(root: Path | str, *, idea: str, arch: str):
    """真实 Codex 修复: 接收 failed artifact + pytest failure evidence → 新代码。

    输入显式: failed_artifact + verification (pytest evidence), 无 hidden state。
    """
    from .workflow_runner import load_llm_key, has_llm_key
    from .config import get_config
    from .session.llm_gateway import complete as _llm_complete
    from .external_executor.registry import build_registry
    from .external_executor.executor import run as ext_run
    import re

    reg = build_registry(str(root))

    def _repair(failed_artifact: dict[str, Any], verification: dict[str, Any],
                ctx: dict[str, Any]) -> dict[str, Any]:
        adapter = reg.get("codex")
        if adapter is None:
            return {"ok": False, "error": "codex 不可用", "artifact_type": "report",
                    "verification": {"result": "FAIL", "error": "no codex"}}
        # 原始代码 (failed artifact payload)
        payload = failed_artifact.get("payload") or {}
        orig_code = payload.get("content") or ""
        # pytest 失败证据
        stdout = verification.get("stdout") or ""
        stderr = verification.get("stderr") or ""
        prompt = (
            f"以下 Python 计算器代码未通过 pytest。修复它使其通过全部测试。\n"
            f"要求: add/subtract/multiply/divide 函数, divide(1,0) 必须 raise ValueError。\n"
            f"只输出完整修正后的 Python 代码。\n"
            f"当前代码:\n{orig_code[:3000]}\n"
            f"pytest 输出:\n{(stdout + stderr)[:2000]}"
        )
        code = ""
        last_err = ""
        for attempt in range(2):
            r = ext_run(adapter, prompt, project_dir="", timeout=120)
            if r.get("exit_code") != 0:
                last_err = r.get("error", "")
                continue
            code = (r.get("output") or "").strip()
            m = re.search(r"```(?:python|py)?\s*\n(.*?)```", code, re.S)
            if m:
                code = m.group(1)
            else:
                lines = code.splitlines()
                start = 0
                for i, ln in enumerate(lines):
                    if ln.startswith("def ") or ln.startswith("import ") or ln.startswith("#!/"):
                        start = i
                        break
                code = "\n".join(lines[start:]) if start else code
            if "def add" not in code:
                last_err = "no add"
                continue
            try:
                compile(code, "<code>", "exec")
                break
            except SyntaxError as exc:
                last_err = f"syntax: {exc}"
        if "def add" not in code:
            return {"ok": False, "error": f"repair 失败: {last_err}", "artifact_type": "report",
                    "verification": {"result": "FAIL", "error": "repair no add"}}
        # repair 后真实 pytest (内置测试)
        ver = verify_code_with_pytest(code, BUILTIN_CALC_TESTS)
        return {"ok": ver["status"] == "PASS", "output": {"content": code},
                "patch_text": "", "error": ver.get("stderr", ""),
                "artifact_type": "code_change", "verification": ver, "content": code}

    return _repair


# ------------------------------------------------------------------ S11: 真实 pytest QA

def verify_code_with_pytest(
    code_content: str,
    test_content: str,
    *,
    code_filename: str = "app.py",
    test_filename: str = "test_app.py",
    timeout: int = 120,
) -> dict[str, Any]:
    """真实 pytest 验证: code + test 写临时目录 → subprocess pytest (S11)。

    返回: {verification_id, status, exit_code, stdout, stderr, command, duration_s, evidence}
    """
    import tempfile

    from .verification import verify_pytest

    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / code_filename).write_text(code_content + "\n", encoding="utf-8")
        (ws / test_filename).write_text(test_content + "\n", encoding="utf-8")
        result = verify_pytest(ws, timeout=timeout)
        result["code_filename"] = code_filename
        result["test_filename"] = test_filename
        return result


def build_real_executor_factory(root: Path | str):
    """真实执行 factory: PM/Arch → LLM, Developer → codex, QA → LLM+pytest。

    返回 executor_factory(agent_id) → fn(input) 与 Node 兼容。
    Developer 输出代码 content; QA 输出测试 content (输入含 code 上下文)。
    """
    from .workflow_runner import load_llm_key, has_llm_key
    from .config import get_config
    from .session.llm_gateway import complete as _llm_complete
    from .external_executor.registry import build_registry
    from .external_executor.executor import run as ext_run

    reg = build_registry(str(root))

    def _llm_call(system_prompt: str, user_msg: str) -> str:
        if not has_llm_key():
            raise RuntimeError("LLM key 缺失")
        llm = get_config().get_llm()
        provider = str(llm.get("provider") or "deepseek")
        model = str(llm.get("model") or "deepseek-chat")
        base_url = str(llm.get("base_url") or "")
        api_key = load_llm_key()
        resp = _llm_complete(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": user_msg}],
            None, provider_id=provider, model=model, base_url=base_url,
            api_key=api_key, temperature=0.2, timeout=120,
        )
        return (resp.get("content") or "").strip()

    def _factory(agent_id: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        role = agent_id.split("-")[-2] if "-" in agent_id else agent_id
        cfg = PROFESSIONAL_ROLES.get(role, {})

        def _fn(input_data: dict[str, Any]) -> dict[str, Any]:
            idea = str(input_data.get("idea") or "")
            context = input_data.get("context") or {}
            code_content = ""
            test_content = ""

            # PM: 真实 LLM → PRD
            if role == "product_manager":
                try:
                    content = _llm_call(cfg["system_prompt"], f"产品想法: {idea}")
                except Exception as exc:  # noqa: BLE001
                    return {"ok": False, "error": f"LLM 失败: {exc}", "artifact_type": "report",
                            "verification": {"result": "FAIL", "error": str(exc)[:200]}}
                ver = _verify_role_output(role, content)
                return {"ok": ver["result"] == "PASS", "output": {"content": content},
                        "patch_text": "", "error": ver.get("error") or "",
                        "artifact_type": "document", "verification": ver, "content": content}

            # Architect: 真实 LLM (输入只能来自 context = Handoff artifacts)
            if role == "software_architect":
                prd = str(next(iter(context.values()), "") or "")
                if not prd:
                    return {"ok": False, "error": "无 PRD 输入 (Handoff 必须传 PRD artifact)",
                            "artifact_type": "document",
                            "verification": {"result": "FAIL", "error": "no prd input"}}
                try:
                    content = _llm_call(cfg["system_prompt"], f"PRD:\n{prd[:3000]}")
                except Exception as exc:  # noqa: BLE001
                    return {"ok": False, "error": f"LLM 失败: {exc}", "artifact_type": "document",
                            "verification": {"result": "FAIL", "error": str(exc)[:200]}}
                ver = _verify_role_output(role, content)
                return {"ok": ver["result"] == "PASS", "output": {"content": content},
                        "patch_text": "", "error": ver.get("error") or "",
                        "artifact_type": "document", "verification": ver, "content": content}

            # Developer: 真实 Codex → 代码 (project_dir 用临时工作目录)
            if role == "software_developer":
                arch = str(next(iter(context.values()), "") or "")
                adapter = reg.get("codex")
                if adapter is None:
                    return {"ok": False, "error": "codex 不可用", "artifact_type": "report",
                            "verification": {"result": "FAIL", "error": "no codex"}}
                prompt = (
                    f"基于以下架构设计, 编写一个完整的 Python 计算器应用 (calculator.py):\n"
                    f"要求: 包含 add(a,b) 和 subtract(a,b) 函数。只输出 Python 代码。\n"
                    f"架构:\n{arch[:2000]}\n"
                    f"想法: {idea}"
                )
                code = ""
                last_err = ""
                for attempt in range(2):  # S11: codex 偶发杂质 → 重试一次 (非 mock)
                    r = ext_run(adapter, prompt, project_dir="", timeout=120)
                    if r.get("exit_code") != 0:
                        last_err = r.get("error", "")
                        continue
                    code = (r.get("output") or "").strip()
                    import re
                    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", code, re.S)
                    if m:
                        code = m.group(1)
                    else:
                        lines = code.splitlines()
                        start = 0
                        for i, ln in enumerate(lines):
                            if ln.startswith("def ") or ln.startswith("import ") or ln.startswith("#!/"):
                                start = i
                                break
                        code = "\n".join(lines[start:]) if start else code
                    if "def add" not in code:
                        last_err = "no add function"
                        continue
                    try:
                        compile(code, "<code>", "exec")
                        break  # 语法 PASS
                    except SyntaxError as exc:
                        last_err = f"syntax: {exc}"
                        continue
                if "def add" not in code:
                    return {"ok": False, "error": f"codex 未生成 add 函数 ({last_err})",
                            "artifact_type": "report",
                            "verification": {"result": "FAIL", "error": "no add function"}}
                try:
                    compile(code, "<code>", "exec")
                except SyntaxError as exc:
                    return {"ok": False, "error": f"语法错误: {exc}", "artifact_type": "report",
                            "verification": {"result": "FAIL", "error": f"syntax: {exc}"}}
                ver = _verify_role_output(role, code)
                # S12: Developer 生成后立即内置 pytest 验证 (真实 subprocess)
                pytest_ver = verify_code_with_pytest(code, BUILTIN_CALC_TESTS)
                if pytest_ver["status"] != "PASS":
                    return {"ok": False, "error": f"内置 pytest 失败: {pytest_ver.get('stderr', '')[:200]}",
                            "artifact_type": "code_change",
                            "verification": pytest_ver, "content": code}
                return {"ok": ver["result"] == "PASS", "output": {"content": code},
                        "patch_text": "", "error": ver.get("error") or "",
                        "artifact_type": "code_change", "verification": ver, "content": code}

            # QA: 真实 LLM → 测试 + 真实 pytest (输入含 code 上下文)
            if role == "qa_engineer":
                code_content = str(next(iter(context.values()), "") or "")
                if not code_content or "def add" not in code_content:
                    return {"ok": False, "error": "无代码输入 (Handoff 必须传 code artifact)",
                            "artifact_type": "report",
                            "verification": {"result": "FAIL", "error": "no code input"}}
                try:
                    test_content = _llm_call(
                        cfg["system_prompt"],
                        f"为以下 Python 代码编写 pytest 测试 (覆盖 add 和 subtract)。"
                        f"代码文件名是 app.py, 所以必须用 `import app` 或 `from app import add, subtract`。"
                        f"不要用占位符, 不要写 'your_module'。\n代码:\n{code_content[:3000]}"
                    )
                    import re
                    m = re.search(r"```(?:python)?\s*\n(.*?)```", test_content, re.S)
                    if m:
                        test_content = m.group(1)
                except Exception as exc:  # noqa: BLE001
                    return {"ok": False, "error": f"LLM 失败: {exc}", "artifact_type": "report",
                            "verification": {"result": "FAIL", "error": str(exc)[:200]}}
                # 真实 pytest (code + test 写临时目录)
                pytest_result = verify_code_with_pytest(code_content, test_content)
                status = pytest_result["status"]
                return {"ok": status == "PASS",
                        "output": {"content": test_content, "pytest": pytest_result},
                        "patch_text": "", "error": pytest_result.get("stderr") or "",
                        "artifact_type": "test", "verification": pytest_result,
                        "content": test_content}

            # S16: 通用文档角色 (market_analyst/ux_designer/release_engineer)
            if role in ("market_analyst", "ux_designer", "release_engineer"):
                try:
                    content = _llm_call(
                        cfg["system_prompt"],
                        f"任务背景: {idea[:2000]}\n"
                        f"上下文:\n{str(next(iter(context.values()), '') or '')[:2000]}\n"
                        f"请输出 {role} 专业文档 (markdown, 含必要章节)。"
                    )
                except Exception as exc:  # noqa: BLE001
                    return {"ok": False, "error": f"LLM 失败: {exc}", "artifact_type": "report",
                            "verification": {"result": "FAIL", "error": str(exc)[:200]}}
                ver = {"result": "PASS" if len(content) > 50 else "FAIL",
                       "error": "" if len(content) > 50 else "内容过短"}
                return {"ok": ver["result"] == "PASS", "output": {"content": content},
                        "patch_text": "", "error": ver.get("error") or "",
                        "artifact_type": "document", "verification": ver, "content": content}

            return {"ok": False, "error": f"未知角色: {role}", "artifact_type": "report",
                    "verification": {"result": "FAIL", "error": "unknown role"}}

        return _fn

    return _factory


# ------------------------------------------------------------------ 真实全链 E2E 入口

def run_real_workforce_e2e(
    root: Path | str,
    *,
    idea: str,
    max_repair: int = 2,
) -> dict[str, Any]:
    """真实 LLM + Codex + pytest 全链 E2E (S11)。

    PM → (LLM) PRD → Architect → (LLM) Architecture → Developer → (Codex) Code
    → QA → (LLM test + real pytest) → PASS/FAIL → 必要时 Repair → Apply 准备。
    """
    import shutil

    result = run_professional_workflow(
        root, idea=idea,
        executor_factory=build_real_executor_factory(root),
    )
    # 标记执行引擎
    result["engines"] = {"pm": "real-llm", "architect": "real-llm",
                         "developer": "real-codex", "qa": "real-llm+pytest"}
    return result


# ------------------------------------------------------------------ Professional Workflow 编排

def run_professional_workflow(
    root: Path | str,
    *,
    idea: str,
    executor_factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]] | None = None,
    max_repair: int = 1,
    experience_guidance: bool = False,
    guidance_limit: int = 3,
    record_usage: bool = True,
) -> dict[str, Any]:
    """执行完整专业生产线: PM → Architect → Developer → QA (AgentRun 串行 + Handoff)。

    每 Agent 独立 AgentRun → ProductionRun → Artifact → Verification。
    Agent 间只通过 Handoff (Artifact references)。
    max_repair: Developer 的自动修复次数 (S12: pytest FAIL → 自动 repair)。
    experience_guidance: S15 — 检索相关 Experience 注入 Agent context (Guidance, 非指令)。
    record_usage: S15 — 记录 experience usage + decision (双向 lineage)。
    """
    ensure_professional_agents(root)
    factory = executor_factory or build_llm_executor_factory(root)
    steps = ["product_manager", "software_architect", "software_developer", "qa_engineer"]
    agent_ids = {role: f"agt-it-{role}-1" for role in steps}
    runs: dict[str, dict[str, Any]] = {}
    handoffs: list[dict[str, Any]] = []
    input_artifacts: list[str] = []

    for i, role in enumerate(steps):
        aid = agent_ids[role]
        # 创建 AgentRun (输入 = 前序 Handoff artifacts 或 idea)
        arun = create_agent_run(root, aid, trigger="workflow",
                                input_artifacts=input_artifacts,
                                context_refs={"idea": idea})
        # 执行 (经 Production Kernel, executor 是专业 LLM executor)
        # 注意: execute 按 node_id 路由 (workflow node="work") → 用闭包固定 role
        role_factory = _bind_role(factory, role)
        # S15: Experience Guidance 注入 (Guidance, 非指令 — Agent 可 ACCEPT/REJECT)
        guidance = []
        if experience_guidance:
            from .production_guidance import retrieve_guidance
            guidance = retrieve_guidance(root, role, idea, limit=guidance_limit)
        # S12: Developer 启用自动修复 (pytest FAIL → 真实 codex repair)
        repair_fn = None
        rmax = 1
        if role == "software_developer" and max_repair > 0:
            arch_ctx = _load_artifact_contexts(root, input_artifacts)
            arch = str(next(iter(arch_ctx.values()), "") or "")
            repair_fn = build_developer_repair_fn(root, idea=idea, arch=arch)
            rmax = max_repair + 1  # 首次 + max_repair 次修复
        wf_input = {"idea": idea,
                    "context": _load_artifact_contexts(root, input_artifacts),
                    "target_file": ROLE_TARGETS.get(role, "out.md")}
        if guidance:
            wf_input["experience_guidance"] = guidance
        done = run_agent(root, arun["agent_run_id"], workflow_id=f"wf-{role}",
                         executor_factory=role_factory,
                         workflow_input=wf_input,
                         max_attempts=rmax, repair_fn=repair_fn)
        # S15: 记录 usage + decision (双向 lineage)
        if record_usage and guidance:
            from .production_guidance import record_usage as _record_usage, record_decision
            for g in guidance:
                exp_id = g.get("experience_id")
                if not exp_id:
                    continue
                # 模拟 Agent 决策 (确定性: 高 relevance → accept; 低 → partial)
                decision = "accept" if g.get("relevance", 0) >= 60 else "partial_apply"
                dec = record_decision(root, agent_run_id=arun["agent_run_id"],
                                      production_run_id=done.get("production_run_id") or "",
                                      experience_ids=[exp_id], decision=decision,
                                      reason=f"relevance={g.get('relevance')} (role/task match)")
                _record_usage(root, production_run_id=done.get("production_run_id") or "",
                              experience_id=exp_id, agent_run_id=arun["agent_run_id"],
                              relevance=int(g.get("relevance", 0)),
                              applied=done["state"] == "COMPLETED",
                              decision_id=dec["decision_id"])
        runs[role] = done
        if done["state"] != "COMPLETED":
            return {"workflow_id": PROFESSIONAL_WORKFLOW_ID, "idea": idea,
                    "runs": runs, "handoffs": handoffs, "state": "FAILED",
                    "failure": f"{role} FAILED: {done.get('failure')}",
                    "current_step": role}
        # Handoff: 本 Agent 输出 → 下一 Agent
        output_arts = done.get("output_artifacts", [])
        if output_arts and i < len(steps) - 1:
            h = create_handoff(root, from_agent_run_id=done["agent_run_id"],
                               to_agent_id=agent_ids[steps[i + 1]],
                               input_artifacts=output_arts)
            handoffs.append(h)
            input_artifacts = output_arts

    return {"workflow_id": PROFESSIONAL_WORKFLOW_ID, "idea": idea,
            "runs": runs, "handoffs": handoffs, "state": "COMPLETED",
            "final_artifacts": input_artifacts}


def _bind_role(factory: Callable[[str], Callable[[dict[str, Any]], dict[str, Any]]], role: str):
    """固定 executor 的 role (execute 按 node_id 路由, 忽略 node_id 直接用 role)。"""
    def _f(_node_id: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
        return factory(f"agt-it-{role}-1")
    return _f


def _load_artifact_contexts(root: Path | str, artifact_ids: list[str]) -> dict[str, str]:
    """从 Artifact 加载输入内容 (只通过 artifact refs, 无 hidden state)。"""
    from .artifact_lifecycle import get_artifact

    ctx: dict[str, str] = {}
    for aid in artifact_ids:
        art = get_artifact(root, aid)
        if art:
            payload = art.get("payload") or {}
            content = ""
            if isinstance(payload, dict):
                content = payload.get("content_tail") or payload.get("content") or ""
            elif isinstance(payload, str):
                content = payload
            ctx[aid] = content
    return ctx

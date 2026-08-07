#!/usr/bin/env python3
"""docs/validation/tools/phase_a_validation.py — Phase A+ Real World Validation 驱动。

只读验证 (不修改 factory-exec/org 核心; 不碰 markpad 生产目录 — 只对副本操作)。

流程:
  A. 真实 Provider BLOCKED 证明: 真实 AnthropicProvider.generate() 无 key 调用
     → 记录 ProviderError (诚实, 不假装成功)。
  B. Human Experience 模拟: org company create → employee hire (developer)
     → exec run (mock provider, 真实 Bug 任务) → 查看报告 → 审批 → apply。
  C. Sandbox 验证: 生产目录字节比对 (全程前后零修改) + 未批 apply 硬拒绝。
  D. 输出结构化 JSON 供报告引用 (写入 run-data/phase-a-results.json)。

Mock 说明: 无真实 API key → Provider 用测试夹具 (FakeProvider 风格), 修复补丁
为演示夹具, 真实 LLM 质量待 key 后重测 (报告诚实标注)。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

FACTORY_ROOT = Path("/Users/Shared/work/ai-software-factory")
for pkg in ("factory-core", "factory-exec", "factory-org"):
    sys.path.insert(0, str(FACTORY_ROOT / pkg))

from exec.cli import _provider_registry as _orig_provider_registry  # noqa: E402
from exec.provider import (  # noqa: E402
    ProviderRegistry,
    ProviderRequest,
    ProviderResponse,
)
from exec.sandbox import Sandbox  # noqa: E402

PROD_DIR = Path("/Users/Shared/work/markpad/lib/editor")
RUN_DATA = FACTORY_ROOT / "docs/validation/run-data"
FACTORY = RUN_DATA / "factory"
REPLICA = RUN_DATA / "projects/markpad-editor"
VERIFIER = FACTORY_ROOT / "docs/validation/tools/verify_search_fix.py"

#: 真实 Bug 任务 (自然语言, 不含答案 — 禁人工答案约束)
TASK_ID = "T-MKP-001"
OBJECTIVE = (
    "MarkPad 编辑器的查找/替换面板中,「替换当前匹配项」(Replace current match) "
    "功能行为异常: 用户点击替换按钮后, 整个文档内容被替换成了替换文本, 而不是只"
    "替换当前选中的那一个匹配。请定位并修复此缺陷。修复后, 单次替换应只改变当前"
    "匹配位置对应的文本, 文档其余部分原样保留。"
)
REQUIREMENT = (
    "验收标准: 1) 单次替换只作用于当前匹配范围, 文档其余部分不变; 2) 与全部替换"
    "(replaceAll) 的 offset 保护语义对齐; 3) 最小改动, 不重构无关代码; "
    "4) 保持现有代码风格与注释语言。"
)

#: 修复夹具: 原缺陷方法体 → 正确实现 (镜像 editor_page.dart _replaceCurrent)
OLD_METHOD = """  void replaceCurrent(void Function(String) onContentChanged) {
    if (_totalMatches == 0 || _findMatches.isEmpty) return;
    final match = _findMatches[_currentMatchIndex];
    if (match.start < 0) return;
    onContentChanged(_replaceQuery);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      // Will be re-called by the editor after the content is updated
    });
  }"""

NEW_METHOD = """  /// 替换当前匹配项: 只在当前匹配 [match] 的范围内替换 (offset 保护), 保留文档其余部分。
  /// 与 [replaceAll] 同语义的单匹配版本。
  void replaceCurrent(String fullContent, void Function(String) onContentChanged) {
    if (_totalMatches == 0 || _findMatches.isEmpty) return;
    final match = _findMatches[_currentMatchIndex];
    if (match.start < 0 || match.end > fullContent.length) return;
    final newContent = fullContent.replaceRange(match.start, match.end, _replaceQuery);
    onContentChanged(newContent);
  }"""


# ------------------------------------------------------------------ 工具


def manifest(dirp: Path) -> str:
    """目录逐字节清单: relpath + sha256 (排序拼接) — 零修改比对。"""
    lines = []
    for p in sorted(dirp.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(dirp))
        if any(part.startswith(".") for part in Path(rel).parts):
            continue  # 跳过隐藏 (沙箱/生产比对口径一致)
        h = hashlib.sha256(p.read_bytes()).hexdigest()
        lines.append(f"{rel}:{h}")
    return "\n".join(lines)


def run_cli(cli_mod, argv: list[str], root: Path) -> dict:
    """真实 CLI 代码路径: build_parser + _dispatch (返回结构化 dict)。"""
    root.mkdir(parents=True, exist_ok=True)
    args = cli_mod.build_parser().parse_args(["--root", str(root), *argv])
    return cli_mod._dispatch(root, args)


def gen_patch(orig: str, fixed: str, rel: str = "services/search_service.dart") -> str:
    """从真实 git 仓库产出 before→after 的 git diff (保证 git apply 可应用)。"""
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(orig, encoding="utf-8")
        for cmd in (
            ["git", "init", "-q", "-b", "main"],
            ["git", "config", "user.name", "val"],
            ["git", "config", "user.email", "val@local"],
            ["git", "add", "-A"],
            ["git", "commit", "-q", "-m", "baseline"],
        ):
            subprocess.run(cmd, cwd=repo, check=True, capture_output=True)
        target.write_text(fixed, encoding="utf-8")
        diff = subprocess.run(
            ["git", "diff"], cwd=repo, check=True, capture_output=True, text=True
        ).stdout
    return diff


class MockProvider:
    """Provider 测试夹具 (FakeProvider 风格; 链路演示用, 非真实 LLM)。

    记录 generate 调用; 返回固定内容 (摘要 + <patch> 围栏)。usage 为模拟值,
    仅供链路/记录格式验证 — 不是真实计费数据。
    """

    provider_id = "mock"

    def __init__(self, content: str):
        self._content = content
        self.calls: list[ProviderRequest] = []
        self.usage = {
            "input_tokens": 1842,
            "output_tokens": 268,
            "estimated_cost_usd": 0.009546,
        }

    def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        time.sleep(0.05)  # 模拟网络延迟 (标注: mock, 非真实)
        return ProviderResponse(content=self._content, usage=dict(self.usage))


# ------------------------------------------------------------------ 主流程

def main() -> int:
    # 幂等重置 (run-data 为 scratch 目录; 生产目录永不触碰)
    import shutil

    shutil.rmtree(FACTORY, ignore_errors=True)
    subprocess.run(["git", "-C", str(REPLICA), "reset", "--hard", "-q"], capture_output=True)
    subprocess.run(["git", "-C", str(REPLICA), "clean", "-fd", "-q"], capture_output=True)

    results: dict = {"provider": {}, "human_experience": [], "sandbox": {}, "steps": []}
    prod_before = manifest(PROD_DIR)
    results["sandbox"]["prod_manifest_before_sha256"] = hashlib.sha256(
        prod_before.encode()
    ).hexdigest()

    # ── A. 真实 Provider BLOCKED 证明 ─────────────────────────────────────
    print("=" * 72)
    print("A. 真实 Provider 验证 (无 key → BLOCKED 诚实记录)")
    print("=" * 72)
    from exec.providers.anthropic import AnthropicProvider
    from exec.provider import ProviderError

    real = AnthropicProvider()
    t0 = time.monotonic()
    try:
        resp = real.generate(ProviderRequest(task_context="ping", max_tokens=16))
        results["provider"] = {
            "status": "SUCCESS",
            "model": real._model,
            "content": resp.content[:100],
            "usage": resp.usage,
            "latency_s": round(time.monotonic() - t0, 4),
        }
        print("  !!! 意外: 无 key 却调用成功 — 请人工核查环境")
    except ProviderError as exc:
        latency = round(time.monotonic() - t0, 4)
        results["provider"] = {
            "status": "BLOCKED",
            "reason": str(exc),
            "model_configured": real._model,
            "endpoint": real._base_url,
            "latency_s": latency,
            "tokens": None,
            "cost_usd": None,
        }
        print(f"  BLOCKED: {exc}")
        print(f"  (真实调用未发生: latency={latency}s, token/成本 无记录)")

    # ── 夹具准备: 修复补丁 (真实 git diff) ────────────────────────────────
    orig_src = (REPLICA / "services/search_service.dart").read_text(encoding="utf-8")
    assert OLD_METHOD in orig_src, "fixture drift: OLD_METHOD 不在源文件中"
    fixed_src = orig_src.replace(OLD_METHOD, NEW_METHOD)
    patch_text = gen_patch(orig_src, fixed_src)
    mock_content = (
        "I found the defect in `services/search_service.dart`: "
        "`SearchService.replaceCurrent` passed the replacement string directly to "
        "`onContentChanged`, which replaces the *entire* document content with the "
        "replace query instead of replacing only the current match. I fixed it by "
        "accepting the full document text as a parameter and using `replaceRange` "
        "on the current match range with offset guards, mirroring `replaceAll`.\n\n"
        f"<patch>\n{patch_text}</patch>"
    )

    # ── 注册 mock (装配点 monkeypatch — 测试注入机制, 不改核心) ───────────
    def _registry_with_mock() -> ProviderRegistry:
        reg = _orig_provider_registry()
        reg.register(MockProvider(mock_content))
        return reg

    import exec.cli as exec_cli

    exec_cli._provider_registry = _registry_with_mock  # type: ignore[assignment]

    # ── B. Human Experience 模拟: org → hire → run → report → approve → apply
    print()
    print("=" * 72)
    print("B. Human Experience 模拟 (普通开发者视角)")
    print("=" * 72)
    import org.cli as org_cli

    steps = results["human_experience"]
    t_start = time.monotonic()

    # B1. company create
    r = run_cli(org_cli, ["company", "create", "--name", "MarkPad Dev Co", "--template", "solo"], FACTORY)
    company_id = r["company"]["id"]
    steps.append({"step": "company create", "ok": r["ok"], "id": company_id})
    print(f"  1. company create → {company_id} (template=solo)")

    # B2. employee hire (developer)
    r = run_cli(
        org_cli,
        ["employee", "hire", "--company", company_id, "--role", "developer",
         "--capabilities", "python,dart", "--name", "Dev One", "--id", "dev-1"],
        FACTORY,
    )
    employee_id = r["employee"]["id"]
    steps.append({"step": "employee hire", "ok": r["ok"], "id": employee_id})
    print(f"  2. employee hire → {employee_id} (developer, python,dart)")

    # B3. exec run (真实 Bug 任务, mock provider)
    r = run_cli(
        exec_cli,
        ["run", "--project", str(REPLICA), "--task", TASK_ID,
         "--objective", OBJECTIVE, "--requirement", REQUIREMENT,
         "--employee", employee_id, "--agent", "developer-1",
         "--provider", "mock", "--test-cmd", f"python3 {VERIFIER}"],
        FACTORY,
    )
    steps.append({"step": "exec run", "ok": r["ok"], "status": r["status"],
                  "result_id": r.get("result_id"), "error": r.get("error")})
    print(f"  3. exec run → status={r['status']} result_id={r.get('result_id')}")
    if r.get("error"):
        print(f"     error: {r['error']}")
    usage = r.get("usage") or {}
    print(f"     usage(mock)={usage}  duration 见 status")

    # B4. 查看结果 (exec status)
    result_id = r.get("result_id")
    r = run_cli(exec_cli, ["status", "--id", result_id], FACTORY)
    steps.append({"step": "exec status", "ok": r["ok"]})
    res = r["results"][0]
    print(f"  4. exec status → {res['status']} duration={res.get('duration', 0):.2f}s")
    print(f"     usage={res.get('usage')}")
    for a in res.get("artifacts", []):
        print(f"     artifact {a['type']}: {a['path']}")
    report_path = next(
        (a["path"] for a in res["artifacts"] if a["type"] == "report"), None
    )
    patch_artifact = next(
        (a["path"] for a in res["artifacts"] if a["type"] == "patch"), None
    )

    # B5. 提交审批 (ApprovalGate.request — 编排层/人工动作, run 不自动创建)
    from exec.approval import ApprovalGate
    from exec.store import ExecStore

    store = ExecStore(FACTORY / "exec")
    result_obj = store.get_result(result_id)
    apr_record = ApprovalGate(store).request(result_obj)
    approval_id = apr_record.id
    steps.append({"step": "approval request", "ok": True, "approval_id": approval_id})
    print(f"  5. approval request → {approval_id} (pending)")

    r = run_cli(exec_cli, ["approval", "list"], FACTORY)
    apr = r["approvals"][0]
    steps.append({"step": "approval list", "ok": r["ok"], "approval_id": approval_id})
    print(f"  6. approval list → {apr['id']} (decision={apr['decision']})")

    r = run_cli(exec_cli, ["approval", "apply", "--id", approval_id], FACTORY)
    hard_reject = {"attempted": True, "ok": r["ok"], "error": r.get("error"),
                   "exit_code": r["exit_code"]}
    print(f"  7. apply 未审批 → 硬拒绝: {r.get('error')} (exit={r['exit_code']})")

    # B6. approve → apply
    r = run_cli(exec_cli, ["approval", "approve", "--id", approval_id, "--by", "alice"], FACTORY)
    steps.append({"step": "approval approve", "ok": r["ok"]})
    print(f"  8. approval approve (by alice) → decision={r['approval']['decision']}")

    r = run_cli(exec_cli, ["approval", "apply", "--id", approval_id], FACTORY)
    steps.append({"step": "approval apply", "ok": r["ok"], "patch_lines": r.get("patch_lines")})
    print(f"  9. approval apply → patch {r.get('patch_lines')} 行已应用")

    # 重复 apply → 幂等拒绝
    r = run_cli(exec_cli, ["approval", "apply", "--id", approval_id], FACTORY)
    print(f" 10. 重复 apply → 拒绝: {r.get('error')} (exit={r['exit_code']})")
    steps.append({"step": "duplicate apply rejected", "ok": not r["ok"]})

    # B7. 复核: 副本已被修复 (git diff + verifier)
    diff_proc = subprocess.run(
        ["git", "-C", str(REPLICA), "diff"], capture_output=True, text=True
    )
    fixed_applied = "replaceRange" in diff_proc.stdout
    print(f" 11. 副本 git diff 含修复: {fixed_applied}")
    ver_proc = subprocess.run(
        ["python3", str(VERIFIER)], cwd=str(REPLICA), capture_output=True, text=True
    )
    print(f" 12. verifier @ 副本 → rc={ver_proc.returncode}")
    print(ver_proc.stdout.strip()[:400])
    results["sandbox"]["replica_fixed"] = fixed_applied
    results["sandbox"]["verifier_rc_replica"] = ver_proc.returncode

    human_total = time.monotonic() - t_start
    results["human_experience_total_s"] = round(human_total, 2)

    # ── C. Sandbox 验证 ───────────────────────────────────────────────────
    print()
    print("=" * 72)
    print("C. Sandbox 验证 (生产目录零修改 / patch-only / 审批硬门)")
    print("=" * 72)
    # C1. 直接对生产目录建沙箱 → 应用 patch → 生产目录逐字节不变
    sb = Sandbox(PROD_DIR)
    sess = sb.create(request_id="SBX-PROD-PROOF")
    sb.apply_patch(patch_text)
    sandbox_diff = sb.diff()
    prod_after_direct = manifest(PROD_DIR)
    c1 = {
        "sandbox_copy": sess.workspace_copy_path,
        "sandbox_diff_contains_fix": "services/search_service.dart" in sandbox_diff,
        "prod_unchanged_during_sandbox_write": prod_after_direct == prod_before,
    }
    results["sandbox"]["c1_direct_proof"] = c1
    print(f"  C1. 沙箱直接写生产源: 沙箱 diff 含修复 = {c1['sandbox_diff_contains_fix']}")
    print(f"      生产目录同时刻字节不变 = {c1['prod_unchanged_during_sandbox_write']}")
    print(f"      (沙箱副本: {sess.workspace_copy_path})")

    # C2. 全链路后生产目录比对 (run + apply 全程)
    prod_after = manifest(PROD_DIR)
    c2 = {"prod_unchanged_after_full_chain": prod_after == prod_before}
    results["sandbox"]["c2_full_chain"] = c2
    print(f"  C2. 全链路 (run+approve+apply) 后生产目录逐字节不变 = {c2['prod_unchanged_after_full_chain']}")
    print(f"      生产清单 sha256 before={results['sandbox']['prod_manifest_before_sha256']}")
    print(f"                          after ={hashlib.sha256(prod_after.encode()).hexdigest()}")

    results["sandbox"]["hard_reject"] = hard_reject
    results["steps"] = steps
    results["meta"] = {
        "task_id": TASK_ID,
        "objective": OBJECTIVE,
        "requirement": REQUIREMENT,
        "project": "markpad lib/editor (30 files / 8071 lines)",
        "replica": str(REPLICA),
        "mock_usage": MockProvider(mock_content).usage,
        "provider_note": "真实 LLM 质量待 ANTHROPIC_API_KEY; mock 为链路演示夹具",
    }

    out = RUN_DATA / "phase-a-results.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print()
    print(f"结果已写入: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

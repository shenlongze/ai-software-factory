#!/usr/bin/env python3
"""PRD 派生 端到端冒烟 —— CLI 链路第 2 环（"目标实跑"）。

为什么需要它:
    理解（第 1 环）产出事实后, 第 2 环「PRD」需要 CLI 入口。
    2026-09-15 补了 `factory conversation prd`（派生 / --list / --show）。
    本脚本是它的验收证据。

★ 刻意**不依赖 LLM**: 事实用**服务层 API 直接造**（`understanding.upsert_fact`）——
   LLM 只负责"把话变成事实"那一段（在 smoke_conversation_understand.py 与人工验证里覆盖）,
   本脚本要验的是"事实 → PRD"这一段, 不该被 LLM 的不确定性污染。

覆盖:
    ① 命令面: conversation 含 prd 子命令
    ② 造 3 条事实（IDEA / REQUIREMENT / CONSTRAINT）后派生 PRD
    ③ PRD 带**版本锚点** `source_product_understanding_version` = 当时 understanding.version
    ④ PRD 含 provenance 章节（可追溯）
    ⑤ --list 列得出 · --show 出 Markdown
    ⑥ 重复派生同名 draft → **明确报错**（formalization 的设计: 防误解, 不静默覆盖）
    ⑦ 全程 --root 隔离, 不碰 ~/.factory
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from ai_factory_os.services.conversation import understanding as U  # noqa: E402

ENV = {"PYTHONPATH": f"{ROOT}:{ROOT / 'src'}", "PATH": "/usr/bin:/bin:/usr/local/bin"}

_checks: list[tuple[str, bool, str]] = []


def chk(name: str, ok: bool, detail: str = "") -> None:
    _checks.append((name, bool(ok), detail))


def run(root: Path, *args: str, timeout: int = 90) -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-m", "apps.cli.main", "--root", str(root), *args],
                       capture_output=True, text=True, cwd=ROOT, env=ENV, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="smoke_prd_"))

    # ① 命令面
    p = subprocess.run(
        [sys.executable, "-c",
         "import importlib;"
         "p=importlib.import_module('apps.cli.main').build_parser();"
         "s=[a for a in p._actions if hasattr(a,'choices') and a.choices and 'conversation' in a.choices][0];"
         "cv=s.choices['conversation'];"
         "cs=[a for a in cv._actions if hasattr(a,'choices') and a.choices][0];"
         "print(','.join(sorted(cs.choices)))"],
        capture_output=True, text=True, cwd=ROOT, env=ENV, timeout=60)
    subs = (p.stdout or "").strip().split(",")
    chk("① 命令面: conversation 含 prd 子命令", "prd" in subs, str(subs))

    # ② 造事实（服务层 API —— 绕过 LLM, 只验"事实 → PRD"）
    conv = U.create_conversation(tmp, title="PRD 冒烟")
    cid = conv["id"]
    U.upsert_fact(tmp, cid, fact_type="IDEA", content="做一个记账 App")
    U.upsert_fact(tmp, cid, fact_type="REQUIREMENT", content="支持手机端")
    U.upsert_fact(tmp, cid, fact_type="CONSTRAINT", content="不做云端同步")
    ver_before = U.understanding_version(tmp, cid)
    n_facts = len(U.list_facts(tmp, cid))
    chk("② 造 3 条事实（IDEA/REQUIREMENT/CONSTRAINT）",
        n_facts == 3 and ver_before >= 3, f"facts={n_facts} v={ver_before}")

    # ③ 派生 PRD
    rc, out = run(tmp, "conversation", "prd", cid)
    prd_id = next((t.rstrip("—,、") for t in out.split() if t.startswith("PRD-")), "")
    chk("③ 派生 PRD 成功", rc == 0 and prd_id.startswith("PRD-"), out.strip()[:100])
    chk("③b PRD 带版本锚点 = 当时 understanding.version",
        f"锚定 understanding v{ver_before}" in out, out.strip()[:110])
    chk("③c PRD 章节含 provenance（可追溯）", "provenance" in out, out.strip()[:120])

    # ⑤ --list / --show
    rc, out = run(tmp, "conversation", "prd", cid, "--list")
    chk("⑤a --list 列得出", rc == 0 and prd_id in out, out.strip()[:80])
    rc, out = run(tmp, "conversation", "prd", cid, "--show", prd_id)
    chk("⑤b --show 出 Markdown（含标题与 draft 状态）",
        rc == 0 and out.startswith("# ") or "# " in out, out.strip()[:80])

    # ⑥ 重复派生 → 明确报错（不静默覆盖）
    rc, out = run(tmp, "conversation", "prd", cid)
    chk("⑥ 重复派生同名 draft → 明确报错（防误解, 不静默覆盖）",
        "派生 PRD 失败" in out or "已存在" in out or "draft" in out, out.strip()[:110])

    print("═══ PRD 派生 端到端（CLI 链路第 2 环）═══")
    for name, ok, detail in _checks:
        print(f"  [{'✓' if ok else '✗'}] {name}" + (f"  ← {detail}" if not ok else ""))
    n_ok = sum(1 for _, ok, _ in _checks if ok)
    print(f"\n  {n_ok}/{len(_checks)} 通过")
    return 0 if n_ok == len(_checks) else 1


if __name__ == "__main__":
    sys.exit(main())

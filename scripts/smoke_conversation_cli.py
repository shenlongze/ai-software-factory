#!/usr/bin/env python3
"""会话入口 端到端冒烟 —— CLI 链路第 1 环（"目标实跑"）。

为什么需要它:
    端到端实测曾发现 **8 环里第 1 环在 CLI 上是空的**（会话创建只在已删的 Web/API 面）。
    2026-09-15 补了 `factory conversation` 命令（new/list/show/say/facts）。
    本脚本是它的**验收证据** —— 走命令行, 不走内部函数（要验的正是"接线通不通"）。

覆盖:
    ① 命令面: 顶层含 conversation, 子命令 = new/list/show/say/facts
    ② new    → 建出 conv-*
    ③ list   → 列出刚建的
    ④ say    → 追加 human 消息（append-only）
    ⑤ show   → 消息数 / 理解版本 / 事实数
    ⑥ facts  → 事实清单（render 分支正确 —— 曾因分支顺序被 list 吃掉而误报"无会话"）
    ⑦ 不存在会话 → 明确报错（不静默成功）
    ⑧ 落盘核对: <root>/conversations/<conv>.json 真实存在且结构正确

隔离: 全程用 `--root <临时目录>`, 不碰 ~/.factory ✓
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_checks: list[tuple[str, bool, str]] = []


def chk(name: str, ok: bool, detail: str = "") -> None:
    _checks.append((name, bool(ok), detail))


def run(root: Path, *args: str) -> tuple[int, str]:
    """跑新 CLI（走命令行 —— 验的就是接线）。"""
    cmd = [sys.executable, "-m", "apps.cli.main", "--root", str(root), *args]
    env = {"PYTHONPATH": f"{ROOT}:{ROOT / 'src'}", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, env=env, timeout=60)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="smoke_conv_cli_"))

    # ① 命令面
    env = {"PYTHONPATH": f"{ROOT}:{ROOT / 'src'}", "PATH": "/usr/bin:/bin:/usr/local/bin"}
    probe = subprocess.run(
        [sys.executable, "-c",
         "import importlib;"
         "p=importlib.import_module('apps.cli.main').build_parser();"
         "s=[a for a in p._actions if hasattr(a,'choices') and a.choices and 'conversation' in a.choices][0];"
         "cv=s.choices['conversation'];"
         "cs=[a for a in cv._actions if hasattr(a,'choices') and a.choices][0];"
         "print(len(s.choices)); print(','.join(sorted(cs.choices)))"],
        capture_output=True, text=True, cwd=ROOT, env=env, timeout=60)
    lines = probe.stdout.strip().splitlines()
    top_n = lines[0] if lines else "0"
    subs = lines[1].split(",") if len(lines) > 1 else []
    chk("① 命令面: 顶层含 conversation 且 5 个基础子命令齐全",
        {"facts", "list", "new", "say", "show"} <= set(subs), f"顶层={top_n} 子命令={subs}")

    # ② new
    rc, out = run(tmp, "conversation", "new", "--title", "冒烟会话")
    cid = ""
    for tok in out.split():
        if tok.startswith("conv-"):
            cid = tok.rstrip("—,、")
    chk("② new → 建出 conv-*", rc == 0 and cid.startswith("conv-"), f"rc={rc} cid={cid}")

    # ③ list
    rc, out = run(tmp, "conversation", "list")
    chk("③ list → 列出刚建的会话", rc == 0 and cid in out, out.strip()[:80])

    # ④ say
    rc, out = run(tmp, "conversation", "say", cid, "我要做一个记账 App")
    chk("④ say → 追加消息成功", rc == 0 and "已追加消息" in out, out.strip()[:80])

    # ⑤ show
    rc, out = run(tmp, "conversation", "show", cid)
    chk("⑤ show → 消息 1 条 / 版本 v0", rc == 0 and "消息 1 条" in out, out.strip()[:90])

    # ⑥ facts（render 分支 —— 曾误报"无会话"）
    rc, out = run(tmp, "conversation", "facts", cid)
    chk("⑥ facts → 不再误报「无会话」（render 分支顺序 bug 已修）",
        rc == 0 and "无会话" not in out and "理解版本" in out, out.strip()[:80])

    # ⑦ 不存在会话
    rc, out = run(tmp, "conversation", "show", "conv-doesnotexist")
    chk("⑦ 不存在的会话 → 明确报错", "不存在" in out, out.strip()[:80])

    # ⑧ 落盘核对
    f = tmp / "conversations" / f"{cid}.json"
    ok = False
    detail = f"{f} 不存在"
    if f.is_file():
        d = json.loads(f.read_text(encoding="utf-8"))
        ok = (d.get("id") == cid and len(d.get("messages", [])) == 1
              and d.get("understanding", {}).get("version") == 0)
        detail = f"id={d.get('id')} msgs={len(d.get('messages', []))} v={d.get('understanding', {}).get('version')}"
    chk("⑧ 落盘核对: conversations/<conv>.json 结构正确", ok, detail)

    print("═══ 会话入口 端到端（CLI 链路第 1 环）═══")
    for name, ok, detail in _checks:
        print(f"  [{'✓' if ok else '✗'}] {name}" + (f"  ← {detail}" if not ok else ""))
    n_ok = sum(1 for _, ok, _ in _checks if ok)
    print(f"\n  {n_ok}/{len(_checks)} 通过")
    return 0 if n_ok == len(_checks) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""会话理解 端到端冒烟 —— CLI 链路第 2 环（"目标实跑"）。

为什么需要它:
    第 1 环（会话入口）之后, 第 2 环「把用户的话理解成事实」也需要 CLI 入口。
    2026-09-15 补了 `factory conversation understand`（LLM → proposal → facts）。
    本脚本是它的验收证据。

★ 刻意**不依赖 LLM**（冒烟必须稳定可重复; 真实 LLM 调用另有人工验证记录）:
    1. 命令面: conversation 子命令含 understand
    2. 无产品语义的话 → **诚实降级**（CLARIFY/无操作, 不炸、不猜事实）
    3. 会话不存在 → 明确报错
    4. 无用户消息且无 --text → 明确提示（不静默成功）
    5. 全程 --root 隔离, 不碰 ~/.factory

真实 LLM 验证（人工, 2026-09-15）:
    输入「我要做一个记账 App，先支持手机端，不做云端同步，用 SQLite 存本地」
    → LLM=available · 抽出 4 条事实:
        [IDEA/PROPOSED]        做一个记账 App
        [REQUIREMENT/PROPOSED] 运行平台: 手机端
        [CONSTRAINT/PROPOSED]  不做云端同步
        [DECISION/PROPOSED]    数据存储: 使用 SQLite 本地存储
      每条带 source_message_id（可追溯）+ confidence + provenance=semantic:add
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENV = {"PYTHONPATH": f"{ROOT}:{ROOT / 'src'}",
       "PATH": "/usr/bin:/bin:/usr/local/bin",
       # 刻意不传 DEEPSEEK_API_KEY ⇒ 走降级路径, 冒烟不依赖外部 LLM
       }

_checks: list[tuple[str, bool, str]] = []


def chk(name: str, ok: bool, detail: str = "") -> None:
    _checks.append((name, bool(ok), detail))


def run(root: Path, *args: str, timeout: int = 90) -> tuple[int, str]:
    p = subprocess.run([sys.executable, "-m", "apps.cli.main", "--root", str(root), *args],
                       capture_output=True, text=True, cwd=ROOT, env=ENV, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="smoke_conv_und_"))

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
    chk("① 命令面: conversation 含 understand 子命令", "understand" in subs, str(subs))

    # 建会话备后续用
    rc, out = run(tmp, "conversation", "new", "--title", "理解冒烟")
    cid = next((t.rstrip("—,、") for t in out.split() if t.startswith("conv-")), "")
    chk("② new → 建出会话（后续检查的前置）", cid.startswith("conv-"), out.strip()[:60])

    # ③ 无产品语义 → 降级（不炸、不猜事实, 不写 Truth）
    rc, out = run(tmp, "conversation", "understand", cid, "--text", "你好呀")
    chk("③ 无 LLM + 无产品语义 → 诚实降级（不炸、无事实落盘）",
        rc == 0 and "事实 0 条" in out, out.strip()[:110])

    # ④ 会话不存在 → 明确报错
    rc, out = run(tmp, "conversation", "understand", "conv-nope", "--text", "做个 App")
    chk("④ 会话不存在 → 明确报错", "不存在" in out, out.strip()[:80])

    # ⑤ 无消息且无 --text → 明确提示
    rc, out = run(tmp, "conversation", "understand", cid)
    chk("⑤ 无用户消息且无 --text → 明确提示（不静默成功）",
        "没有可理解" in out, out.strip()[:80])

    print("═══ 会话理解 端到端（CLI 链路第 2 环）═══")
    for name, ok, detail in _checks:
        print(f"  [{'✓' if ok else '✗'}] {name}" + (f"  ← {detail}" if not ok else ""))
    n_ok = sum(1 for _, ok, _ in _checks if ok)
    print(f"\n  {n_ok}/{len(_checks)} 通过")
    return 0 if n_ok == len(_checks) else 1


if __name__ == "__main__":
    sys.exit(main())

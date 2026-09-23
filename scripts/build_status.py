#!/usr/bin/env python
"""生成状态页 `apps/api/status.html` —— 给 `factory serve` 的 `/status` 用。

为什么是脚本而不是手写 HTML（Founder: "要留痕" ✓）:
  · 页面内容**全部来自真源**: `docs/TODO.md`（活清单）· `docs/WORKLOG.md`（追加式日志）·
    实时读数（版本 / 守卫数 / pytest 数 / 架构分类红 / 最近提交）
  · ⇒ 不可能出现"网页写 A、文档写 B"的漂移 ✗；重跑一次就同步 ✓

用法: `.venv/bin/python scripts/build_status.py`
"""
from __future__ import annotations

import html
import re
import subprocess as sp
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "apps" / "api" / "status.html"


def _run(cmd: list[str], timeout: int = 180) -> str:
    try:
        return sp.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout).stdout
    except (OSError, sp.SubprocessError):
        return ""


def _version() -> str:
    m = re.search(r'version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return m.group(1) if m else "?"


def _counts() -> dict[str, str]:
    guards = _run([".venv/bin/python", "scripts/smoke_chain_links.py"]).strip().splitlines()
    pytest_out = _run([".venv/bin/python", "-m", "pytest", "-q"])
    arch = _run([".venv/bin/python", "scripts/check_architecture.py"])
    cls = _run([".venv/bin/python", "scripts/check_classification.py"])

    def _summary(text: str) -> str:
        for ln in text.splitlines():
            if "汇总" in ln:
                return ln.strip()
        return "?"

    py = "?"
    for ln in pytest_out.splitlines():
        if "passed" in ln or "failed" in ln:
            py = ln.strip()
    return {
        "守卫": guards[-1].strip() if guards else "?",
        "pytest": py,
        "架构 R1–R17": _summary(arch),
        "分类 R18–R23": _summary(cls),
    }


def _recent(n: int = 15) -> list[str]:
    return [ln.strip() for ln in _run(["git", "log", f"-{n}", "--oneline"]).splitlines() if ln.strip()]


def _md_tables(text: str) -> str:
    """把 markdown 里的表格与标题转成 HTML（够用就好；不求全 ✓）。"""
    out: list[str] = []
    in_table = False
    for raw in text.splitlines():
        ln = raw.rstrip()
        if ln.startswith("|") and ln.endswith("|"):
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if set("".join(cells)) <= set("-: "):          # 分隔行
                continue
            tag = "th" if not in_table else "td"
            if not in_table:
                out.append("<table>")
                in_table = True
            out.append("<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if ln.startswith("#"):
            lvl = min(4, len(ln) - len(ln.lstrip("#")))
            out.append(f"<h{lvl}>{html.escape(ln.lstrip('# ').strip())}</h{lvl}>")
        elif ln.startswith("> "):
            out.append(f"<blockquote>{html.escape(ln[2:])}</blockquote>")
        elif ln.strip():
            out.append(f"<p>{html.escape(ln)}</p>")
    if in_table:
        out.append("</table>")
    return "\n".join(out)


def main() -> int:
    ver = _version()
    counts = _counts()
    todo = (ROOT / "docs" / "TODO.md").read_text(encoding="utf-8")
    log = (ROOT / "docs" / "WORKLOG.md").read_text(encoding="utf-8")
    recent = _recent()
    now = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M")

    page = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI Factory OS · 状态（v{html.escape(ver)}）</title>
<style>
  :root{{--bg:#f5f5f7;--card:#fff;--ink:#1d1d1f;--ink2:#6e6e73;--line:#d2d2d7;
        --brand:#0071e3;--ok:#34c759;--warn:#ff9f0a;--bad:#ff3b30;--r:18px}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:var(--bg);color:var(--ink);
       font:16px/1.55 -apple-system,BlinkMacSystemFont,"SF Pro SC","PingFang SC",Arial,sans-serif}}
  .wrap{{max-width:1100px;margin:0 auto;padding:28px 20px 60px}}
  h1{{font-size:28px;margin:0 0 4px}} h2{{font-size:20px;margin:32px 0 10px}}
  h3{{font-size:17px;margin:22px 0 8px}} h4{{font-size:15px;margin:16px 0 6px;color:var(--ink2)}}
  .sub{{color:var(--ink2);margin:0 0 18px}}
  .cards{{display:flex;flex-wrap:wrap;gap:12px;margin:14px 0 4px}}
  .card{{background:var(--card);border:1px solid var(--line);border-radius:var(--r);
        padding:14px 18px;min-width:190px;box-shadow:0 2px 14px rgba(0,0,0,.04)}}
  .card b{{display:block;font-size:13px;color:var(--ink2);font-weight:500;margin-bottom:4px}}
  .card span{{font-size:15px}}
  table{{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);
        border-radius:var(--r);overflow:hidden;margin:10px 0 4px;font-size:14px}}
  th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}}
  th{{background:#fafafa;font-weight:600}} tr:last-child td{{border-bottom:0}}
  blockquote{{margin:8px 0;padding:8px 14px;border-left:3px solid var(--brand);
             background:#fff;border-radius:8px;color:var(--ink2)}}
  code,pre{{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}}
  pre{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px 14px;overflow:auto}}
  .ok{{color:var(--ok)}} .warn{{color:var(--warn)}} .bad{{color:var(--bad)}}
  footer{{margin-top:34px;color:var(--ink2);font-size:13px}}
</style>
</head>
<body><div class="wrap">
  <h1>AI Factory OS · 状态</h1>
  <p class="sub">v{html.escape(ver)} · 生成于 {html.escape(now)} ·
     数据来自 <code>docs/TODO.md</code> + <code>docs/WORKLOG.md</code> + 实时读数 ⇒ 不可能与文档漂移 ✓</p>

  <div class="cards">
    {''.join(f'<div class="card"><b>{html.escape(k)}</b><span>{html.escape(v)}</span></div>' for k, v in counts.items())}
  </div>

  <h2>最近提交</h2>
  <pre>{html.escape(chr(10).join(recent))}</pre>

  <h2>活清单（TODO.md）</h2>
  {_md_tables(todo)}

  <h2>工作日志（WORKLOG.md，追加式）</h2>
  {_md_tables(log)}

  <footer>这一页由 <code>scripts/build_status.py</code> 生成；
    改完清单/日志后重跑一次即可同步 ✓</footer>
</div></body></html>
"""
    OUT.write_text(page, encoding="utf-8")
    print(f"  已生成 {OUT.relative_to(ROOT)}（{len(page)} 字节） 版本 v{ver}")
    for k, v in counts.items():
        print(f"    {k}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

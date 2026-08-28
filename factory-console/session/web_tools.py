"""factory-console/session/web_tools.py — 通用搜索/执行工具 (S8, v1.1.246).

一劳永逸: 不预置天气/股价/航班等专用工具 — 给会话"搜索 + 执行"两条腿,
任意一般问题先搜再做, 现场解决。工具使用阶梯: 本地优先, 网络兜底。

工具 (统一返回 {ok, output, error, need_approval, duration_ms}):
- web_search(query, max_results): DuckDuckGo HTML 免费搜索 (无 key)
- web_fetch(url, max_chars): HTTP GET 抓取 + 去 HTML 标签 + 大小限制
- bash_exec(command, timeout): 沙箱执行 — 黑名单硬拦截 + 写操作批准标记 + 超时 + 截断

安全: 危险命令模式 → 拒绝执行; 写/敏感操作 → need_approval=True (由调用方走批准门);
默认只读命令 (curl/python3/grep/cat/ls 等查询类) 直接执行。全程审计由 dispatch 层负责。
"""

from __future__ import annotations

import html as _html
import re
import shlex
import subprocess
import time
import urllib.parse
import urllib.request
from typing import Any

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
DEFAULT_TIMEOUT = 30          # bash 默认超时 (秒)
FETCH_TIMEOUT = 15            # web_fetch 超时 (秒)
FETCH_MAX_CHARS = 20_000      # web_fetch 内容上限
BASH_MAX_CHARS = 20_000       # bash 输出上限
SEARCH_MAX_RESULTS = 8        # 搜索默认条数
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

#: 危险命令模式 — 硬拦截, 不执行 (匹配即拒绝)
DANGEROUS_PATTERNS: list[str] = [
    r"\brm\s+-rf\s+[/~]\s*$",        # rm -rf / 或 ~
    r"\brm\s+-rf\s+/\*",             # rm -rf /*
    r"\bsudo\b",                     # sudo
    r"\bmkfs",                       # 格式化
    r"\bdd\s+if=",                   # dd 写盘
    r"\bshutdown\b", r"\breboot\b", r"\bpoweroff\b", r"\binit\s+0\b",
    r"chmod\s+777\s+/\s",            # 根目录放权
    r":\(\)\s*\{",                   # fork 炸弹
    r"curl\s+[^|]*\|\s*(ba)?sh",     # curl | sh
    r"wget\s+[^|]*\|\s*(ba)?sh",     # wget | sh
    r"\bkill\s+-9\s+(-1|0)\b",       # 杀所有进程
    r"\bformat\s+[a-zA-Z]:",
    r"rm\s+-rf\s+[a-zA-Z]:/",       # Windows 盘删除 (C:/ 等)
]

#: 写/敏感操作 — need_approval=True (不直接执行, 由调用方走批准门)
APPROVAL_PATTERNS: list[str] = [
    r">>", r">\s+[^&|]",             # 重定向写
    r"\bmv\b", r"\bcp\b", r"\brm\b", r"\bmkdir\b", r"\btouch\b",
    r"\bchmod\b", r"\bchown\b", r"\bkill\b", r"\bpkill\b",
    r"\bgit\s+(push|commit|add|rm|reset|checkout|merge|rebase|revert)",
    r"pip\s+install", r"npm\s+install", r"brew\s+install", r"apt\s+(install|remove)",
    r"\bsed\s+-i", r"\btruncate\b", r"\bdd\b", r"\btee\b", r"\bscp\b", r"\brsync\b",
    r"\bpython3?\s+(-m\s+)?pip", r"os\.remove", r"unlink\(", r"shutil\.rmtree",
]


def _match_any(command: str, patterns: list[str]) -> bool:
    try:
        return any(re.search(p, command, re.IGNORECASE) for p in patterns)
    except Exception:  # noqa: BLE001 — 正则坏 → 不误拦 (保守)
        return False


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


# ---------------------------------------------------------------------------
# web_search — DuckDuckGo HTML 免费搜索 (无 key)
# ---------------------------------------------------------------------------
def web_search(query: str, max_results: int = SEARCH_MAX_RESULTS) -> dict[str, Any]:
    """DuckDuckGo HTML 搜索 → [{title, url, snippet}]。失败 → 诚实错误。"""
    t0 = _now_ms()
    q = str(query or "").strip()
    if not q:
        return {"ok": False, "error": "查询词为空", "need_approval": False, "duration_ms": 0}
    try:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(q)
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"搜索失败: {exc}", "need_approval": False,
                "duration_ms": _now_ms() - t0}
    # 解析 DDG HTML: result__a (标题+链接), result__snippet (摘要)
    items: list[dict[str, str]] = []
    for m in re.finditer(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        raw, re.DOTALL,
    ):
        href = _html.unescape(m.group(1))
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        # DDG 重定向链接 → 提取真实 url (uddg= 参数)
        real = href
        um = re.search(r"[?&]uddg=([^&]+)", href)
        if um:
            real = urllib.parse.unquote(um.group(1))
        items.append({"title": _html.unescape(title)[:200], "url": real})
        if len(items) >= max_results:
            break
    # 摘要
    snips = re.findall(
        r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', raw, re.DOTALL)
    for i, sn in enumerate(snips[:max_results]):
        txt = re.sub(r"<[^>]+>", "", sn).strip()
        if i < len(items):
            items[i]["snippet"] = _html.unescape(txt)[:300]
    if not items:
        return {"ok": False, "error": "搜索无结果 (网络或反爬限制, 可换措辞重试)",
                "need_approval": False, "duration_ms": _now_ms() - t0}
    out = "\n\n".join(
        f"{i+1}. {it.get('title','')}\n   {it.get('url','')}\n   {it.get('snippet','')}"
        for i, it in enumerate(items)
    )
    return {"ok": True, "output": f"搜索『{q}』结果:\n{out}",
            "items": items, "need_approval": False, "duration_ms": _now_ms() - t0}


# ---------------------------------------------------------------------------
# web_fetch — HTTP GET + 去 HTML
# ---------------------------------------------------------------------------
def web_fetch(url: str, max_chars: int = FETCH_MAX_CHARS) -> dict[str, Any]:
    """抓取网页/接口 → 纯文本 (去标签)。支持 JSON/HTML/纯文本。"""
    t0 = _now_ms()
    u = str(url or "").strip()
    if not u.startswith(("http://", "https://")):
        return {"ok": False, "error": "URL 必须以 http(s):// 开头", "need_approval": False,
                "duration_ms": 0}
    try:
        req = urllib.request.Request(u, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"抓取失败: {exc}", "need_approval": False,
                "duration_ms": _now_ms() - t0}
    # 去 HTML 标签 + 压缩空白
    text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", raw, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n...(内容过长, 截断至 {max_chars} 字符)"
    if not text:
        return {"ok": False, "error": "页面无文本内容", "need_approval": False,
                "duration_ms": _now_ms() - t0}
    return {"ok": True, "output": text, "url": u, "need_approval": False,
            "duration_ms": _now_ms() - t0}


# ---------------------------------------------------------------------------
# bash_exec — 沙箱执行 (黑名单 + 批准标记 + 超时 + 截断)
# ---------------------------------------------------------------------------
def bash_exec(command: str, timeout: int = DEFAULT_TIMEOUT, force: bool = False) -> dict[str, Any]:
    """执行 shell 命令。危险命令 → 永远拒绝 (force 也不放行); 写/敏感 → need_approval
    (调用方走批准门; force=True 由批准门放行后跳过 approval 检查);
    只读查询类 (curl/python3/grep/cat/ls…) → 直接执行。"""
    t0 = _now_ms()
    cmd = str(command or "").strip()
    if not cmd:
        return {"ok": False, "error": "命令为空", "need_approval": False, "duration_ms": 0}
    try:
        to = max(1, min(int(timeout or DEFAULT_TIMEOUT), 120))
    except Exception:  # noqa: BLE001
        to = DEFAULT_TIMEOUT
    # 1) 危险命令硬拦截
    if _match_any(cmd, DANGEROUS_PATTERNS):
        return {"ok": False, "error": "危险命令被拦截 (含 rm -rf /、sudo、格式化、管道直执行等)",
                "need_approval": False, "duration_ms": _now_ms() - t0}
    # 2) 写/敏感操作 → 批准门 (force=True 表示已获用户批准, 放行)
    if _match_any(cmd, APPROVAL_PATTERNS) and not force:
        return {"ok": False, "error": (
            "该命令涉及写操作/敏感操作 (重定向/删改/安装/git push 等), 需要用户批准后执行。"
            f"命令: {cmd[:200]}"),
            "need_approval": True, "command": cmd[:2000], "duration_ms": _now_ms() - t0}
    # 3) 只读查询类 → 执行
    try:
        proc = subprocess.run(
            ["/bin/zsh", "-lc", cmd],
            capture_output=True, text=True, timeout=to,
            cwd=None,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"命令超时 (>{to}s), 已终止", "need_approval": False,
                "duration_ms": _now_ms() - t0}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"执行失败: {exc}", "need_approval": False,
                "duration_ms": _now_ms() - t0}
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr and proc.returncode != 0 else "")
    out = out.strip()
    if len(out) > BASH_MAX_CHARS:
        out = out[:BASH_MAX_CHARS] + f"\n...(输出过长, 截断至 {BASH_MAX_CHARS} 字符)"
    if proc.returncode != 0:
        return {"ok": False, "error": f"命令退出码 {proc.returncode}: {out[:2000]}",
                "output": out[:BASH_MAX_CHARS], "need_approval": False,
                "duration_ms": _now_ms() - t0}
    if not out:
        out = "命令执行成功, 无输出。"
    return {"ok": True, "output": out, "need_approval": False, "duration_ms": _now_ms() - t0}


__all__ = ["web_search", "web_fetch", "bash_exec",
           "DANGEROUS_PATTERNS", "APPROVAL_PATTERNS"]

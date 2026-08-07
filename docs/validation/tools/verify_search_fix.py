#!/usr/bin/env python3
"""docs/validation/tools/verify_search_fix.py — 沙箱验证脚本 (--test-cmd 用)。

在沙箱副本根目录 (cwd) 内校验 search_service.dart 的 replaceCurrent 修复是否
落在预期语义上 (纯 Python 静态检查, 零 Flutter 依赖 — 沙箱只有 lib/editor 副本,
无 pubspec 上下文, 无法跑 dart analyze; 此脚本是 Phase A+ demo 的测试命令):

期望修复语义 (镜像 editor_page.dart _replaceCurrent 的正确实现):
1. replaceCurrent 签名接收全文参数 (fullContent/display 语义), 不再只有
   onContentChanged 回调。
2. 方法体内对当前匹配范围做 replaceRange, 而非把整篇文档替换成替换词。
3. 不得再出现 `onContentChanged(_replaceQuery);` 直接把替换词当全文的调用。

退出码: 0 = 通过 (PASS), 1 = 未通过 (FAIL)。输出供 ExecutionReport 展示。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

TARGET = Path("services/search_service.dart")

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def main() -> int:
    if not TARGET.is_file():
        check("target file exists", False, f"missing {TARGET}")
        return 1
    src = TARGET.read_text(encoding="utf-8")

    # 1) 签名: replaceCurrent 必须接收全文参数 (处理嵌套括号: void Function(String))
    m = re.search(
        r"void\s+replaceCurrent\s*\(\s*((?:[^()]|\([^)]*\))*)\)\s*\{",
        src,
        re.DOTALL,
    )
    sig_ok = bool(m)
    if m:
        params = m.group(1)
        has_full = bool(
            re.search(r"\bfullContent\b", params)
            or re.search(r"\bdisplay\b", params)
        )
        has_cb = "onContentChanged" in params
        sig_ok = has_full and has_cb
        check(
            "replaceCurrent 签名含全文参数 + 回调",
            sig_ok,
            detail=f"params: {params.strip()[:120]}",
        )
    else:
        check("replaceCurrent 签名可解析", False)

    # 2) 方法体: 使用 replaceRange 对当前匹配做局部替换
    body_ok = "replaceRange" in src
    check("方法体使用 replaceRange (局部替换)", body_ok)

    # 3) 反模式: 不得把替换词整体作为新文档内容回调
    anti_ok = "onContentChanged(_replaceQuery)" not in src
    check(
        "不得整体替换文档 (onContentChanged(_replaceQuery) 反模式)",
        anti_ok,
        detail="残留整体替换调用" if not anti_ok else "",
    )

    # 4) 结果仍可被 parse (括号配平粗检)
    balance = src.count("(") - src.count(")")
    check("括号配平", balance == 0, detail=f"delta={balance}")

    passed = not FAILURES
    print("")
    print(f"RESULT: {'PASS' if passed else 'FAIL'} — replaceCurrent 修复语义 "
          f"{'已就位' if passed else '未就位'} ({len(FAILURES)} 项失败)")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())

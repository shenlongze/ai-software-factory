#!/usr/bin/env python3
"""scripts/coverage_report.py — F-10 测试覆盖度 (stdlib trace, 模块级报告; 零第三方依赖)。

用法:
    python scripts/coverage_report.py [--driver factory_console.session.eval_suite:run_smoke]
                                     [--output docs/eval/coverage-report.json] [--verbose]

行为:
- 用 stdlib trace.Trace(count=True, trace=False) 跑 driver (默认 eval_suite.run_smoke —
  覆盖 eval_suite 全部评测项代码路径)
- 按文件/包聚合: covered/total 可执行行 → 模块级覆盖率百分比
- **不设达标线, 只报** (如实呈现; 覆盖率低不伪造不拦截)
- 写 JSON 报告 (modules + packages + total) — C-4/人工查看用

边界:
- 不装 pytest-cov (禁新增依赖 — F-10 用 stdlib trace)
- trace 只统计 driver 实际执行到的代码 (import 即执行 → 导入面也计入)
- 失败安全: 单个文件解析失败 → 跳过, 不崩
"""

from __future__ import annotations

import argparse
import json
import linecache
import sys
import trace
from datetime import datetime, timezone
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _module_name(repo: Path, filename: str) -> str:
    """仓库相对路径 → 模块名 (factory-console/... → factory_console...)。"""
    try:
        rel = Path(filename).resolve().relative_to(repo.resolve())
    except ValueError:
        rel = Path(filename)
    name = str(rel).replace(".pyc", ".py").replace("\\", "/")
    if name.endswith(".py"):
        name = name[:-3]
    return name.replace("/", ".").replace("-", "_")


def _package_name(repo: Path, filename: str) -> str:
    """模块名 → 顶层包 (factory_console.session.eval_suite → factory_console)。"""
    return _module_name(repo, filename).split(".")[0]


def run_coverage(
    driver: str,
    *,
    repo: Path,
    ignoredirs: tuple[str, ...] = (),
) -> dict:
    """跑 driver 并返回模块级覆盖率报告 dict (确定性, 失败安全)。"""
    module_path, _, func_name = driver.partition(":")
    if not module_path or not func_name:
        raise ValueError(f"driver 格式应为 MODULE:FUNC, 收到: {driver!r}")
    import importlib

    mod = importlib.import_module(module_path)
    fn = getattr(mod, func_name)

    default_ignoredirs = (sys.prefix,)
    t = trace.Trace(
        count=True,
        trace=False,
        ignoredirs=tuple(dict.fromkeys(default_ignoredirs + ignoredirs)),
    )
    t.runfunc(fn)

    counts = t.results().counts  # {(filename, lineno): count}
    per_file: dict[str, dict[int, int]] = {}
    for (filename, lineno), count in counts.items():
        if filename.startswith("<") and filename.endswith(">"):
            continue
        per_file.setdefault(filename, {})[lineno] = count

    repo_root = repo.resolve()
    excluded_roots = {str(repo_root / ".venv"), str(repo_root / "build")}
    modules: list[dict] = []
    skipped_external = 0
    for filename, hits in sorted(per_file.items()):
        try:
            resolved = Path(filename).resolve()
        except Exception:  # noqa: BLE001 — 失败安全
            resolved = Path(filename)
        # 只统计仓库内模块 (外部/venv/build → 跳过, 不计入总量)
        if resolved != repo_root and repo_root not in resolved.parents:
            skipped_external += 1
            continue
        if any(str(resolved).startswith(root) for root in excluded_roots):
            skipped_external += 1
            continue
        try:
            executable = trace._find_executable_linenos(filename)  # noqa: SLF001 — stdlib 内部, 覆盖统计用
        except Exception:  # noqa: BLE001 — 失败安全: 单文件解析失败跳过
            continue
        if not isinstance(executable, dict):
            executable = {ln: 1 for ln in executable}
        covered = sum(1 for ln in executable if ln in hits)
        total = len(executable)
        percent = round(100.0 * covered / total, 2) if total else 0.0
        modules.append({
            "module": _module_name(repo, filename),
            "package": _package_name(repo, filename),
            "file": str(resolved),
            "covered_lines": covered,
            "executable_lines": total,
            "coverage_percent": percent,
        })

    modules.sort(key=lambda m: (-m["executable_lines"], m["module"]))
    # 包级聚合
    packages: dict[str, dict[str, float]] = {}
    for m in modules:
        p = packages.setdefault(m["package"], {"covered_lines": 0, "executable_lines": 0})
        p["covered_lines"] += m["covered_lines"]
        p["executable_lines"] += m["executable_lines"]
    package_rows = [
        {
            "package": name,
            "covered_lines": v["covered_lines"],
            "executable_lines": v["executable_lines"],
            "coverage_percent": round(100.0 * v["covered_lines"] / v["executable_lines"], 2)
            if v["executable_lines"] else 0.0,
        }
        for name, v in sorted(packages.items())
    ]
    total_covered = sum(m["covered_lines"] for m in modules)
    total_lines = sum(m["executable_lines"] for m in modules)
    return {
        "generated_at": _now_iso(),
        "driver": driver,
        "tool": "stdlib trace (F-10, 零第三方依赖)",
        "threshold": None,  # 不设达标线, 只报
        "modules": modules,
        "packages": package_rows,
        "skipped_external_files": skipped_external,
        "total": {
            "covered_lines": total_covered,
            "executable_lines": total_lines,
            "coverage_percent": round(100.0 * total_covered / total_lines, 2)
            if total_lines else 0.0,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="F-10 测试覆盖度 (stdlib trace, 模块级报告)")
    parser.add_argument(
        "--driver", default="factory_console.session.eval_suite:run_smoke",
        help="driver (MODULE:FUNC, 缺省 eval_suite.run_smoke)",
    )
    parser.add_argument("--output", default=None, help="报告落盘路径 (缺省打印到 stdout)")
    parser.add_argument("--verbose", action="store_true", help="打印模块明细")
    args = parser.parse_args(argv)
    try:
        report = run_coverage(args.driver, repo=_REPO)
    except Exception as exc:  # noqa: BLE001 — 失败安全
        print(f"[E5101] 错误: 覆盖度统计失败 — {exc}", file=sys.stderr)
        return 1
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"覆盖度报告已保存: {out}")
    if args.verbose:
        for m in report["modules"]:
            print(
                f"  {m['module']:<60} {m['coverage_percent']:6.2f}%  "
                f"({m['covered_lines']}/{m['executable_lines']})"
            )
    total = report["total"]
    print(
        f"F-10 覆盖度: {len(report['modules'])} 个模块 "
        f"{total['coverage_percent']}% ({total['covered_lines']}/{total['executable_lines']}) "
        f"— 不设达标线, 只报"
    )
    for p in report["packages"]:
        print(
            f"  包 {p['package']:<20} {p['coverage_percent']:6.2f}%  "
            f"({p['covered_lines']}/{p['executable_lines']})"
        )
    if not args.output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

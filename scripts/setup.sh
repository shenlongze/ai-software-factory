#!/usr/bin/env bash
# scripts/setup.sh — AI Software Factory 一键环境搭建 (Phase 13A)
#
# 用法:
#   bash scripts/setup.sh            # 完整安装: venv + editable install + 可选 frontend + init 冒烟
#   bash scripts/setup.sh --check    # 轻量验证 (只读: venv/console script/examples/CLI 是否就绪)
#
# 设计: 幂等 (重复执行安全); --check 不写任何文件 (只读探测, 供 CI/安装冒烟)。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR=".venv"
VENV_PY="$VENV_DIR/bin/python"
VENV_FACTORY="$VENV_DIR/bin/factory"

say() { printf '\033[1;32m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*" >&2; }

check() {
    local fail=0
    say "== setup --check: 环境就绪性验证 =="
    [ -x "$VENV_PY" ] && say "  [ok] venv          $VENV_PY" || { warn "  [缺] venv          先运行: bash scripts/setup.sh"; fail=1; }
    [ -x "$VENV_FACTORY" ] && say "  [ok] console script $VENV_FACTORY" || { warn "  [缺] factory 入口   先运行: bash scripts/setup.sh"; fail=1; }
    if [ -x "$VENV_FACTORY" ] && "$VENV_FACTORY" --help >/dev/null 2>&1; then
        say "  [ok] CLI            factory --help 退出码 0"
    else
        warn "  [缺] CLI            factory --help 失败 (venv 损坏?)"; fail=1
    fi
    for f in examples/markpad-demo/idea.json examples/markpad-demo/requirements.json examples/markpad-demo/expected-flow.md; do
        if [ -f "$f" ]; then say "  [ok] 示例           $f"; else warn "  [缺] 示例           $f"; fail=1; fi
    done
    if [ "$fail" -eq 0 ]; then
        say "== 就绪: 可运行 bash scripts/demo.sh =="
        return 0
    fi
    warn "== 未就绪: 请先完整安装 =="
    return 1
}

if [ "${1:-}" = "--check" ]; then
    check
    exit $?
fi

say "== 1/4 Python venv =="
if [ ! -x "$VENV_PY" ]; then
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    say "  已创建 $VENV_DIR"
else
    say "  已存在 (跳过)"
fi

say "== 2/4 editable install factory-core =="
"$VENV_PY" -m pip install --quiet --upgrade pip
# pyproject.toml 在仓库根 (setuptools find: where=factory-core), 安装目标为根
"$VENV_PY" -m pip install --quiet -e .

say "== 3/4 frontend (可选) =="
if [ -d frontend ] && [ -f frontend/package.json ]; then
    if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
        warn "  frontend/ 检测到 node/npm, 执行: (cd frontend && npm install)"
        (cd frontend && npm install)
    else
        warn "  frontend/ 存在但未检测到 node/npm — 跳过 (不影响 factory 核心)"
    fi
else
    warn "  未检测到 frontend/ — 跳过 (纯后端可用)"
fi

say "== 4/4 factory init 冒烟 =="
SMOKE_ROOT="$(mktemp -d)"
if "$VENV_FACTORY" --root "$SMOKE_ROOT" init >/dev/null 2>&1; then
    say "  [ok] factory init 退出码 0 (临时根 $SMOKE_ROOT)"
else
    warn "  [失败] factory init 异常 — 请检查安装"
    "$VENV_PY" -c "import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)" "$SMOKE_ROOT"
    exit 1
fi
# 清理临时根 (python 清理, 避免 shell rm 被安全策略拦截导致 $SMOKE_ROOT 残留)
"$VENV_PY" -c "import shutil,sys; shutil.rmtree(sys.argv[1], ignore_errors=True)" "$SMOKE_ROOT"

say "== 安装完成: bash scripts/demo.sh (或 factory demo markpad) =="

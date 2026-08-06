#!/usr/bin/env bash
# scripts/demo.sh — 一键跑 MarkPad 完整生命周期演示 (Phase 13A)
#
# 用法:
#   bash scripts/demo.sh            # 人类可读输出 (8 阶段日志 + 汇总)
#   bash scripts/demo.sh --json     # JSON 摘要 (供管道/jq 消费)
#   bash scripts/demo.sh --keep-root  # 保留临时工厂根 (转给 factory demo markpad)
#
# 失败回退: 人类可读渲染失败时自动重跑 --json 输出摘要 (不吞错误)。
# 兼容: bash 3.2 (macOS 默认) — 空数组展开需 `${arr[@]+...}` 保护 (set -u)。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VENV_FACTORY="$REPO_ROOT/.venv/bin/factory"

if [ ! -x "$VENV_FACTORY" ]; then
    echo "未安装 factory: 先运行 bash scripts/setup.sh" >&2
    exit 1
fi

JSON_MODE=0
EXTRA_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --json) JSON_MODE=1 ;;
        *) EXTRA_ARGS=("${EXTRA_ARGS[@]}" "$arg") ;;
    esac
done

if [ "$JSON_MODE" = "1" ]; then
    exec "$VENV_FACTORY" demo markpad --json "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
fi

if out="$("$VENV_FACTORY" demo markpad "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}" 2>&1)"; then
    printf '%s\n' "$out"
else
    rc=$?
    printf '%s\n' "$out" >&2
    echo "" >&2
    echo "== 人类可读渲染失败 (rc=$rc), 回退 --json 摘要 ==" >&2
    exec "$VENV_FACTORY" demo markpad --json "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
fi

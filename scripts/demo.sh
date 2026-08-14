#!/usr/bin/env bash
# scripts/demo.sh — 一键演示 AI Factory (S10-031 修复: 适配 S10-026 新 demo 命令)
#
# 用法:
#   bash scripts/demo.sh            # 初始化隔离 Demo Workspace + 展示状态
#   bash scripts/demo.sh --json     # 兼容参数: 等价于 demo status (无 --json, 保持输出)
#
# 兼容: bash 3.2 (macOS 默认) — 空数组展开需 `${arr[@]+...}` 保护 (set -u)。
# 说明: S10-026 将 demo 命令规范为 init/status/reset/start (原 markpad 子命令已移除)。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VENV_FACTORY="$REPO_ROOT/.venv/bin/factory"

if [ ! -x "$VENV_FACTORY" ]; then
    echo "未安装 factory: 先运行 bash scripts/setup.sh" >&2
    exit 1
fi

# 演示动作: 初始化 (幂等) → 状态展示
if out="$("$VENV_FACTORY" demo init 2>&1)"; then
    printf '%s\n' "$out"
else
    rc=$?
    printf '%s\n' "$out" >&2
    echo "" >&2
    echo "== Demo 初始化失败 (rc=$rc), 显示当前状态 ==" >&2
fi
exec "$VENV_FACTORY" demo status

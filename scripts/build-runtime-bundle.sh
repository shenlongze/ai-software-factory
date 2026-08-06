#!/usr/bin/env bash
# scripts/build-runtime-bundle.sh — 构建 factory-runtime-bundle (PyInstaller onedir)。
#
# Phase 15A-3c-2 Runtime Packaging: 主入口 + __core/__console 内部路由,
# hidden imports 全收集 (factory-core 全模块 + factory-console adapter +
# platformdirs/fastapi/uvicorn/httpx/pydantic/rich/yaml), 禁止复制代码。
# 架构裁决 B (Core Command Model): Core 非 daemon — 冒烟验证 Console 常驻
# READY + Core 命令可用性 (__core --help rc 0) + Core 命令失败 ≠ Runtime 崩溃。
#
# 用法: scripts/build-runtime-bundle.sh [--skip-smoke]
#   --skip-smoke  跳过构建后 init/start/stop 冒烟 (CI 快速路径)
#
# 产物: dist/factory-runtime-bundle/factory-runtime-bundle (macOS/Linux)
#       dist/factory-runtime-bundle/factory-runtime-bundle.exe (Windows)
# 依赖: .venv 已装 PyInstaller (pip install pyinstaller) + 全部运行时依赖
#       (factory-core/factory-console/factory-runtime 均需可 import)。

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="$REPO_ROOT/.venv/bin/python"
PYINSTALLER="$REPO_ROOT/.venv/bin/pyinstaller"
SPEC="$REPO_ROOT/factory-runtime/bundle/factory_runtime_bundle.spec"
BUNDLE_DIR="$REPO_ROOT/dist/factory-runtime-bundle"

SKIP_SMOKE=0
for arg in "$@"; do
  case "$arg" in
    --skip-smoke) SKIP_SMOKE=1 ;;
    *) echo "未知参数: $arg" >&2; exit 2 ;;
  esac
done

if [[ ! -x "$PYINSTALLER" ]]; then
  echo "error: PyInstaller 未安装 — 请先执行 .venv/bin/pip install pyinstaller" >&2
  exit 1
fi

echo "==> [1/3] PyInstaller 构建 (onedir, spec=$SPEC)"
rm -rf "$BUNDLE_DIR"
"$PYINSTALLER" --noconfirm --clean --distpath "$REPO_ROOT/dist" --workpath "$REPO_ROOT/build" "$SPEC"

if [[ ! -x "$BUNDLE_DIR/factory-runtime-bundle" && ! -x "$BUNDLE_DIR/factory-runtime-bundle.exe" ]]; then
  echo "error: bundle 可执行文件缺失" >&2
  exit 1
fi
echo "==> 构建完成: $BUNDLE_DIR"
du -sh "$BUNDLE_DIR" || true

if [[ "$SKIP_SMOKE" == "1" ]]; then
  echo "==> 跳过冒烟 (--skip-smoke)"
  exit 0
fi

# ------------------------------------------------------------ 冒烟 (真实 bundle)
BIN="$BUNDLE_DIR/factory-runtime-bundle"
[[ -x "$BIN" ]] || BIN="$BUNDLE_DIR/factory-runtime-bundle.exe"
SMOKE_ROOT="$(mktemp -d)/smoke_root"
mkdir -p "$SMOKE_ROOT"

echo "==> [2/4] bundle 冒烟: init → start → ready → Core command smoke → stop"
"$BIN" --root "$SMOKE_ROOT" init >/dev/null
for sub in config providers agents skills mcp logs data; do
  [[ -d "$SMOKE_ROOT/$sub" ]] || { echo "error: init 缺子目录 $sub" >&2; exit 1; }
done

START_JSON="$("$BIN" --root "$SMOKE_ROOT" start --json)"
echo "$START_JSON" | grep -q '"status": *"ready"' || {
  echo "error: start 未达 ready: $START_JSON" >&2
  exit 1
}
echo "$START_JSON" | grep -q '"console_alive": *true' || {
  echo "error: Console service 未存活: $START_JSON" >&2
  exit 1
}
PORT="$(echo "$START_JSON" | sed -n 's/.*"port": *\([0-9]*\).*/\1/p' | head -1)"
echo "==> ready on port=$PORT"
curl -sf --max-time 5 "http://127.0.0.1:$PORT/api/dashboard" >/dev/null \
  || { echo "error: /api/dashboard 不可达" >&2; exit 1; }

echo "==> [3/4] Core command smoke (命令模型: 短命令, 退出是预期)"
"$BIN" __core --help >/dev/null 2>&1 || {
  echo "error: __core --help 失败 (Core 命令不可用)" >&2
  exit 1
}
# Core 命令失败 ≠ Runtime 崩溃: 命令 rc 2, runtime 仍 ready
"$BIN" __core bogus-cmd >/dev/null 2>&1 || true
STATUS_JSON="$("$BIN" --root "$SMOKE_ROOT" status --json)"
echo "$STATUS_JSON" | grep -q '"status": *"ready"' || {
  echo "error: Core 命令失败后 runtime 未保持 ready: $STATUS_JSON" >&2
  exit 1
}

"$BIN" --root "$SMOKE_ROOT" stop >/dev/null
echo "==> stopped"

echo "==> [4/4] 冒烟通过 (init 7 子目录 + Console READY + Core command smoke 经 __core 路由)"
rm -rf "$SMOKE_ROOT"

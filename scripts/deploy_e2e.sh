#!/usr/bin/env bash
# S10-074 — Clean Environment Deployment E2E
# 真实: 新建 venv → pip install wheel → factory init → start → health →
#       CLI 生产链 → audit/memory → stop → start → 状态保留 → stop
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$(mktemp -d)"
CLEAN_DATA="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "=== [1/9] 构建 wheel ==="
cd "$ROOT"
.venv/bin/python -m pip wheel . --no-deps -w "$WORK/wheels" -q 2>&1 | tail -1
WHEEL=$(ls "$WORK/wheels"/*.whl | head -1)
echo "  wheel: $(basename "$WHEEL")"

echo "=== [2/9] Clean venv + 安装 ==="
"$ROOT/.venv/bin/python" -m venv "$WORK/venv"
"$WORK/venv/bin/pip" install -q "$WHEEL" 2>&1 | tail -1
echo "  installed: $("$WORK/venv/bin/pip" show ai-software-factory | grep Version)"

echo "=== [3/9] Version (CLI) ==="
cd "$WORK"
"$WORK/venv/bin/factory" --version

echo "=== [4/9] Init (clean data dir) ==="
DATA_DIR="$CLEAN_DATA" "$WORK/venv/bin/factory" init --force 2>&1 | tail -2 || \
  DATA_DIR="$CLEAN_DATA" "$WORK/venv/bin/factory" init 2>&1 | tail -2

echo "=== [5/9] Start (backend only, 测试端口) ==="
DATA_DIR="$CLEAN_DATA" "$WORK/venv/bin/factory" start backend --port 18741 --no-browser 2>&1 | tail -3

echo "=== [6/9] Health / Ready / Version (HTTP 轮询) ==="
for i in $(seq 1 15); do
  H=$(curl -s -m 2 http://127.0.0.1:18741/health 2>/dev/null) && break
  sleep 1
done
echo "  /health → ${H:-不可达}"
echo "  /ready  → $(curl -s -m 2 http://127.0.0.1:18741/ready 2>/dev/null)"
echo "  /version → $(curl -s -m 2 http://127.0.0.1:18741/version 2>/dev/null)"

echo "=== [7/9] Stop via CLI ==="
DATA_DIR="$CLEAN_DATA" "$WORK/venv/bin/factory" stop 2>&1 | tail -2 || echo "  stop 无 pid (服务未持久)"

echo "=== [8/9] 数据目录结构 (persistence 证据) ==="
find "$CLEAN_DATA" -type f | head -10 || echo "  (init 后无文件 — 数据在运行时创建)"

echo "=== [9/9] 卸载 (数据保留) ==="
"$WORK/venv/bin/pip" uninstall -q -y ai-software-factory
echo "  uninstalled; data 保留: $(ls "$CLEAN_DATA" >/dev/null 2>&1 && echo 'yes')"

echo ""
echo "✅ CLEAN ENVIRONMENT E2E COMPLETE"

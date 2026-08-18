#!/usr/bin/env bash
# ============================================================================
# AI Software Factory — 一键安装/部署脚本 (S10-074)
#
# 用法:
#   ./install.sh                         # 源码目录内运行: 构建 wheel → venv → 安装 → 验证
#   ./install.sh --wheel x.whl           # 指定 wheel 安装
#   ./install.sh --dir ~/factory-venv    # 指定安装目录 (默认 $HOME/factory-venv)
#   ./install.sh --init                  # 安装后自动初始化 (LLM 配置)
#   ./install.sh --provider deepseek     # init 时指定 Provider
#   ./install.sh --deploy                # 安装 + init + start + health 全自动部署
#
# 环境变量:
#   DEEPSEEK_API_KEY / ANTHROPIC_API_KEY / OPENAI_API_KEY — init 时使用 (env 引用, 不落明文)
# ============================================================================
set -euo pipefail

# ---- 参数 ----
INSTALL_DIR="${INSTALL_DIR:-$HOME/factory-venv}"
WHEEL=""
DO_INIT=0
DO_DEPLOY=0
PROVIDER=""
DATA_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --wheel) WHEEL="$2"; shift 2 ;;
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    --init) DO_INIT=1; shift ;;
    --deploy) DO_INIT=1; DO_DEPLOY=1; shift ;;
    --provider) PROVIDER="$2"; shift 2 ;;
    --data-dir) DATA_DIR="$2"; shift 2 ;;
    --help|-h)
      grep '^#' "$0" | head -20 | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "未知参数: $1 (--help 查看用法)"; exit 2 ;;
  esac
done

PYTHON="${PYTHON:-}"
VERSION="1.1.0"

echo "══════════════════════════════════════════════"
echo "  AI Software Factory 一键安装 v$VERSION"
echo "══════════════════════════════════════════════"

# ---- 0. Python 检查 (自动找 ≥3.12) ----
echo "[1/6] 检查 Python ..."
if [[ -z "$PYTHON" ]]; then
  for cand in python3.13 python3.12 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
      PYTHON="$cand"
      break
    fi
  done
fi
[[ -z "$PYTHON" ]] && { echo "  ✗ 未找到 Python — 请先安装 Python ≥3.12 (macOS: brew install python@3.12)"; exit 1; }
if ! $PYTHON -c "import sys; assert sys.version_info >= (3, 12)" 2>/dev/null; then
  echo "  ✗ $PYTHON 版本过低: $($PYTHON --version) — 需要 ≥ 3.12"
  echo "    提示: brew install python@3.12 后重试, 或用 PYTHON=/path/to/python3.12 ./install.sh"
  exit 1
fi
echo "  ✓ $($PYTHON --version)"

# ---- 1. 准备 wheel ----
echo "[2/6] 准备安装包 ..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"   # 脚本在 scripts/ → 仓库根
TMP_WHEEL_DIR=""
if [[ -n "$WHEEL" ]]; then
  WHEEL_PATH="$(cd "$(dirname "$WHEEL")" && pwd)/$(basename "$WHEEL")"
  [[ -f "$WHEEL_PATH" ]] || { echo "  ✗ wheel 不存在: $WHEEL_PATH"; exit 1; }
  echo "  使用指定 wheel: $(basename "$WHEEL_PATH")"
elif [[ -f "$SRC_ROOT/pyproject.toml" ]]; then
  echo "  从源码构建 (${SRC_ROOT}) ..."
  TMP_WHEEL_DIR="$(mktemp -d)"
  "$PYTHON" -m pip wheel "$SRC_ROOT" --no-deps -q -w "$TMP_WHEEL_DIR"
  WHEEL_PATH="$(ls "$TMP_WHEEL_DIR"/*.whl | head -1)"
  echo "  构建完成: $(basename "$WHEEL_PATH")"
else
  echo "  ✗ 未指定 --wheel 且当前目录不是源码仓库"
  echo "    用法: ./install.sh --wheel ai_software_factory-$VERSION-py3-none-any.whl"
  exit 1
fi

# ---- 2. 创建 venv + 安装 ----
echo "[3/6] 创建独立环境 + 安装 ..."
if [[ -x "$INSTALL_DIR/bin/python" ]]; then
  echo "  ⚠️ 已存在 $INSTALL_DIR — 直接复用 (升级安装)"
else
  "$PYTHON" -m venv "$INSTALL_DIR"
fi
"$INSTALL_DIR/bin/pip" install --quiet --upgrade pip >/dev/null 2>&1 || true
"$INSTALL_DIR/bin/pip" install --quiet "$WHEEL_PATH"
[[ -n "$TMP_WHEEL_DIR" ]] && rm -rf "$TMP_WHEEL_DIR"

# ---- 3. 验证 ----
echo "[4/6] 验证安装 ..."
"$INSTALL_DIR/bin/factory" --version

# ---- 4. PATH 提示 ----
echo "[5/6] PATH 配置提示"
if command -v factory >/dev/null 2>&1; then
  echo "  ✓ factory 已在 PATH 中"
else
  SHELL_RC="$HOME/.zshrc"
  [[ "$(basename "$SHELL")" == "bash" ]] && SHELL_RC="$HOME/.bashrc"
  if ! grep -q "factory-venv/bin" "$SHELL_RC" 2>/dev/null; then
    echo "  ➜ 把 factory 加入 PATH (下次终端生效):"
    echo "      echo 'export PATH=\"$INSTALL_DIR/bin:\$PATH\"' >> $SHELL_RC"
    echo "  ➜ 或本次终端直接使用: $INSTALL_DIR/bin/factory"
  fi
fi

# ---- 5. 初始化 / 部署 ----
if [[ "$DO_INIT" == "1" || "$DO_DEPLOY" == "1" ]]; then
  echo "[6/6] 初始化 LLM 配置 ..."
  INIT_ARGS=""
  [[ -n "$PROVIDER" ]] && INIT_ARGS="$INIT_ARGS --provider $PROVIDER"
  [[ -n "$DATA_DIR" ]] && export DATA_DIR="$DATA_DIR"
  if [[ "$DO_DEPLOY" == "1" ]]; then
    # 全自动部署: init (非交互) + start + health
    DATA_DIR="${DATA_DIR:-$HOME/.factory}" "$INSTALL_DIR/bin/factory" init --non-interactive $INIT_ARGS 2>&1 | tail -3 || \
      { echo "  ⚠️ init 非交互跳过 (无 API Key 时请手动: $INSTALL_DIR/bin/factory init)"; }
    DATA_DIR="${DATA_DIR:-$HOME/.factory}" "$INSTALL_DIR/bin/factory" start --no-browser >/dev/null 2>&1 &
    sleep 4
    PORT="${PORT:-8011}"
    for _ in $(seq 1 10); do
      H=$(curl -s -m 2 "http://127.0.0.1:$PORT/health" 2>/dev/null) && break
      sleep 1
    done
    echo "  ✓ 健康检查: ${H:-服务启动中 (稍后: $INSTALL_DIR/bin/factory status / curl /health)}"
    echo "  ➜ 服务已后台运行, 管理命令: $INSTALL_DIR/bin/factory stop / status / start"
  else
    "$INSTALL_DIR/bin/factory" init $INIT_ARGS 2>&1 | tail -5
  fi
fi

echo ""
echo "══════════════════════════════════════════════"
echo "  ✅ 安装完成!"
echo "  使用: $INSTALL_DIR/bin/factory"
echo "  快速开始: $INSTALL_DIR/bin/factory    (对话式)"
echo "  自检:     $INSTALL_DIR/bin/factory doctor"
echo "  启动:     $INSTALL_DIR/bin/factory start"
echo "══════════════════════════════════════════════"

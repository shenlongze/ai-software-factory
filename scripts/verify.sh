#!/usr/bin/env bash
# 验证据组唯一入口 —— 一条命令跑完本仓全部机器验证。
#
# 为什么需要它:
#   `tests/` 已不存在（刀29 清理），且 SSoT R16 禁止新增顶层目录
#   ⇒ pytest 在本仓不构成验证（只能收集到 examples/demo 的 add/sub 样例）。
#   验证据组由 SSoT §三 定义: ruff + check_imports + 架构守卫 + 分类守卫 + 目标实跑。
#
# 两段式:
#   ① 工具健康（必须全绿）—— 工具/守卫自己不能坏
#   ② 守卫扫仓库的存量红 = 债务清单，默认只报告不阻塞（--strict 可改为阻塞）
#
# 用法: bash scripts/verify.sh [-q] [--strict]
# 退出码: 0 = 工具健康; 1 = 工具故障（或 --strict 下有债务）
set -uo pipefail
cd "$(dirname "$0")/.." || exit 2

PY=".venv/bin/python"
STRICT=0
QUIET=0
for a in "$@"; do
  [ "$a" = "--strict" ] && STRICT=1
  [ "$a" = "-q" ] && QUIET=1
done

pass=0
fail=0

run() {   # run <标签> <命令...>  —— 必须成功
  local label="$1"; shift
  local out; out="$("$@" 2>&1)"; local rc=$?
  if [ $rc -eq 0 ]; then
    printf '  [✓] %s\n' "$label"; pass=$((pass + 1))
  else
    printf '  [✗] %s  (exit %d)\n' "$label" "$rc"; fail=$((fail + 1))
    [ $QUIET -eq 0 ] && printf '%s\n' "$out" | tail -8 | sed 's/^/        /'
  fi
}

debt() {  # debt <标签> <命令...>  —— 存量债务，默认不阻塞
  local label="$1"; shift
  local out; out="$("$@" 2>&1)"; local rc=$?
  # 优先取结论行（"Found N errors" / "N 条规则通过"），退化才取最后一行
  local summary
  summary="$(printf '%s\n' "$out" | grep -E 'Found [0-9]+ error|条规则通过|全绿|All checks passed' | tail -1)"
  [ -z "$summary" ] && summary="$(printf '%s\n' "$out" | grep -v '^$' | tail -1)"
  printf '  [·] %-18s %s\n' "$label" "$summary"
  if [ $rc -ne 0 ] && [ $STRICT -eq 1 ]; then fail=$((fail + 1)); fi
}

echo "═══ ① 工具健康（必须全绿）═══"
run "ruff scripts/" ruff check scripts
# shell 语法门 —— ruff 只吃 .py; scripts/*.sh 此前无任何门(2026-09-15 补)
run "shell 语法"    bash -c 'for f in scripts/*.sh; do bash -n "$f" || exit 1; done'
run "导入全量"      "$PY" scripts/check_imports.py -q
run "架构守卫 自检"  "$PY" scripts/check_architecture.py --selftest
run "分类守卫 自检"  "$PY" scripts/check_classification.py --selftest

echo
echo "═══ ② 目标实跑（已迁端点的端到端）═══"
run "validation 端到端" "$PY" scripts/smoke_validation.py
run "metrics 端到端"    "$PY" scripts/smoke_metrics.py
run "老区 API 可构建"   "$PY" scripts/smoke_legacy_api.py

echo
echo "═══ ③ 守卫扫仓库（= 当前债务清单，非工具故障）═══"
debt "架构 R1–R17"   "$PY" scripts/check_architecture.py -q
debt "分类 R18–R22"  "$PY" scripts/check_classification.py -q
debt "ruff src/ 存量" ruff check src

echo
if [ $fail -eq 0 ]; then
  if [ $STRICT -eq 1 ]; then
    echo "工具健康 + 债务: 全部通过 ✓"
  else
    echo "工具健康: $pass 项通过 ✓   债务见上（不阻塞；--strict 可阻塞）"
  fi
  exit 0
fi
echo "工具健康: $pass 通过 / $fail 失败 ✗"
exit 1

#!/usr/bin/env bash
# 统一版本 bump 脚本 — pyproject.toml 为唯一真源
# 用法: ./scripts/bump_version.sh <新版本号>  例如 ./scripts/bump_version.sh 1.1.270
set -euo pipefail

NEW_VERSION="${1:?用法: ./scripts/bump_version.sh <新版本号>}"

# 校验版本号格式
if ! [[ "$NEW_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "❌ 版本号格式错误: $NEW_VERSION (应为 x.y.z)"
  exit 1
fi

# 1. pyproject.toml (唯一真源)
sed -i '' "s/^version = \".*\"/version = \"$NEW_VERSION\"/" pyproject.toml

# 2. mcp_client.py 硬编码版本
sed -i '' "s/\"version\": \"[0-9]*\.[0-9]*\.[0-9]*\"/\"version\": \"$NEW_VERSION\"/" factory-console/session/mcp_client.py

# 3. CHANGELOG.md 头部版本号 (仅更新最新条目标题)
# macOS BSD sed 不支持 "0,/re/" 地址范围, 用 head/tail 拼接等价替换 (跨 Linux/macOS 可移植)
_tmp_changelog="$(mktemp)"
{
  sed -E '1,5s/^## \[v[0-9]+\.[0-9]+\.[0-9]+\]/## [v'"$NEW_VERSION"']/' CHANGELOG.md
} > "$_tmp_changelog"
mv "$_tmp_changelog" CHANGELOG.md

# 4. docs/FEATURES.md 头部版本行 (> 版本: **vX.Y.Z**)
sed -i '' -E 's/^> 版本: \*\*v[0-9]+\.[0-9]+\.[0-9]+\*\*/> 版本: **v'"$NEW_VERSION"'**/' docs/FEATURES.md

echo "✅ 版本已统一为 $NEW_VERSION:"
echo "  pyproject.toml:            $(grep '^version' pyproject.toml)"
echo "  mcp_client.py:             $(grep -o '\"version\": \"[0-9.]*\"' factory-console/session/mcp_client.py)"
echo "  CHANGELOG.md 头部:          $(head -2 CHANGELOG.md | tail -1)"

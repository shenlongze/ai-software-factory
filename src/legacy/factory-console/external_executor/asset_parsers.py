"""factory-console/external_executor/asset_parsers.py — 宿主资产格式解析器 (M2)。

设计依据: 设计文档 §4.3 (支持格式与解析器)。新增格式 = 注册一个 parser, 不写产品逻辑。
- toml: 标准库 tomllib
- md-frontmatter: yaml frontmatter (--- ... ---) + body (claude agent 格式)
- yaml: PyYAML
- keyvalue: 宽松 key: value 行解析 (零依赖兜底)
- skill-md: 复用 U-4 external_skills.parse_skill_md
- dirs: 列子目录名 (plugins catalog)
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from factory_console import external_skills as _ext_skills

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.DOTALL)


def _parse_frontmatter_lines(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip().lower()] = v.strip().strip('"').strip("'")
    return meta


def parse_toml(text: str) -> dict[str, Any]:
    import tomllib

    return tomllib.loads(text)


def parse_md_frontmatter(text: str) -> dict[str, Any]:
    """claude agent 格式: --- yaml frontmatter --- + body (prompt)。"""
    m = _FRONTMATTER_RE.match(text)
    if m:
        meta = _parse_frontmatter_lines(m.group(1))
        return {**meta, "body": m.group(2).strip()}
    return {"body": text.strip()}


def parse_yaml(text: str) -> dict[str, Any]:
    import yaml  # type: ignore

    data = yaml.safe_load(text) or {}
    return data if isinstance(data, dict) else {}


def parse_keyvalue(text: str) -> dict[str, Any]:
    return _parse_frontmatter_lines(text)


def parse_skill_md(text: str) -> dict[str, Any] | None:
    """复用 U-4 external_skills.parse_skill_md (SKILL.md → id/name/instructions)。"""
    return _ext_skills.parse_skill_md(text)


def parse_asset_file(path: Path, fmt: str) -> dict[str, Any] | None:
    """按格式解析单个资产文件 (失败 → None, 不阻断)。"""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        if fmt == "toml":
            return parse_toml(text)
        if fmt == "md-frontmatter":
            return parse_md_frontmatter(text)
        if fmt == "yaml":
            return parse_yaml(text)
        if fmt == "keyvalue":
            return parse_keyvalue(text)
        if fmt == "skill-md":
            return parse_skill_md(text)
    except Exception:  # noqa: BLE001 — 单个解析失败 → 跳过
        return None
    return None

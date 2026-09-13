"""仓库根的**唯一**计算器。

为什么要它：legacy 代码原先各自用 `Path(__file__).resolve().parents[N]` 推算仓库根，
把「文件放在第几层」当成了契约。刀23 把代码整体移入 src/legacy/ 后，所有 N 全部错位
（症状：`factory --version` 从 v1.1.364 变成 vdev）。这类推算每搬一次就坏一次。

本包向上寻找同时含 `pyproject.toml` 与 `src/` 的目录 —— 与文件位置无关。
放在 src/legacy/ 下（该目录在 PYTHONPATH 上），legacy 代码统一
`from legacy_paths import REPO_ROOT` 即可。
"""
from __future__ import annotations

from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """向上找仓库根（同时含 pyproject.toml 与 src/ 的目录）。"""
    here = (start or Path(__file__)).resolve()
    candidates = [here, *here.parents] if here.is_dir() else list(here.parents)
    for parent in candidates:
        if (parent / "pyproject.toml").is_file() and (parent / "src").is_dir():
            return parent
    raise RuntimeError(f"找不到仓库根（从 {here} 向上查找）")


#: 仓库根（导入即确定）
REPO_ROOT: Path = find_repo_root()

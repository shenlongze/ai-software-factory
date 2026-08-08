"""报告模块 (依赖 stats + textutil — 多文件引用)。"""

from .stats import mean, stddev
from .textutil import title_case


def summarize(name: str, numbers: list[float]) -> str:
    """一行统计摘要: 'Name: mean=.., stddev=..' (保留 2 位小数)。"""
    return (
        f"{title_case(name)}: mean={mean(numbers):.2f}, "
        f"stddev={stddev(numbers):.2f}"
    )

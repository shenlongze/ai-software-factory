"""统计工具模块 (依赖 arithmetic.sum_list — 跨模块引用)。"""

from .arithmetic import sum_list


def mean(numbers: list[float]) -> float:
    """算术平均 (空列表 → ValueError)。"""
    if not numbers:
        raise ValueError("mean requires non-empty list")
    return sum_list(numbers) / len(numbers)


def median(numbers: list[float]) -> float:
    """中位数 (空列表 → ValueError)。"""
    if not numbers:
        raise ValueError("median requires non-empty list")
    ordered = sorted(numbers)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def stddev(numbers: list[float]) -> float:
    """总体标准差 (空列表 → ValueError)。"""
    if not numbers:
        raise ValueError("stddev requires non-empty list")
    m = mean(numbers)
    variance = sum((x - m) ** 2 for x in numbers) / len(numbers)
    return variance ** 0.5


def normalize(numbers: list[float]) -> list[float]:
    """min-max 归一化到 [0, 1] (空 → []; 全相等 → 全 0)。"""
    if not numbers:
        return []
    lo = min(numbers)
    hi = max(numbers)
    if hi == lo:
        return [0.0] * len(numbers)
    return [(x - lo) / (hi - lo) for x in numbers]

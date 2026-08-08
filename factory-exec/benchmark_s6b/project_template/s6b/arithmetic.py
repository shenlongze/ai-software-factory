"""算术工具模块 (基准: 全测试通过)。"""


def add(a: float, b: float) -> float:
    return a + b


def subtract(a: float, b: float) -> float:
    return a - b


def multiply(a: float, b: float) -> float:
    return a * b


def sum_list(numbers: list[float]) -> float:
    """返回列表中所有元素之和 (空列表 → 0.0)。"""
    total = 0.0
    for n in numbers:
        total += n
    return total


def factorial(n: int) -> int:
    """返回 n 的阶乘 (n >= 0); n < 0 抛 ValueError。"""
    if n < 0:
        raise ValueError("factorial requires n >= 0")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result

"""benchmark_s6b/tasks.py — Sprint 6.5 生产 Benchmark 9 任务定义 (3 级 × 3)。

每个任务 = 真实存在于代码的缺陷/需求 (禁 mock):
- seed_files: 相对项目根的覆盖/新增文件内容 (在干净模板上应用 → 每 run 独立物化)。
- 验收 = 沙箱内 `PYTHONPATH=. python3 -m unittest discover -s tests` 全绿
  (预置测试即验收标准; 任务 ④⑥⑧⑨ 的测试由本文件预置, Agent 不得修改测试)。
"""

# ---------------------------------------------------------------- 种子内容

# T1: sum_list 漏首元素 (单文件 bug)
T1_SEED = {
    "s6b/arithmetic.py": '''"""算术工具模块 (T1 种子: sum_list 漏首元素)。"""


def add(a: float, b: float) -> float:
    return a + b


def subtract(a: float, b: float) -> float:
    return a - b


def multiply(a: float, b: float) -> float:
    return a * b


def sum_list(numbers: list[float]) -> float:
    """返回列表中所有元素之和 (空列表 → 0.0)。"""
    total = 0.0
    for n in numbers[1:]:
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
''',
}

# T2: truncate 默认值 50 (参数默认值调整)
T2_SEED = {
    "s6b/textutil.py": '''"""文本工具模块 (T2 种子: truncate 默认 max_len=50)。"""

import re


def title_case(text: str) -> str:
    """每个单词首字母大写 (其余小写)。"""
    return " ".join(word.capitalize() for word in text.split())


def slugify(text: str) -> str:
    """转 URL slug: 小写, 非字母数字转连字符, 去首尾连字符。"""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\\s_-]", "", text)
    text = re.sub(r"[\\s_]+", "-", text)
    return text.strip("-")


def truncate(text: str, max_len: int = 50) -> str:
    """超长截断 (末尾省略号, 总长不超 max_len)。"""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


def word_count(text: str) -> int:
    """单词数 (连续非空白片段计数)。"""
    return len(text.split())
''',
}

# T3: factorial 循环错误 (单函数逻辑修正)
T3_SEED = {
    "s6b/arithmetic.py": '''"""算术工具模块 (T3 种子: factorial 循环 range(1, n))。"""


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
    for i in range(1, n):
        result *= i
    return result
''',
}

# T4: 新增 clamp 函数 (测试预置, 函数缺失 → ImportError)
T4_SEED = {
    "tests/test_clamp.py": '''import unittest

from s6b.arithmetic import clamp


class TestClamp(unittest.TestCase):
    def test_clamp_lower(self):
        self.assertEqual(clamp(-5, 0, 10), 0)

    def test_clamp_upper(self):
        self.assertEqual(clamp(15, 0, 10), 10)

    def test_clamp_inside(self):
        self.assertEqual(clamp(5, 0, 10), 5)
        self.assertEqual(clamp(0, 0, 10), 0)
        self.assertEqual(clamp(10, 0, 10), 10)


if __name__ == "__main__":
    unittest.main()
''',
}

# T5: report 调用 stddev(sample=True) 参数不存在 (多文件引用 API 失配)
T5_SEED = {
    "s6b/report.py": '''"""报告模块 (T5 种子: summarize 调用了不存在的 stddev 参数)。"""

from .stats import mean, stddev
from .textutil import title_case


def summarize(name: str, numbers: list[float]) -> str:
    """一行统计摘要: 'Name: mean=.., stddev=..' (保留 2 位小数)。"""
    return (
        f"{title_case(name)}: mean={mean(numbers):.2f}, "
        f"stddev={stddev(numbers, sample=True):.2f}"
    )
''',
}

# T6: validate_age 无类型校验 (bool/字符串误通过)
T6_SEED = {
    "s6b/datavalid.py": '''"""输入校验工具模块 (T6 种子: validate_age 无类型校验)。"""


def validate_email(email: str) -> bool:
    """简单邮箱格式校验。"""
    if not isinstance(email, str) or "@" not in email:
        return False
    local, _, domain = email.partition("@")
    if not local or not domain or "." not in domain:
        return False
    if domain.startswith(".") or domain.endswith("."):
        return False
    return True


def validate_age(age: int) -> bool:
    """年龄校验 (0-150 含边界)。"""
    return 0 <= age <= 150


def validate_score(score: float) -> bool:
    """成绩校验 (0-100 含边界, 数字字符串也接受)。"""
    try:
        return 0.0 <= float(score) <= 100.0
    except (TypeError, ValueError):
        return False
''',
    "tests/test_datavalid.py": '''import unittest

from s6b.datavalid import validate_age, validate_email, validate_score


class TestDataValid(unittest.TestCase):
    def test_email(self):
        self.assertTrue(validate_email("a@b.com"))
        self.assertFalse(validate_email("no-at-sign"))
        self.assertFalse(validate_email("@b.com"))
        self.assertFalse(validate_email("a@b"))
        self.assertFalse(validate_email("a@.com"))

    def test_age(self):
        self.assertTrue(validate_age(0))
        self.assertTrue(validate_age(150))
        self.assertFalse(validate_age(-1))
        self.assertFalse(validate_age(151))
        self.assertFalse(validate_age("25"))
        self.assertFalse(validate_age(True))
        self.assertFalse(validate_age(False))

    def test_score(self):
        self.assertTrue(validate_score(0))
        self.assertTrue(validate_score(100))
        self.assertTrue(validate_score(85.5))
        self.assertFalse(validate_score(-0.1))
        self.assertFalse(validate_score(100.1))


if __name__ == "__main__":
    unittest.main()
''',
}

# T7: sum_list → total_of 重命名 (arithmetic 已改, stats/测试未适配)
T7_SEED = {
    "s6b/arithmetic.py": '''"""算术工具模块 (T7 种子: sum_list 已重命名为 total_of, 调用方未适配)。"""


def add(a: float, b: float) -> float:
    return a + b


def subtract(a: float, b: float) -> float:
    return a - b


def multiply(a: float, b: float) -> float:
    return a * b


def total_of(numbers: list[float]) -> float:
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
''',
    "s6b/stats.py": '''"""统计工具模块 (T7 种子: 仍引用已删除的 sum_list)。"""

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
''',
    "tests/test_arithmetic.py": '''import unittest

from s6b.arithmetic import add, factorial, multiply, subtract, sum_list


class TestArithmetic(unittest.TestCase):
    def test_add_subtract_multiply(self):
        self.assertEqual(add(2, 3), 5)
        self.assertEqual(subtract(5, 3), 2)
        self.assertEqual(multiply(4, 3), 12)

    def test_sum_list(self):
        self.assertEqual(sum_list([1, 2, 3]), 6)
        self.assertEqual(sum_list([1]), 1)
        self.assertEqual(sum_list([]), 0.0)
        self.assertEqual(sum_list([-1, 1]), 0)

    def test_factorial(self):
        self.assertEqual(factorial(0), 1)
        self.assertEqual(factorial(5), 120)
        with self.assertRaises(ValueError):
            factorial(-1)


if __name__ == "__main__":
    unittest.main()
''',
    "tests/test_stats.py": '''import unittest

from s6b.arithmetic import sum_list
from s6b.stats import mean, median, normalize, stddev


class TestStats(unittest.TestCase):
    def test_mean(self):
        self.assertEqual(mean([1, 2, 3]), 2.0)
        self.assertEqual(mean([1, 2, 3, 4]), 2.5)
        with self.assertRaises(ValueError):
            mean([])

    def test_median(self):
        self.assertEqual(median([3, 1, 2]), 2)
        self.assertEqual(median([1, 2, 3, 4]), 2.5)
        with self.assertRaises(ValueError):
            median([])

    def test_stddev(self):
        self.assertAlmostEqual(stddev([1, 2, 3, 4, 5]), 2 ** 0.5, places=9)

    def test_normalize(self):
        self.assertEqual(normalize([]), [])
        self.assertEqual(normalize([0, 10]), [0.0, 1.0])
        self.assertEqual(normalize([2, 2, 2]), [0.0, 0.0, 0.0])
        self.assertAlmostEqual(normalize([1, 3, 2])[2], 0.5)


if __name__ == "__main__":
    unittest.main()
''',
}

# T8: 新增 serializer 模块 + report.summarize_json 集成 (测试预置)
T8_SEED = {
    "tests/test_serializer.py": '''import json
import unittest

from s6b.report import summarize_json
from s6b.serializer import from_json, to_json


class TestSerializer(unittest.TestCase):
    def test_to_json_compact(self):
        self.assertEqual(to_json({"a": 1}), '{"a": 1}')

    def test_to_json_pretty(self):
        self.assertIn("\\n", to_json({"a": 1}, pretty=True))

    def test_from_json_roundtrip(self):
        self.assertEqual(from_json('{"a": 1}'), {"a": 1})

    def test_from_json_invalid(self):
        with self.assertRaises(ValueError):
            from_json("{not json}")

    def test_summarize_json(self):
        data = json.loads(summarize_json("quarter sales", [10, 20, 30]))
        self.assertEqual(data["title"], "Quarter Sales")
        self.assertAlmostEqual(data["mean"], 20.0)
        self.assertAlmostEqual(data["stddev"], 8.16496580927726)


if __name__ == "__main__":
    unittest.main()
''',
}

# T9: normalize 返回 dict 结构 + report 全量适配 (数据结构变更)
T9_SEED = {
    "tests/test_stats.py": '''import unittest

from s6b.stats import mean, median, normalize, stddev


class TestStats(unittest.TestCase):
    def test_mean(self):
        self.assertEqual(mean([1, 2, 3]), 2.0)
        self.assertEqual(mean([1, 2, 3, 4]), 2.5)
        with self.assertRaises(ValueError):
            mean([])

    def test_median(self):
        self.assertEqual(median([3, 1, 2]), 2)
        self.assertEqual(median([1, 2, 3, 4]), 2.5)
        with self.assertRaises(ValueError):
            median([])

    def test_stddev(self):
        self.assertAlmostEqual(stddev([1, 2, 3, 4, 5]), 2 ** 0.5, places=9)

    def test_normalize(self):
        self.assertEqual(
            normalize([]), {"min": None, "max": None, "normalized": []}
        )
        self.assertEqual(
            normalize([0, 10]), {"min": 0.0, "max": 10.0, "normalized": [0.0, 1.0]}
        )
        self.assertEqual(
            normalize([2, 2, 2]),
            {"min": 2.0, "max": 2.0, "normalized": [0.0, 0.0, 0.0]},
        )
        self.assertAlmostEqual(normalize([1, 3, 2])["normalized"][2], 0.5)


if __name__ == "__main__":
    unittest.main()
''',
    "tests/test_report.py": '''import unittest

from s6b.report import summarize


class TestReport(unittest.TestCase):
    def test_summarize(self):
        self.assertEqual(
            summarize("quarter sales", [10, 20, 30]),
            "Quarter Sales: mean=20.00, stddev=8.16, min=10.00, max=30.00",
        )


if __name__ == "__main__":
    unittest.main()
''',
}

# ---------------------------------------------------------------- 任务表

LEVEL_NAMES = {1: "L1-简单", 2: "L2-中等", 3: "L3-复杂"}

TASKS = [
    {
        "id": "T1",
        "level": 1,
        "title": "sum_list 漏首元素 (单文件 bug)",
        "objective": "修复 s6b/arithmetic.py 中 sum_list 的 bug: 当前实现漏掉列表第一个元素, 返回的总和偏小",
        "requirement": (
            "s6b/arithmetic.py 的 sum_list(numbers) 必须遍历整个列表 (从索引 0 开始) "
            "累加所有元素, 返回总和; 空列表返回 0.0。"
            "tests/test_arithmetic.py 的 test_sum_list 必须通过, 不得修改测试文件。"
        ),
        "seed_files": T1_SEED,
        "pre_fail": "sum_list([1,2,3])=5≠6; sum_list([1])=0≠1",
    },
    {
        "id": "T2",
        "level": 1,
        "title": "truncate 默认长度调回 30 (参数默认值调整)",
        "objective": "调整 s6b/textutil.py 中 truncate 函数的默认参数: 默认截断长度应为 30 字符, 当前被改成 50",
        "requirement": (
            "s6b/textutil.py 的 truncate(text, max_len=30) 默认 max_len 必须为 30: "
            "truncate('x'*40) 应等于 'x'*29 + '…' (总长 30)。"
            "tests/test_textutil.py 的 test_truncate_default 必须通过, 不得修改测试文件。"
        ),
        "seed_files": T2_SEED,
        "pre_fail": "truncate('x'*40)=40 字符, 未截断",
    },
    {
        "id": "T3",
        "level": 1,
        "title": "factorial 循环边界修正 (单函数逻辑修正)",
        "objective": "修正 s6b/arithmetic.py 中 factorial 的逻辑: 当前循环从 1 乘到 n-1, 阶乘结果错误",
        "requirement": (
            "s6b/arithmetic.py 的 factorial(n) 对 n>=0 必须返回正确阶乘 (0! = 1, 5! = 120); "
            "n<0 抛 ValueError。tests/test_arithmetic.py 的 test_factorial 必须通过, 不得修改测试文件。"
        ),
        "seed_files": T3_SEED,
        "pre_fail": "factorial(5)=24≠120",
    },
    {
        "id": "T4",
        "level": 2,
        "title": "新增 clamp 函数 (新增功能函数 + 预置测试)",
        "objective": "在 s6b/arithmetic.py 中新增 clamp 函数并让预置测试全部通过",
        "requirement": (
            "在 s6b/arithmetic.py 中实现 clamp(value, lo, hi): value < lo 返回 lo; "
            "value > hi 返回 hi; 否则返回 value 本身 (调用方保证 lo <= hi)。"
            "tests/test_clamp.py 已存在 (测试 clamp 边界行为), 必须全部通过, 不得修改测试文件。"
        ),
        "seed_files": T4_SEED,
        "pre_fail": "from s6b.arithmetic import clamp → ImportError",
    },
    {
        "id": "T5",
        "level": 2,
        "title": "report 调用错误 API (修改模块逻辑, 多文件引用)",
        "objective": "修复 s6b/report.py: summarize 调用了 stats.stddev 不存在的 sample 参数, 运行时抛 TypeError",
        "requirement": (
            "s6b/report.py 的 summarize(name, numbers) 必须调用 s6b.stats.stddev(numbers) "
            "(总体标准差, 单参数); 输出格式必须与 tests/test_report.py 完全一致: "
            "'{Title}: mean={:.2f}, stddev={:.2f}'。不得修改 stats.py 的 stddev 签名, "
            "不得修改测试文件。tests/test_report.py 必须通过。"
        ),
        "seed_files": T5_SEED,
        "pre_fail": "stddev() got an unexpected keyword argument 'sample' → TypeError",
    },
    {
        "id": "T6",
        "level": 2,
        "title": "validate_age 增加类型校验 (输入校验 + 测试)",
        "objective": "加强 s6b/datavalid.py 的 validate_age 输入校验: 非 int 类型 (含 bool、字符串) 目前误判为合法年龄",
        "requirement": (
            "s6b/datavalid.py 的 validate_age(age) 必须: 非 int 类型 → False "
            "(注意 bool 是 int 子类, True/False 也应返回 False); int 且 0 <= age <= 150 → True。"
            "tests/test_datavalid.py 的 test_age 已含新增断言 ('25'、True、False 均 False), "
            "必须全部通过, 不得修改测试文件。"
        ),
        "seed_files": T6_SEED,
        "pre_fail": "validate_age('25')=True; validate_age(True)=True",
    },
    {
        "id": "T7",
        "level": 3,
        "title": "sum_list→total_of 重命名重构 (跨模块重构: A 改接口, B 适配)",
        "objective": "完成 sum_list → total_of 重命名重构: s6b/stats.py 与测试仍引用已删除的 sum_list, 全部 ImportError",
        "requirement": (
            "s6b/arithmetic.py 已将 sum_list 重命名为 total_of (签名 total_of(numbers) → float, "
            "逻辑不变); 不允许在 arithmetic.py 中保留 sum_list 别名。"
            "s6b/stats.py 必须改为导入并调用 total_of; tests/test_arithmetic.py 与 tests/test_stats.py "
            "中所有 sum_list 引用必须同步改为 total_of (不得改变测试断言语义)。"
            "全部测试必须通过。"
        ),
        "seed_files": T7_SEED,
        "pre_fail": "ImportError: cannot import name 'sum_list' (stats.py + 2 测试文件)",
    },
    {
        "id": "T8",
        "level": 3,
        "title": "新增 serializer 模块 + report 集成 (新文件 + 集成)",
        "objective": "新增 s6b/serializer.py JSON 序列化模块, 并集成到 report 模块提供 summarize_json",
        "requirement": (
            "1) 新建 s6b/serializer.py: to_json(obj, pretty=False) 用 json.dumps 序列化 "
            "(pretty=True → indent=2); from_json(text) 解析 JSON, 非法 JSON 抛 ValueError。"
            "2) s6b/report.py 新增 summarize_json(name, numbers) → 返回 dict "
            "{\"title\": title_case(name), \"mean\": mean(numbers), \"stddev\": stddev(numbers)} "
            "经 to_json 序列化后的字符串。tests/test_serializer.py 已存在, 必须全部通过, 不得修改测试文件。"
        ),
        "seed_files": T8_SEED,
        "pre_fail": "ImportError: No module named 's6b.serializer' + report 缺 summarize_json",
    },
    {
        "id": "T9",
        "level": 3,
        "title": "normalize 数据结构变更 + 全量适配 (数据结构变更)",
        "objective": "数据结构变更: stats.normalize 返回类型从 list 改为 dict 结果对象, 所有调用方与测试需适配",
        "requirement": (
            "s6b/stats.py 的 normalize(numbers) 返回类型改为 dict: "
            "{\"min\": float, \"max\": float, \"normalized\": list[float]} "
            "(空列表 → {\"min\": None, \"max\": None, \"normalized\": []}; 全相等 → normalized 全 0.0; "
            "min/max 为原列表最小/最大值)。"
            "s6b/report.py 的 summarize 必须适配新结构, 输出追加 min/max: "
            "'{Title}: mean={:.2f}, stddev={:.2f}, min={:.2f}, max={:.2f}' "
            "(mean/stddev 语义不变)。tests/test_stats.py 与 tests/test_report.py 已更新为新结构断言, "
            "必须全部通过, 不得修改测试文件。"
        ),
        "seed_files": T9_SEED,
        "pre_fail": "normalize 返回 list≠dict; summarize 缺 min/max 字段",
    },
]


def get_task(task_id: str) -> dict:
    for t in TASKS:
        if t["id"] == task_id:
            return t
    raise KeyError(task_id)

import unittest

from s6b.report import summarize


class TestReport(unittest.TestCase):
    def test_summarize(self):
        self.assertEqual(
            summarize("quarter sales", [10, 20, 30]),
            "Quarter Sales: mean=20.00, stddev=8.16",
        )


if __name__ == "__main__":
    unittest.main()

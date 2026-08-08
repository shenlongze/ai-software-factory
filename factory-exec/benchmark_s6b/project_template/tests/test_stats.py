import unittest

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

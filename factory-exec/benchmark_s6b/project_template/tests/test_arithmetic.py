import unittest

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

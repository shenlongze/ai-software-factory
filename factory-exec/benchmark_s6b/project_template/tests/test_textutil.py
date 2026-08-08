import unittest

from s6b.textutil import slugify, title_case, truncate, word_count


class TestTextUtil(unittest.TestCase):
    def test_title_case(self):
        self.assertEqual(title_case("hello world"), "Hello World")
        self.assertEqual(title_case("HELLO"), "Hello")
        self.assertEqual(title_case(""), "")

    def test_slugify(self):
        self.assertEqual(slugify("Hello World"), "hello-world")
        self.assertEqual(slugify("  Hello, World!  "), "hello-world")
        self.assertEqual(slugify("a_b_c"), "a-b-c")

    def test_truncate_default(self):
        self.assertEqual(truncate("short"), "short")
        self.assertEqual(truncate("x" * 40), "x" * 29 + "…")
        self.assertEqual(len(truncate("x" * 100)), 30)

    def test_truncate_custom(self):
        self.assertEqual(truncate("x" * 100, 10), "x" * 9 + "…")

    def test_word_count(self):
        self.assertEqual(word_count("one two three"), 3)
        self.assertEqual(word_count(""), 0)


if __name__ == "__main__":
    unittest.main()

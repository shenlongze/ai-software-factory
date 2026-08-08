import unittest

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

    def test_score(self):
        self.assertTrue(validate_score(0))
        self.assertTrue(validate_score(100))
        self.assertTrue(validate_score(85.5))
        self.assertFalse(validate_score(-0.1))
        self.assertFalse(validate_score(100.1))


if __name__ == "__main__":
    unittest.main()

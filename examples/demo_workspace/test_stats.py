import unittest
from stats import mean


class MeanTests(unittest.TestCase):
    def test_empty(self):
        with self.assertRaises(ValueError):
            mean([])

    def test_regular(self):
        self.assertEqual(mean([1, 2, 3]), 2)

    def test_negative(self):
        self.assertEqual(mean([-2, 2]), 0)

    def test_single(self):
        self.assertEqual(mean([7]), 7)


if __name__ == '__main__':
    unittest.main()

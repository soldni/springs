import unittest
from tempfile import TemporaryDirectory

from springs.memoizer import memoize


class TestMemoize(unittest.TestCase):
    def test_memoize_function(self):
        with TemporaryDirectory() as d:

            @memoize(cachedir=d)
            def add(a, b):
                return a + b

            self.assertEqual(add(1, 2), 3)
            self.assertEqual(add(1, 2), 3)

    def test_memoize_method(self):
        with TemporaryDirectory() as d:

            class Adder:
                @memoize(cachedir=d)
                def add(self, a, b):
                    return a + b

            adder = Adder()
            self.assertEqual(adder.add(1, 2), 3)
            self.assertEqual(adder.add(1, 2), 3)
            self.assertEqual(adder.add(1, 4), 5)

    def test_repeat(self):
        counter = {"calls": 0}

        with TemporaryDirectory() as d:

            @memoize(cachedir=d)
            def add(a, b):
                counter["calls"] += 1
                return a + b

            add(1, 2)
            add(1, 2)
            self.assertEqual(counter["calls"], 1)

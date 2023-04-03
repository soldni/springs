import unittest

from omegaconf.errors import ConfigTypeError

from springs.core import edit_list, from_python, merge, to_python


class TestMerge(unittest.TestCase):
    def test_merge_dicts(self):
        d1 = from_python({"a": {"c": 4, "d": 5}, "b": 2, "c": 3})
        d2 = from_python({"a": {"c": 6, "e": 7}, "b": {"f": 8}})

        d3 = merge(d1, d2)
        self.assertEqual(to_python(d3["a"]), {"c": 6, "d": 5, "e": 7})
        self.assertEqual(to_python(d3["b"]), {"f": 8})
        self.assertEqual(d3["c"], 3)

    def test_merge_lists(self):
        l1 = from_python([1, 2, 3])
        l2 = from_python([4, 5, 6])

        l3 = merge(l1, l2)

        # lists are always full overrides, not concatenation
        self.assertNotEqual(to_python(l3), [1, 2, 3, 4, 5, 6])
        self.assertEqual(to_python(l3), [4, 5, 6])

    def test_select_list(self):
        l1 = from_python([1, 2, 3])
        d1 = from_python({"0": [1, 1.1]})

        with self.assertRaises(ConfigTypeError):
            l3 = merge(l1, d1)

        l3 = edit_list(l1, d1)

        self.assertEqual(to_python(l3[0]), [1, 1.1])

        d2 = from_python({"3": [4, 4.1]})

        with self.assertRaises(IndexError):
            edit_list(l3, d2)

import pickle
import unittest

import springs as sp


@sp.dataclass
class ConfigA:
    a: int = 1


@sp.flexyclass
@sp.dataclass
class ConfigB:
    b: int = 2


class TestPickle(unittest.TestCase):
    def test_fixed_pickle(self):
        c = sp.from_dataclass(ConfigA)
        c_ = pickle.loads(pickle.dumps(c))

        self.assertEqual(c, c_)

    def test_flexy_pickle(self):
        c = sp.from_dataclass(ConfigB)
        c_ = pickle.loads(pickle.dumps(c))

        self.assertEqual(c, c_)

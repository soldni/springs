import unittest

import springs as sp


@sp.make_flexy
@sp.dataclass
class FlexyConfig:
    a: int = sp.MISSING


class TestFlexyClass(unittest.TestCase):
    def test_flexyclass(self):
        di = {"a": 1, "b": 2}
        config = sp.from_dict(
            {"_target_": sp.Target.to_string(FlexyConfig), **di}
        )
        self.assertEqual(config.a, di["a"])
        self.assertEqual(config.b, di["b"])

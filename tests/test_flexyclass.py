import unittest

import springs as sp
from springs.flexyclasses import flexy_field


@sp.make_flexy
@sp.dataclass
class FlexyConfig:
    a: int = sp.MISSING


@sp.dataclass
class FlexyConfigContainer:
    f1: FlexyConfig = FlexyConfig(a=1)
    f2: FlexyConfig = flexy_field(FlexyConfig, a=1, b=2)


class TestFlexyClass(unittest.TestCase):
    def test_flexyclass(self):
        di = {"a": 1, "b": 2}
        config = sp.from_dict(
            {"_target_": sp.Target.to_string(FlexyConfig), **di}
        )
        self.assertEqual(config.a, di["a"])
        self.assertEqual(config.b, di["b"])

    def test_flexyclass_container(self):
        config = sp.from_dataclass(FlexyConfigContainer)
        self.assertTrue(
            hasattr(config.f2, "b"), "FlexyConfigContainer.f1.b is not set"
        )

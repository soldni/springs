import unittest
from dataclasses import dataclass

from springs import MISSING, from_dataclass, from_dict, make_target
from springs.flexyclasses import flexyclass


@flexyclass
@dataclass
class FlexyConfig:
    a: int = MISSING


@dataclass
class FlexyConfigContainer:
    f1: FlexyConfig = FlexyConfig(a=1)
    f2: FlexyConfig = FlexyConfig(a=1, b=2)  # type: ignore


@flexyclass
class PipelineStepConfig:
    _target_: str = MISSING


class TestFlexyClass(unittest.TestCase):
    def test_flexyclass(self):
        di = {"a": 1, "b": 2}
        config = from_dict({"_target_": make_target(FlexyConfig), **di})
        self.assertEqual(config.a, di["a"])
        self.assertEqual(config.b, di["b"])

    def test_flexyclass_container(self):
        config = from_dataclass(FlexyConfigContainer)
        self.assertTrue(
            hasattr(config.f2, "b"), "FlexyConfigContainer.f1.b is not set"
        )

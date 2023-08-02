import unittest

import springs as sp


@sp.flexyclass
class FlexyConfig:
    a: int = sp.MISSING


@sp.dataclass
class FlexyConfigContainer:
    f1: FlexyConfig = sp.field(default_factory=lambda: FlexyConfig(a=1))
    f2: FlexyConfig = sp.field(
        default_factory=lambda: FlexyConfig(a=1, b=2)  # type: ignore
    )


@sp.flexyclass
class PipelineStepConfig:
    _target_: str = sp.MISSING


class TestFlexyClass(unittest.TestCase):
    def test_flexyclass(self):
        di = {"a": 1, "b": 2}
        config = sp.from_dict({"_target_": sp.make_target(FlexyConfig), **di})
        self.assertEqual(config.a, di["a"])
        self.assertEqual(config.b, di["b"])

    def test_flexyclass_container(self):
        config = sp.from_dataclass(FlexyConfigContainer)
        self.assertTrue(
            hasattr(config.f2, "b"), "FlexyConfigContainer.f1.b is not set"
        )

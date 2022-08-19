import unittest
from typing import Callable

from springs.core import from_dict
from springs.initialize import Target, init


class SampleClass:
    def __init__(self, a: int, b: int) -> None:
        self.a = a
        self.b = b

    def __eq__(self, __o: object) -> bool:
        if not isinstance(__o, SampleClass):
            return False
        if self.a != __o.a or self.b != __o.b:
            return False
        return True


class TestInit(unittest.TestCase):
    def test_init_now(self):
        di = {"a": 1, "b": 2}

        config = from_dict({"_target_": Target.to_string(SampleClass), **di})
        out = init.now(config, SampleClass)

        self.assertIsNotNone(out)
        self.assertEqual(out, SampleClass(**di))

    def test_init_later(self):
        di = {"a": 1, "b": 2}

        config = from_dict({"_target_": Target.to_string(SampleClass)})
        out_cls = init.later(config, SampleClass)

        self.assertIsNotNone(out_cls)
        self.assertEqual(out_cls(**di), SampleClass(**di))

    def test_init_now_with_kwargs(self):
        di = {"a": 1, "b": 2}

        config = from_dict({"_target_": Target.to_string(SampleClass)})
        out = init.now(config, SampleClass, **di)

        self.assertIsNotNone(out)
        self.assertEqual(out, SampleClass(**di))

    def test_init_warning(self):
        config = from_dict(
            {"_target_": Target.to_string(SampleClass), "a": 1, "b": 2}
        )
        with self.assertWarns(UserWarning):
            init.now(config)

    def test_init_function(self):
        config = from_dict({"_target_": "str.lower"})
        fn = init.later(config, Callable[..., str])

        self.assertEqual(fn("ABC"), "abc")

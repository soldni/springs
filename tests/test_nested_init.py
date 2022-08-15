import unittest
from dataclasses import dataclass

from springs.initialize import Target, init


class Inner:
    def __init__(self, a: int) -> None:
        self.a = a


class Outer:
    def __init__(self, a: Inner, b: int) -> None:
        self.a = a
        self.b = b


@dataclass
class InnerConfig:
    _target_: str = Target.to_string(Inner)
    a: int = 1


@dataclass
class OuterConfig:
    _target_: str = Target.to_string(Outer)
    a: InnerConfig = InnerConfig()
    b: int = 2


class TestInit(unittest.TestCase):
    def test_nested_init(self):
        config = OuterConfig()
        out = init.now(config, Outer)

        self.assertTrue(isinstance(out, Outer))
        self.assertTrue(isinstance(out.a, Inner))

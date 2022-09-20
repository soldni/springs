import pickle
import unittest
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from omegaconf import OmegaConf

from springs import DictConfig
from springs.core import merge
from springs.flexyclasses import FlexyClass


@FlexyClass.flexyclass
class ObjNestedConfig:
    bird: int = 0


@FlexyClass.flexyclass
@dataclass
class ObjConfig:
    _target_: str = "springs.core"
    nest: ObjNestedConfig = ObjNestedConfig()


@dataclass
class FooCfg:
    a: int = 1
    b: int = 2


@dataclass
class AppCfg:
    elsewhere: Optional[Any] = None
    foo: FooCfg = field(default_factory=FooCfg)
    bar: bool = False
    c: ObjConfig = ObjConfig()
    cn: Dict[str, ObjConfig] = field(default_factory=dict)


class TestNewMerge(unittest.TestCase):
    def test_first_override(self):
        override_yaml = """
        # override.yaml
        # this config file will be merged with the default
        foo: ${elsewhere}
        elsewhere:
            a: 3
            b: 4
        """

        config: DictConfig = OmegaConf.structured(AppCfg)
        out = merge(config, OmegaConf.create(override_yaml))

        self.assertEqual(out.foo.a, 3)
        self.assertEqual(out.foo.b, 4)
        self.assertEqual(out.foo, out.elsewhere)

    def test_second_override(self):
        override_yaml = """
            c:
                xxx: -42
            """

        config: DictConfig = OmegaConf.structured(AppCfg)
        out = merge(config, OmegaConf.create(override_yaml))

        self.assertEqual(out.c.xxx, -42)
        self.assertEqual(out.c._target_, "springs.core")

    def test_third_override(self):
        override_dict = {"cn": {"c_1": {**ObjConfig.defaults(), "bar": 33}}}

        config: DictConfig = OmegaConf.structured(AppCfg)
        out = merge(config, OmegaConf.create(override_dict))

        self.assertEqual(out.cn.c_1.bar, 33)
        self.assertEqual(out.cn.c_1._target_, "springs.core")
        self.assertEqual(out.cn.c_1.nest.bird, 0)
        self.assertEqual(out.c.nest.bird, 0)

        out2 = pickle.loads(pickle.dumps(out))
        self.assertEqual(out, out2)

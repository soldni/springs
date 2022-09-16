import unittest
from typing import Dict, List

from omegaconf import SI, OmegaConf
from omegaconf.errors import ValidationError

import springs as sp


@sp.dataclass
class NestedConfig:
    value: int = 0


@sp.dataclass
class Config:
    nested: NestedConfig = NestedConfig()
    li: List[NestedConfig] = sp.field(default_factory=list)
    di: Dict[str, NestedConfig] = sp.field(default_factory=dict)


class TestResolversInNested(unittest.TestCase):
    def test_list(self):
        merge_into = sp.from_dataclass(Config)
        merge_from = sp.from_dict({"li": [SI("${nested}")]})

        with self.assertRaises(ValidationError):
            # this should fail with "omegaconf.errors.ValidationError:
            # Invalid type assigned: str is not a subclass of
            # NestedConfig." see https://github.com/omry/omegaconf/issues/1005
            cfg = OmegaConf.merge(merge_into, merge_from)

        # this should work thanks to extra logic built into Springs
        cfg = sp.validate(sp.merge(merge_into, merge_from))

        self.assertEqual(sp.to_dict(cfg)["nested"], {"value": 0})
        self.assertEqual(sp.to_dict(cfg)["li"], [{"value": 0}])

    def test_dict(self):
        merge_into = sp.from_dataclass(Config)
        merge_from = sp.from_dict({"di": {"key": "${nested}"}})

        # this should work without any extra logic
        cfg = sp.resolve(OmegaConf.merge(merge_into, merge_from))

        self.assertEqual(sp.to_dict(cfg)["nested"], {"value": 0})
        self.assertEqual(sp.to_dict(cfg)["di"], {"key": {"value": 0}})


if __name__ == "__main__":
    TestResolversInNested().test_list()
    TestResolversInNested().test_dict()

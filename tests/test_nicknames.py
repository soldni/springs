import unittest

import springs as sp


@sp.dataclass
class DataConfig:
    path: str = sp.MISSING


@sp.nickname("dev_config")
@sp.dataclass
class DevConfig:
    data: DataConfig = DataConfig(path="/dev")
    name: str = "dev"
    batch_size: int = 32


class TestNicknames(unittest.TestCase):
    def test_nicknames(self):
        cfg = sp.from_dict(
            {
                "train": {
                    "data": {"path": "/train"},
                    "name": "train",
                    "batch_size": 32,
                },
                "dev": "${sp.from_node: dev_config}",
                "test": (
                    '${sp.from_node: ${train}'
                    ', "name=test", "data.path=/test"}'
                ),
            }
        )
        for name, split in cfg.items():
            self.assertEqual(split.data.path, f"/{name}")
            self.assertEqual(split.name, name)
            self.assertEqual(split.batch_size, 32)

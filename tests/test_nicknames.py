import json
import os
import unittest
from dataclasses import dataclass
from tempfile import TemporaryDirectory

from omegaconf import DictConfig

import springs as sp


@dataclass
class DataConfig:
    path: str = sp.MISSING


@sp.nickname("dev_config")
@sp.dataclass
class DevConfig:
    data: DataConfig = DataConfig(path="/dev")
    name: str = "dev"
    batch_size: int = 32


class TestNicknames(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = sp.from_dict(
            {
                "train": {
                    "data": {"path": "/train"},
                    "name": "train",
                    "batch_size": 32,
                },
                "dev": "${sp.ref: dev_config}",
                "test": (
                    "${sp.ref: ${train}" ', "name=test", "data.path=/test"}'
                ),
            }
        )

        with TemporaryDirectory() as tmpdir:
            dst = f"{tmpdir}/temp.yaml"
            with open(dst, "w") as f:
                f.write(json.dumps({"data": {"path": "/tmp"}}))
            sp.scan(path=dst, prefix="test")

            os.mkdir(f"{tmpdir}/temp")
            dst = f"{tmpdir}/temp/config.yaml"
            with open(dst, "w") as f:
                f.write(json.dumps({"data": {"path": "/tmp"}}))
            sp.scan(path=f"{tmpdir}/temp", prefix="test")

    def test_nicknames(self):
        for name, split in self.cfg.items():
            self.assertEqual(split.data.path, f"/{name}")
            self.assertEqual(split.name, name)
            self.assertEqual(split.batch_size, 32)

    def test_dict_nicknames(self):
        mod = sp.get_nickname("test/temp")
        self.assertTrue(isinstance(mod, DictConfig))
        self.assertEqual(mod.data.path, "/tmp")  # pyright: ignore

        mod2 = sp.get_nickname("test/temp/config")
        self.assertTrue(isinstance(mod2, DictConfig))
        self.assertEqual(sp.to_python(mod), sp.to_python(mod2))

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


@sp.nickname("class_nickname")
class NC:
    def __init__(self) -> None:
        self.foo = "bar"


@sp.nickname("function_nickname")
def nf(text: str = "bar"):
    return text


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

    def test_class_nickname(self):
        mod = sp.get_nickname("class_nickname")
        self.assertEqual(
            mod, sp.from_dict({"_target_": "tests.test_nicknames.NC"})
        )

        obj = sp.init.now(mod, NC)
        self.assertTrue(isinstance(obj, NC))
        self.assertEqual(obj.foo, "bar")

    def test_function_nickname(self):
        mod = sp.get_nickname("function_nickname")
        self.assertEqual(
            mod,
            sp.from_dict(
                {
                    "_target_": "tests.test_nicknames.nf",
                    "text": "bar",
                }
            ),
        )

        obj = sp.init.now(mod, str)
        self.assertEqual(obj, "bar")

        obj = sp.init.now(mod, str, text="foo")
        self.assertEqual(obj, "foo")

    def test_nickname_from_resolver(self):
        mod = sp.from_string("func: ${sp.ref:function_nickname}")
        mod = sp.resolve(mod)
        self.assertEqual(
            mod,
            sp.from_python(
                {
                    "func": {
                        "_target_": "tests.test_nicknames.nf",
                        "text": "bar",
                    }
                }
            ),
        )
        obj = sp.init.now(mod.func, str, text="foo")
        self.assertEqual(obj, "foo")

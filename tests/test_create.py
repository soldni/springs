import unittest
from tempfile import NamedTemporaryFile

from omegaconf import DictConfig, ListConfig

import springs as sp


@sp.dataclass
class DT:
    foo: str = "bar"


class TestCreation(unittest.TestCase):
    def test_from_dict(self):
        self.assertEqual(
            sp.to_dict(sp.from_dict({"foo": "bar"})), {"foo": "bar"}
        )
        self.assertEqual(sp.to_dict(sp.from_dict(None)), {})
        self.assertEqual(sp.to_dict(sp.from_dict(DictConfig({}))), {})

    def test_from_dataclass(self):
        self.assertEqual(sp.to_dict(sp.from_dataclass(DT)), {"foo": "bar"})
        self.assertEqual(sp.to_dict(sp.from_dataclass(None)), {})
        self.assertEqual(sp.to_dict(sp.from_dataclass(DictConfig({}))), {})

    def test_from_python(self):
        self.assertEqual(
            sp.to_python(sp.from_python({"foo": "bar"})), {"foo": "bar"}
        )
        self.assertEqual(
            sp.to_python(sp.from_python(None)), {}  # type: ignore
        )
        self.assertEqual(
            sp.to_python(sp.from_python(ListConfig([]))), []  # type: ignore
        )

    def test_from_file(self):
        with NamedTemporaryFile("w") as f:
            f.write("foo: bar")
            f.flush()
            self.assertEqual(sp.to_dict(sp.from_file(f.name)), {"foo": "bar"})

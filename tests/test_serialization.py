import sys
import unittest
from pathlib import Path
from tempfile import NamedTemporaryFile

from omegaconf import DictConfig

from springs import (
    from_dataclass,
    from_file,
    from_python,
    merge,
    to_json,
    to_python,
    to_yaml,
)

full_config_path = Path(__file__).parent / "fixtures/full_config"
sys.path.append(str(full_config_path))

from config import SseConfig  # type: ignore  # noqa: E402,F401


class TestFullConfig(unittest.TestCase):
    def _get_config(self) -> DictConfig:
        cfg = merge(
            from_dataclass(SseConfig),
            from_file(full_config_path / "config.yaml"),
        )

        return from_python(to_python(cfg))

    def test_yaml(self):
        cfg = self._get_config()

        with NamedTemporaryFile("r+") as f:
            f.write(to_yaml(cfg))
            f.seek(0)
            cfg2 = from_file(f.name)

            self.assertEqual(cfg, cfg2)

    def test_json(self):
        cfg = self._get_config()

        with NamedTemporaryFile("r+") as f:
            f.write(to_json(cfg))
            f.seek(0)
            cfg2 = from_file(f.name)

            self.assertEqual(cfg, cfg2)

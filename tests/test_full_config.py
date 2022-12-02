import sys
import unittest
from pathlib import Path

from springs import from_dataclass, from_file, merge, scan, to_python
from springs.commandline import load_from_file_or_nickname

full_config_path = Path(__file__).parent / "fixtures/full_config"
sys.path.append(str(full_config_path))

from config import SseConfig  # type: ignore  # noqa: E402,F401


class TestFullConfig(unittest.TestCase):
    def setUp(self) -> None:
        scan(path=full_config_path, ok_ext=["yaml"])

    def test_full_config(self):
        cfg = merge(
            from_dataclass(SseConfig),
            from_file(full_config_path / "config.yaml"),
        )

        self.assertEqual(len(cfg.data.train_splits_config), 2)
        self.assertEqual(
            cfg.data.train_splits_config[0].loader.path, "cleaned"
        )
        self.assertEqual(cfg.data.train_splits_config[1].loader.split, "train")
        self.assertEqual(
            cfg.data.valid_splits_config[0].mappers,
            cfg.data.train_splits_config[0].mappers,
        )
        self.assertEqual(len(cfg.data.valid_splits_config[0].mappers), 11)
        self.assertEqual(len(cfg.data.test_splits_config), 0)

    def test_load_from_file_or_nickname(self):
        cfg1 = load_from_file_or_nickname(full_config_path / "config.yaml")
        cfg2 = load_from_file_or_nickname("{full_config/config}")
        self.assertEqual(to_python(cfg1), to_python(cfg2))

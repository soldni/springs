import sys
import unittest
from pathlib import Path

from springs import from_dataclass, from_file, merge

full_config_path = Path(__file__).parent / "fixtures/full_config"
sys.path.append(str(full_config_path))

from config import SseConfig    # type: ignore  # noqa: E402,F401


class TestFullConfig(unittest.TestCase):
    def test_full_config(self):
        cfg = merge(
            from_dataclass(SseConfig),
            from_file(full_config_path / "config.yaml")
        )

        self.assertEqual(len(cfg.data.train_splits_config), 2)
        self.assertEqual(
            cfg.data.train_splits_config[0].loader.path, "cleaned"
        )
        self.assertEqual(
            cfg.data.train_splits_config[1].loader.split, "train"
        )
        self.assertEqual(
            cfg.data.valid_splits_config[0].mappers,
            cfg.data.train_splits_config[0].mappers
        )
        self.assertEqual(
            len(cfg.data.valid_splits_config[0].mappers),
            11
        )
        self.assertEqual(len(cfg.data.test_splits_config), 0)

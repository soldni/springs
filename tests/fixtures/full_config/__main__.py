from pathlib import Path

import springs as sp

from .config import SseConfig

sp.scan(path=Path(__file__).parent, ok_ext=["yaml"])


@sp.cli(SseConfig)
def main(_: SseConfig):
    pass


if __name__ == "__main__":
    main()

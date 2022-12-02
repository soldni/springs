from pathlib import Path
from .config import SseConfig

import springs as sp

sp.scan(path=Path(__file__).parent, ok_ext=["yaml"])


@sp.cli(SseConfig)
def main(_: SseConfig):
    pass


if __name__ == "__main__":
    main()

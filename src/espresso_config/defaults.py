import os
from datetime import datetime, timezone

from .registry import ConfigRegistry


@ConfigRegistry.add
def __fullpath__(path: str) -> str:
    if '~' in path:
        path = os.path.expanduser(path)
    path = os.path.realpath(os.path.abspath(path))
    return path

@ConfigRegistry.add
def __timestamp__(*args) -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

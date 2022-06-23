from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .core import register


@register('sp.fullpath')
def get_full_path(path: str) -> str:
    """Resolve all implicit and relative path components
    to give an absolute path to a file or directory"""
    return str(Path(path).resolve().absolute())


@register('sp.timestamp')
def get_timestamp(fmt: Optional[str] = None) -> str:
    """Returns a timestamp in the format provided; if not provided, use
    year-month-day_hour-minute-second."""

    fmt = fmt or "%Y-%m-%d_%H-%M-%S"
    return datetime.now(tz=timezone.utc).strftime(fmt)

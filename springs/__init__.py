from dataclasses import dataclass, field
from typing import Callable, Optional

from omegaconf import II, MISSING, SI

from .commandline import cli
from .core import (
    cast,
    from_dataclass,
    from_dict,
    from_file,
    from_none,
    from_options,
    from_string,
    merge,
    to_dict,
    to_yaml,
    validate,
)
from .flexyclasses import flexy_field, flexyclass, make_flexy
from .initialize import Target, init
from .logging import configure_logging
from .resolvers import all_resolvers, register
from .traversal import traverse
from .types import get_type
from .utils import SpringsWarnings


def toggle_warnings(value: Optional[bool] = None):
    SpringsWarnings.toggle(value)


def make_target(c: Callable) -> str:
    return Target.to_string(c)


__all__ = [
    "all_resolvers",
    "cast",
    "cli",
    "configure_logging",
    "dataclass",
    "field",
    "flexyclass",
    "flexy_field",
    "from_dataclass",
    "from_dict",
    "from_file",
    "from_none",
    "from_options",
    "from_string",
    "get_type",
    "II",
    "init",
    "make_flexy",
    "make_target",
    "merge",
    "MISSING",
    "register",
    "SI",
    "Target",
    "toggle_warnings",
    "to_dict",
    "to_yaml",
    "traverse",
    "validate",
]

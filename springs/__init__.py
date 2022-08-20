from dataclasses import dataclass, field
from typing import Callable, Optional, Type, TypeVar

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
from .nicknames import NicknameRegistry
from .resolvers import all_resolvers, register
from .traversal import traverse
from .types import get_type
from .utils import SpringsWarnings

T = TypeVar("T")


def toggle_warnings(value: Optional[bool] = None):
    """Shortcut for springs.utils.SpringsWarnings.toggle"""
    SpringsWarnings.toggle(value)


def make_target(c: Callable) -> str:
    """Shortcut for springs.initialize.Target.to_string"""
    return Target.to_string(c)


def nickname(name: str) -> Callable[[Type[T]], Type[T]]:
    """Shortcut for springs.nicknames.NicknameRegistry.add"""
    return NicknameRegistry.add(name)


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
    "nickname",
    "register",
    "SI",
    "Target",
    "toggle_warnings",
    "to_dict",
    "to_yaml",
    "traverse",
    "validate",
]

import importlib.metadata
from dataclasses import dataclass, field
from typing import Callable, Optional, Type, TypeVar

from omegaconf import II, MISSING, SI, DictConfig, ListConfig

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


try:
    # package has been installed, so it has a version number
    # from pyproject.toml
    __version__ = importlib.metadata.version(__package__ or __name__)
except importlib.metadata.PackageNotFoundError:
    # package hasn't been installed, so set version to "dev"
    __version__ = "dev"


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
    "DictConfig",
    "field",
    "flexy_field",
    "flexyclass",
    "from_dataclass",
    "from_dict",
    "from_file",
    "from_none",
    "from_options",
    "from_string",
    "get_type",
    "II",
    "init",
    "ListConfig",
    "make_flexy",
    "make_target",
    "merge",
    "MISSING",
    "nickname",
    "register",
    "SI",
    "Target",
    "to_dict",
    "to_yaml",
    "toggle_warnings",
    "traverse",
    "validate",
]

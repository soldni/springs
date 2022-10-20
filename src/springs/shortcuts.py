from dataclasses import field
from logging import Logger
from typing import Any, Callable, Dict, List, Optional, Type, TypeVar

from .flexyclasses import flexyclass
from .initialize import Target
from .logging import configure_logging
from .nicknames import NicknameRegistry
from .utils import SpringsConfig, SpringsWarnings

T = TypeVar("T")


def get_nickname(name: str, raise_if_missing: bool = False) -> Optional[Type]:
    """Shortcut for springs.nicknames.NicknameRegistry.get"""
    # slightly clunky but annoyingly doesn't work with typing
    if raise_if_missing:
        return NicknameRegistry.get(name)
    else:
        return NicknameRegistry.get(name, raise_if_missing=False)


def toggle_warnings(value: Optional[bool] = None):
    """Shortcut for springs.utils.SpringsWarnings.toggle"""
    SpringsWarnings.toggle(value)


def make_target(c: Callable) -> str:
    """Shortcut for springs.initialize.Target.to_string"""
    return Target.to_string(c)


def nickname(name: str) -> Callable[[Type[T]], Type[T]]:
    """Shortcut for springs.nicknames.NicknameRegistry.add"""
    return NicknameRegistry.add(name)


def make_flexy(cls_: Any) -> Any:
    """Shortcut for springs.flexyclasses.flexyclass"""

    SpringsWarnings.deprecated(
        deprecated="make_flexy",
        replacement="flexyclass",
    )
    return flexyclass(cls_)


def fdict(**kwargs: Any) -> Dict[str, Any]:
    """Shortcut for creating a Field with a default_factory that returns
    a dictionary.

    Args:
        **kwargs: values for the dictionary returned by default factory"""

    def _factory_fn() -> Dict[str, Any]:
        return {**kwargs}

    return field(default_factory=_factory_fn)


def flist(*args: Any) -> List[Any]:
    """Shortcut for creating a Field with a default_factory that returns
    a list.

    Args:
        *args: values for the list returned by default factory"""

    def _factory_fn() -> List[Any]:
        return [*args]

    return field(default_factory=_factory_fn)


def debug_logger(*args: Any, **kwargs: Any) -> Logger:
    """Shortcut for springs.utils.SpringsWarnings.debug"""
    SpringsConfig.toggle_debug(True)
    return configure_logging(*args, **kwargs)

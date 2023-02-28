import copy
from logging import Logger
from pathlib import Path
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Set,
    TypeVar,
    Union,
)

from typing_extensions import ParamSpec

from .field_utils import field
from .flexyclasses import flexyclass
from .initialize import Target
from .logging import configure_logging
from .nicknames import NicknameRegistry, RegistryValue
from .utils import SpringsConfig, SpringsWarnings

T = TypeVar("T")
P = ParamSpec("P")


def get_nickname(
    name: str, raise_if_missing: bool = False
) -> Optional[RegistryValue]:
    """Shortcut for springs.nicknames.NicknameRegistry.get"""
    # slightly clunky but annoyingly doesn't work with typing
    if raise_if_missing:
        return NicknameRegistry.get(name)
    else:
        return NicknameRegistry.get(name, raise_if_missing=False)


def toggle_warnings(value: Optional[bool] = None):
    """Shortcut for springs.utils.SpringsWarnings.toggle"""
    return SpringsWarnings.toggle(value)


def make_target(c: Callable) -> str:
    """Shortcut for springs.initialize.Target.to_string"""
    return Target.to_string(c)


def nickname(name: str) -> Callable[[T], T]:
    """Shortcut for springs.nicknames.NicknameRegistry.add"""
    return NicknameRegistry.add(name)  # type: ignore


def scan(
    path: Union[str, Path],
    prefix: Optional[str] = None,
    ok_ext: Optional[Union[Sequence[str], Set[str]]] = None,
):
    """Scan a path for valid yaml or json configurations and
    add them to the registry. This is a shortcut for calling
    springs.nicknames.NicknameRegistry.scan"""
    return NicknameRegistry.scan(path=path, prefix=prefix, ok_ext=ok_ext)


def make_flexy(cls_: Any) -> Any:
    """Shortcut for springs.flexyclasses.flexyclass"""

    SpringsWarnings.deprecated(
        deprecated="make_flexy",
        replacement="flexyclass",
    )
    return flexyclass(cls_)


def fval(value: T, **kwargs) -> T:
    """Shortcut for creating a Field with a default value.

    Args:
        value: value returned by default factory"""

    return field(default=value, **kwargs)


def fobj(object: T, **kwargs) -> T:
    """Shortcut for creating a Field with a default_factory that returns
    a specific object.

    Args:
        obj: object returned by default factory"""

    def _factory_fn() -> T:
        # make a copy so that the same object isn't returned
        # (it's a factory, not a singleton!)
        return copy.deepcopy(object)

    return field(default_factory=_factory_fn, **kwargs)


def fdict(**kwargs: Any) -> Dict[str, Any]:
    """Shortcut for creating a Field with a default_factory that returns
    a dictionary.

    Args:
        **kwargs: values for the dictionary returned by default factory"""
    return fobj(kwargs)


def flist(*args: Any) -> List[Any]:
    """Shortcut for creating a Field with a default_factory that returns
    a list.

    Args:
        *args: values for the list returned by default factory"""
    return fobj(list(args))


def debug_logger(*args: Any, **kwargs: Any) -> Logger:
    """Shortcut for springs.utils.SpringsWarnings.debug"""
    SpringsConfig.toggle_debug(True)
    return configure_logging(*args, **kwargs)

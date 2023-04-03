from collections.abc import Callable
from typing import TypeVar, overload

from omegaconf.basecontainer import BaseContainer

__all__ = ["field", "HelpLookup"]

_T = TypeVar("_T")

@overload
def field(
    default: _T,
    *,
    help: str | None = ...,
    omegaconf_ignore: bool = ...,
    **kwargs,
) -> _T: ...
@overload
def field(
    default_factory: Callable[..., _T],
    *,
    help: str | None = ...,
    omegaconf_ignore: bool = ...,
    **kwargs,
) -> _T: ...

class HelpLookup:
    def __init__(self, node: BaseContainer) -> None: ...
    def __getitem__(self, key: str) -> str | None: ...

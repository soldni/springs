from typing import Callable, Sequence, TypeVar

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from omegaconf import OmegaConf
from omegaconf.basecontainer import BaseContainer


# for return type
RegisterReturnType = TypeVar('RegisterReturnType')


def register(
    name: str,
    use_cache: bool = False
) -> Callable[[Callable[..., RegisterReturnType]],
              Callable[..., RegisterReturnType]]:

    def _register(
        func: Callable[..., RegisterReturnType]
    ) -> Callable[..., RegisterReturnType]:

        # will raise an error if the resolver is already registered
        OmegaConf.register_new_resolver(
            name=name, resolver=func, use_cache=use_cache, replace=False
        )
        return func

    return _register


def all_resolvers() -> Sequence[str]:
    return [str(k) for k in BaseContainer._resolvers.keys()]


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

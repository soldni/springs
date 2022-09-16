from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, Sequence, TypeVar, Union

from omegaconf import DictConfig, ListConfig, OmegaConf
from omegaconf.basecontainer import BaseContainer
from yaml.error import MarkedYAMLError

from .core import edit_list, from_dataclass, from_options, unsafe_merge
from .nicknames import NicknameRegistry

T = TypeVar("T")

__all__ = ["fullpath", "timestamp", "from_node"]


def register(
    name: str, use_cache: bool = False
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def _register(func: Callable[..., T]) -> Callable[..., T]:

        # will raise an error if the resolver is already registered
        OmegaConf.register_new_resolver(
            name=name, resolver=func, use_cache=use_cache, replace=False
        )
        return func

    return _register


def all_resolvers() -> Sequence[str]:
    return [str(k) for k in BaseContainer._resolvers.keys()]


@register("sp.fullpath")
def fullpath(path: str) -> str:
    """Resolve all implicit and relative path components
    to give an absolute path to a file or directory"""
    return str(Path(path).resolve().absolute())


@register("sp.timestamp")
def timestamp(fmt: Optional[str] = None) -> str:
    """Returns a timestamp in the format provided; if not provided, use
    year-month-day_hour-minute-second."""

    fmt = fmt or "%Y-%m-%d_%H-%M-%S"
    return datetime.now(tz=timezone.utc).strftime(fmt)


@register("sp.from_node")
def from_node(
    node_or_nickname: Union[DictConfig, ListConfig, str], *values: str
) -> Union[DictConfig, ListConfig]:
    """Instantiates a node from another node of a nickname to a config.

    Example:

    ```python
    import springs as sp

    cfg = sp.from_dict({
        'train': {
            'data': {'path': '/train'},
            'name': 'train',
            'bs': 32
        },
            'test': '${sp.from_node: ${train}, "name=test", "data.path=/test"}'
    })
    print(sp.to_dict(sp.validate(cfg)))

    # Prints the following
    # {'test': {'data': {'path': '/test'}, 'name': 'test', 'bs': 32},
    #  'train': {'data': {'path': '/train'}, 'name': 'train', 'bs': 32}}
    ```

    Args:
        node_or_nickname: The node or nickname to instantiate from;
            if a nickname, the node is looked up in the registry;
            if node, it must be a valid omegaconf DictConfig.
        values: The overrides to pass to the node; they must be in the
            format of command line arguments, e.g. "path.to.key=value".
    """

    if isinstance(node_or_nickname, str):
        node = from_dataclass(NicknameRegistry.get(node_or_nickname))
    elif isinstance(node_or_nickname, (DictConfig, ListConfig)):
        node = node_or_nickname
    else:
        raise TypeError(
            "node must be a reference to another node in the config or "
            "the nickname assigned to a structured config, not"
            f"not {type(node_or_nickname)}"
        )

    if not values:
        # no replacement to do!
        return node

    try:
        if not all(isinstance(v, str) for v in values):
            raise TypeError
        replace = from_options(values)
    except (MarkedYAMLError, TypeError) as e:
        raise ValueError(
            "sp.from_node overrides must be in the path.to.key=value format, "
            f"not {' '.join(values)}"
        ) from e

    # do the merging
    if isinstance(node, DictConfig):
        new_node = unsafe_merge(node, replace)
    elif isinstance(node, ListConfig):
        new_node = edit_list(node, replace)
    else:
        new_node = replace

    return new_node

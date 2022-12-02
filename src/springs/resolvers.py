import re
from dataclasses import dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence, TypeVar, Union

from omegaconf import DictConfig, ListConfig, OmegaConf
from omegaconf.basecontainer import BaseContainer
from pathvalidate import sanitize_filename
from yaml.error import MarkedYAMLError

from .core import edit_list, from_dataclass, from_options, unsafe_merge
from .nicknames import NicknameRegistry
from .utils import SpringsWarnings

T = TypeVar("T")


@dataclass
class KwResolver:
    """Simple dataclass to hold any keyword argument for a resolver.
    Must be subclassed to add any options."""

    @classmethod
    def from_args(cls, *args):
        parsed = {}
        for field, arg in zip(fields(cls), args):
            parsed[field.name] = field.type(arg)
        return cls(**parsed)


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
def timestamp(*args: Any) -> str:
    """Returns a timestamp in the format provided; if not provided, use
    year-month-day_hour-minute-second."""

    @dataclass
    class TimestampKw(KwResolver):
        fmt: str = "%Y-%m-%d_%H-%M-%S"

    options = TimestampKw.from_args(*args)

    return datetime.now(tz=timezone.utc).strftime(options.fmt)


@register("sp.sanitize")
def sanitize_path(filename: str, *args: Any) -> str:
    """Sanitize a path by replacing all invalid characters with underscores"""

    @dataclass
    class SanitizeKw(KwResolver):
        collapse: bool = True
        max_len: int = 255
        replacement_text: str = "_"
        remove_full_stop: bool = True

    options = SanitizeKw.from_args(*args)

    p = sanitize_filename(
        filename=filename,
        replacement_text=options.replacement_text,
        max_len=options.max_len,
    )

    if options.collapse:
        s = re.sub(
            rf"{options.replacement_text}+", options.replacement_text, str(p)
        )
    else:
        s = str(p)

    if options.remove_full_stop:
        s = re.sub(r"^\.+", "", s)  # leading dots
        s = re.sub(r"\.+$", "", s)  # trailing dots
        s = re.sub(r"\.+", options.replacement_text, s)  # remaining dots

    return s


@register("sp.from_node")
def from_node(
    node_or_nickname: Union[str, DictConfig, ListConfig], *args: str
):
    """Deprecate this resolver in favor of sp.ref"""
    SpringsWarnings.deprecated(deprecated="sp.from_node", replacement="sp.ref")
    return ref(node_or_nickname, *args)


@register("sp.ref")
def ref(
    node_or_nickname: Union[DictConfig, ListConfig, str], *args: str
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
            'test': '${sp.ref: ${train}, "name=test", "data.path=/test"}'
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

    if not args:
        # no replacement to do!
        return node

    try:
        if not all(isinstance(v, str) for v in args):
            raise TypeError
        replace = from_options(args)
    except (MarkedYAMLError, TypeError) as e:
        raise ValueError(
            "sp.ref overrides must be in the path.to.key=value format, "
            f"not {' '.join(args)}"
        ) from e

    # do the merging
    if isinstance(node, DictConfig):
        new_node = unsafe_merge(node, replace)
    elif isinstance(node, ListConfig):
        new_node = edit_list(node, replace)
    else:
        new_node = replace

    return new_node

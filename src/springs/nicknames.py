import inspect
import json
from dataclasses import is_dataclass
from inspect import isclass
from logging import getLogger
from pathlib import Path
from typing import (
    Callable,
    Dict,
    Literal,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    overload,
)

from omegaconf import MISSING, DictConfig, ListConfig
from typing_extensions import ParamSpec

from .core import from_dict, from_file, to_python
from .flexyclasses import FlexyClass

RegistryValue = Union[Callable, Type[FlexyClass], DictConfig, ListConfig]
# M = TypeVar("M", bound=RegistryValue)

T = TypeVar("T")
P = ParamSpec("P")


LOGGER = getLogger(__name__)


class NicknameRegistry:
    __registry__: Dict[str, RegistryValue] = {}

    @classmethod
    def scan(
        cls,
        path: Union[str, Path],
        prefix: Optional[str] = None,
        ok_ext: Optional[Union[Sequence[str], Set[str]]] = None,
    ):
        """Scan a path for valid yaml or json configurations and
        add them to the registry.

        Args:
            path (Union[str, Path]): Path to scan.
            prefix (Optional[str], optional): Prefix to add to the name of
                each configuration. For example, if the path is "test.yml" and
                the prefix is "foo", the configuration will be added to the
                registry as "foo/test". Defaults to None.
            ok_ext (Optional[Sequence[str]], optional): List of
                allowed extensions. If None, all extensions are allowed.
                Defaults to None.
        """

        path = Path(path)
        ok_ext = set(ok_ext or [])
        if path.is_file() and ok_ext and path.suffix.lstrip(".") not in ok_ext:
            # we skip this file
            return

        if not path.exists():
            raise ValueError(f"Path {path} does not exist")

        name = f"{prefix}/{path.stem}" if prefix else path.name

        if path.is_dir():
            # iterate over all non-hidden files and directories
            for child in path.iterdir():
                if child.name.startswith("."):
                    continue

                # recursively scan children
                cls.scan(path=child, prefix=name, ok_ext=ok_ext)
        else:
            try:
                # try to load the file as a configuration
                # and adding it to the registry
                config = from_file(path)
                cls._add(name, config)

            except ValueError:
                LOGGER.warning(f"Could not load config from {path}")

    @classmethod
    def _add(cls, name: str, config: RegistryValue) -> RegistryValue:
        cls.__registry__[name] = config
        return config

    @overload
    @classmethod
    def add(cls, name: str) -> Callable[[Type[T]], Type[T]]:
        ...

    @overload
    @classmethod
    def add(  # type: ignore
        cls, name: str
    ) -> Callable[[Callable[P, T]], Callable[P, T]]:
        ...

    @classmethod
    def add(
        cls, name: str
    ) -> Union[
        Callable[[Type[T]], Type[T]],
        Callable[[Callable[P, T]], Callable[P, T]],
    ]:
        """Decorator to save a structured configuration with a nickname
        for easy reuse."""

        if name in cls.__registry__:
            raise ValueError(f"{name} is already registered")

        def add_to_registry(
            cls_or_fn: Union[Type[T], Callable[P, T]]
        ) -> Union[Type[T], Callable[P, T]]:
            if is_dataclass(cls_or_fn):
                # Pylance complains about dataclasses not being a valid type,
                # but the problem is DataclassInstance is only defined within
                # Pylance, so I can't type annotate with that.
                cls._add(name, cls_or_fn)  # pyright: ignore
            elif isclass(cls_or_fn) and issubclass(cls_or_fn, FlexyClass):
                cls._add(name, cls_or_fn)
            else:
                from .initialize import Target, init

                sig = inspect.signature(cls_or_fn)
                entry = from_dict(
                    {
                        init.TARGET: Target.to_string(cls_or_fn),
                        **{
                            k: (v.default if v.default != v.empty else MISSING)
                            for k, v in sig.parameters.items()
                        },
                    }
                )
                cls._add(name, entry)
            return cls_or_fn  # type: ignore

        return add_to_registry  # type: ignore

    @overload
    @classmethod
    def get(
        cls, name: str, raise_if_missing: Literal[True] = True
    ) -> RegistryValue:
        ...

    @overload
    @classmethod
    def get(
        cls, name: str, raise_if_missing: Literal[False] = False
    ) -> Union[RegistryValue, None]:
        ...

    @classmethod
    def get(
        cls, name: str, raise_if_missing: Literal[True, False] = False
    ) -> Union[RegistryValue, None]:
        if raise_if_missing and name not in cls.__registry__:
            raise ValueError(f"{name} is not registered as a nickname")
        return cls.__registry__.get(name, None)

    @staticmethod
    def convert_nickname_value_to_string(config: RegistryValue) -> str:
        if is_dataclass(config):
            return getattr(config, "__name__", type(config).__name__)
        elif isinstance(config, (DictConfig, ListConfig)):
            return json.dumps(to_python(config), indent=2)
        else:
            return type(config).__name__

    @classmethod
    def all(cls) -> Sequence[Tuple[str, str]]:
        return [
            (name, cls.convert_nickname_value_to_string(config))
            for name, config in cls.__registry__.items()
        ]

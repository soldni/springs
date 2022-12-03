from dataclasses import is_dataclass
from inspect import isclass
from pathlib import Path
from typing import (
    Any,
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
    cast,
    overload,
)

from omegaconf import DictConfig, ListConfig

from .core import from_file
from .flexyclasses import FlexyClass
from .logging import configure_logging

RegistryValue = Union[Type[Any], Type[FlexyClass], DictConfig, ListConfig]

T = TypeVar("T")
M = TypeVar("M", bound=RegistryValue)

LOGGER = configure_logging(__name__)


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
    def _add(cls, name: str, config: M) -> M:
        cls.__registry__[name] = config
        return config

    @classmethod
    def add(cls, name: str) -> Callable[[Type[T]], Type[T]]:
        """Decorator to save a structured configuration with a nickname
        for easy reuse."""

        def add_to_registry(cls_: Type[T]) -> Type[T]:
            if not (
                is_dataclass(cls_)
                or isclass(cls_)
                and issubclass(cls_, FlexyClass)
            ):
                raise ValueError(f"{cls_} must be a dataclass")

            if name in cls.__registry__:
                raise ValueError(f"{name} is already registered")
            return cast(Type[T], cls._add(name, cls_))

        return add_to_registry

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

    @classmethod
    def all(cls) -> Sequence[Tuple[str, str]]:
        return [
            (
                name,
                str(config.__name__)
                if is_dataclass(config)
                else type(config).__name__,
            )
            for name, config in cls.__registry__.items()
        ]

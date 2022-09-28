from dataclasses import is_dataclass
from typing import (
    Callable,
    Dict,
    Literal,
    Sequence,
    Tuple,
    Type,
    TypeVar,
    Union,
    overload,
)

T = TypeVar("T")


class NicknameRegistry:
    __registry__: Dict[str, Type] = {}

    @classmethod
    def add(cls, name: str) -> Callable[[Type[T]], Type[T]]:
        """Save a configuration with a nickname for easy reuse."""

        def add_to_registry(fn: Type[T]) -> Type[T]:
            if not is_dataclass(fn):
                raise ValueError(f"{fn} must be a dataclass")

            if name in cls.__registry__:
                raise ValueError(f"{name} is already registered")
            cls.__registry__[name] = fn
            return fn

        return add_to_registry

    @overload
    @classmethod
    def get(cls, name: str, raise_if_missing: Literal[True] = True) -> Type:
        ...

    @overload
    @classmethod
    def get(
        cls, name: str, raise_if_missing: Literal[False] = False
    ) -> Union[Type, None]:
        ...

    @classmethod
    def get(
        cls, name: str, raise_if_missing: Literal[True, False] = False
    ) -> Union[Type, None]:
        if raise_if_missing and name not in cls.__registry__:
            raise ValueError(f"{name} is not registered as a nickname")
        return cls.__registry__.get(name, None)

    @classmethod
    def all(cls) -> Sequence[Tuple[str, str]]:
        return [
            (name, str(config.__name__))
            for name, config in cls.__registry__.items()
        ]

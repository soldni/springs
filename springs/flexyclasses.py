import inspect
from dataclasses import Field, dataclass, field, is_dataclass
from functools import wraps
from typing import Any, Callable, Dict, Type, TypeVar

from omegaconf import DictConfig, ListConfig, OmegaConf
from typing_extensions import dataclass_transform

from .traversal import traverse
from .types import get_type
from .warnings import warn_on_flexyclass_fn


class FlexyClass:
    ...


_T = TypeVar("_T")


@dataclass_transform(field_specifiers=(Field, field))
def make_flexy(cls_: Type[_T]) -> Type[_T]:
    """A flexyclass is like a dataclass, but it supports partial
    specification of properties."""

    if not inspect.isclass(cls_) or not is_dataclass(cls_):
        raise TypeError(f"flexyclass must decorate a dataclass, not {cls_}")

    # type ignore is for pylance, which freaks out a bit otherwise
    new_cls: Type[_T] = type(                                   # type: ignore
        f"FlexyClass{cls_.__name__}", (cls_, FlexyClass), {}    # type: ignore
    )

    return new_cls


@dataclass_transform(field_specifiers=(Field, field))
def flexyclass(cls: Type[_T]) -> Type[_T]:
    """A flexyclass is like a dataclass, but it supports partial
    specification of properties."""
    warn_on_flexyclass_fn()
    return make_flexy(dataclass(cls))


def flexyfactory(
    flexy_cls: Type[Dict[str, Any]], **kwargs: Any
) -> Dict[str, Any]:
    def factory_fn() -> Dict[str, Any]:
        return flexy_cls(**kwargs)

    return field(default_factory=factory_fn)


DictOrListConfig = TypeVar("DictOrListConfig", DictConfig, ListConfig)


def unlock_all_flexyclasses(
    cast_fn: Callable[..., DictOrListConfig]
) -> Callable[..., DictOrListConfig]:
    @wraps(cast_fn)
    def unlock_fn(*args, **kwargs):
        config_node = cast_fn(*args, **kwargs)

        for spec in traverse(
            node=config_node, include_nodes=True, include_root=True
        ):

            if not isinstance(spec.value, DictConfig):
                # only DictConfigs can be flexyclasses
                continue

            typ_ = get_type(spec.value)
            if typ_ and issubclass(typ_, FlexyClass):
                OmegaConf.set_struct(spec.value, False)

        return config_node

    return unlock_fn

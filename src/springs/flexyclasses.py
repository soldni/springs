import inspect
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Dict, Type, TypeVar

from omegaconf import DictConfig, ListConfig, OmegaConf
from typing_extensions import dataclass_transform

from .traversal import traverse
from .types import get_type


class FlexyClass:
    ...


ClsToFlex = TypeVar('ClsToFlex')


@dataclass_transform()
def flexyclass(cls: Type[ClsToFlex]) -> Type[ClsToFlex]:
    """A flexyclass is like a dataclass, but it supports partial
    specification of properties."""

    if not inspect.isclass(cls):
        raise TypeError(f'flexyclass must decorate a class, not {cls}')

    new_cls = type(f'FlexyClass{cls.__name__}',
                   (dataclass(cls), FlexyClass),
                   {})

    return new_cls


def flexyfactory(
    flexy_cls: Type[Dict[str, Any]],
    **kwargs: Any
) -> Dict[str, Any]:
    def factory_fn() -> Dict[str, Any]:
        return flexy_cls(**kwargs)
    return field(default_factory=factory_fn)


DictOrListConfig = TypeVar('DictOrListConfig', DictConfig, ListConfig)


def unlock_all_flexyclasses(
    cast_fn: Callable[..., DictOrListConfig]
) -> Callable[..., DictOrListConfig]:

    @wraps(cast_fn)
    def unlock_fn(*args, **kwargs):
        config_node = cast_fn(*args, **kwargs)

        for spec in traverse(node=config_node,
                             include_nodes=True,
                             include_root=True):

            if not isinstance(spec.value, DictConfig):
                # only DictConfigs can be flexyclasses
                continue

            typ_ = get_type(spec.value)
            if typ_ and issubclass(typ_, FlexyClass):
                OmegaConf.set_struct(spec.value, False)

        return config_node

    return unlock_fn

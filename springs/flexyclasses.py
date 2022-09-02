import inspect
from dataclasses import dataclass, field, fields, is_dataclass, make_dataclass
from functools import wraps
from typing import Any, Callable, Type, TypeVar

from omegaconf import DictConfig, ListConfig, OmegaConf
from typing_extensions import dataclass_transform

from .traversal import traverse
from .types import get_type
from .utils import SpringsWarnings

DT = TypeVar("DT")


FLEXY_FLAG = "__flexyclass__"


@dataclass_transform()
def make_flexy(cls_: Type[DT]) -> Type[DT]:
    """A flexyclass is like a dataclass, but it supports partial
    specification of properties."""

    if not inspect.isclass(cls_) or not is_dataclass(cls_):
        raise TypeError(f"flexyclass must decorate a dataclass, not {cls_}")

    setattr(cls_, FLEXY_FLAG, FLEXY_FLAG)

    return cls_  # pyright: ignore


def is_flexy(obj_or_cls: Any) -> bool:
    """Returns true if a class or configuration is flexy, false otherwise"""

    if isinstance(obj_or_cls, (DictConfig, ListConfig)):
        # case 1: we got a omega dict/list config; in this case, we use
        # the get_type function to peek inside it.
        obj_or_cls = get_type(obj_or_cls)

    if not inspect.isclass(obj_or_cls):
        # case 2: we got a generic instance of a dataclass; then we get
        # the type directly
        obj_or_cls = type(obj_or_cls)

    # finally, we look for the flag
    return hasattr(obj_or_cls, FLEXY_FLAG)


@dataclass_transform()
def flexyclass(cls: Type[DT]) -> Type[DT]:
    """A flexyclass is like a dataclass, but it supports partial
    specification of properties."""
    SpringsWarnings.flexyclass()
    return make_flexy(dataclass(cls))


def flexy_field(type_: Type[DT], /, **kwargs: Any) -> DT:
    """A flexy_ field is like dataclass.field, but it supports
    passing arbitrary keyword arguments to a flexyclass.

    Args:
        type_: The flexyclass this field is for.
        kwargs: Any keyword arguments to pass to the flexyclass.
    """
    SpringsWarnings.flexyfield()

    if not is_dataclass(type_) and not is_flexy(type_):
        raise TypeError(f"flexy_field must receive a flexyclass, not {type_}")

    # find the argument that are extra from what has been defined in
    # the flexyclass.
    known_fields = set(f.name for f in fields(type_))
    known_kwargs, extra_kwargs = {}, {}
    for k, v in kwargs.items():
        if k in known_fields:
            known_kwargs[k] = v
        else:
            extra_kwargs[k] = v

    # decorate
    if extra_kwargs:
        cls_ = make_dataclass(
            cls_name=f"{type_.__name__}_{'_'.join(extra_kwargs)}",
            fields=[
                (f_name, type(f_value), field(default_factory=lambda: f_value))
                for f_name, f_value in extra_kwargs.items()
            ],
            bases=(type_,),
        )
    else:
        cls_ = type_

    new_field: DT = field(
        default_factory=lambda: cls_(**known_kwargs)  # type: ignore
    )
    return new_field


DictOrListConfig = TypeVar("DictOrListConfig", DictConfig, ListConfig)


def unlock_all_flexyclasses(
    cast_fn: Callable[..., DictOrListConfig]
) -> Callable[..., DictOrListConfig]:
    """Unlock all flexy classes in a configuration so they can be
    merged without causing disruption."""

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
            if typ_ and is_flexy(typ_):
                OmegaConf.set_struct(spec.value, False)

        return config_node

    return unlock_fn

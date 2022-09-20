from copy import deepcopy
from dataclasses import MISSING as DT_MISSING
from dataclasses import Field, field, fields, is_dataclass
from typing import Any, Dict, Generic, Type, TypeVar

from omegaconf import MISSING as OC_MISSING
from typing_extensions import dataclass_transform

from .utils import get_annotations

C = TypeVar("C", bound=Any)


class FlexyClass(dict, Generic[C]):
    """A FlexyClass is a dictionary with some default values assigned to it
    FlexyClasses are generally not used directly, but rather creating using
    the `flexyclass` decorator.

    NOTE: When instantiating a new FlexyClass object directly, the constructor
    actually returns a `dataclasses.Field` object. This is for API consistency
    with how dataclasses are used in a structured configuration. If you want to
    access values in the FlexyClass directly, use FlexyClass.defaults property.
    """

    __origin__: type = dict
    __flexyclass_defaults__: Dict[str, Any] = {}

    @classmethod
    def _unpack_if_dataclass_field(cls, value: Any) -> Any:
        if isinstance(value, Field):
            if value.default_factory is not DT_MISSING:
                value = value.default_factory()
            elif value.default is not DT_MISSING:
                value = value.default
            else:
                value = OC_MISSING
        else:
            value = value

        if isinstance(value, dict):
            value = {
                k: cls._unpack_if_dataclass_field(v) for k, v in value.items()
            }
        elif isinstance(value, list):
            value = [cls._unpack_if_dataclass_field(v) for v in value]

        return value

    @classmethod
    def defaults(cls):
        """The default values for the FlexyClass"""

        return cls._unpack_if_dataclass_field(
            deepcopy(cls.__flexyclass_defaults__)
        )

    def __new__(cls, **kwargs):
        # We completely change how the constructor works to allow users
        # to use flexyclasses in the same way they would use a dataclass.
        factory_dict: Dict[str, Any] = {}
        factory_dict = {**cls.defaults(), **kwargs}
        return field(default_factory=lambda: factory_dict)

    @classmethod
    def flexyclass(cls, target_cls: Type[C]) -> Type["FlexyClass"]:
        """Decorator to create a FlexyClass from a class"""

        if is_dataclass(target_cls):
            attributes_iterator = ((f.name, f) for f in fields(target_cls))
        else:
            attributes_iterator = (
                (f_name, getattr(target_cls, f_name, OC_MISSING))
                for f_name in get_annotations(target_cls)
            )

        defaults = {
            f_name: cls._unpack_if_dataclass_field(f_value)
            for f_name, f_value in attributes_iterator
        }

        return type(
            target_cls.__name__,
            (FlexyClass,),
            {"__flexyclass_defaults__": defaults},
        )


@dataclass_transform()
def flexyclass(cls: Type[C]) -> Type[FlexyClass[C]]:
    """Alias for FlexyClass.flexyclass"""
    return FlexyClass.flexyclass(cls)

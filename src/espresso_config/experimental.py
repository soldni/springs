import inspect
from typing import Any, Sequence, Tuple, Type, Union

from .node import ConfigNode, ConfigParam


class MultiTypeMeta(type):
    types: Tuple[Type]

    def __subclasscheck__(cls, __subclass: type) -> bool:
        return issubclass(__subclass, cls.types)

class MultiType(metaclass=MultiTypeMeta):
    types = Tuple[Type]

    def __str__(self):
        types_repr = "|".join(repr(t) for t in self.types)
        return f'{type(self).__name__}({types_repr})'

    def __repr__(self):
        return self.__str__()

    def __instancecheck__(cls, __instance: Any) -> bool:
        return isinstance(__instance, cls.types)

    def __new__(cls, to_cast):
        if not isinstance(to_cast, cls.types):
            # we try to cast one type at the time
            for t in cls.types:
                try:
                    # we immediately return in case
                    # casting is successful
                    return t(to_cast)

                except Exception as e:
                    ...

            msg = (f'`{to_cast}` cannot be casted to ' +
                   ", ".join(t.__name__ for t in cls.types))
            raise ValueError(msg)
        return to_cast


class ConfigParamMultiType(ConfigParam):
    """A ConfigParameter that accepts multiple types.
    casting to parameters is resolved in the order they
    are provided."""
    def __init__(self, *target_types: Sequence[Type]):
        # in case target types is an iterable
        target_types = tuple(t for t in target_types)

        if len(target_types) < 1:
            raise ValueError('Must provide at least one type')

        if any(inspect.isclass(t) and issubclass(t, ConfigNode)
               for t in target_types):
            # TODO: support nested configs
            msg = (f'{type(self).__name__} does not currently accept '
                    'ConfigNode as one of the provided types.')
            raise ValueError(msg)

        self._types = target_types

    @property
    def type(self):
        target_type_repr = ', '.join(t.__name__ for t in self._types)
        return type(f'MultiType({target_type_repr})',
                    (MultiType, ),
                    {'types': self._types})

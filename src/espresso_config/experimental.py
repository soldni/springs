import inspect
from typing import Any, Sequence, Tuple, Type, Union

from .node import ConfigNode, ConfigParam


class ConfigParamMultiType(ConfigParam):
    """A ConfigParameter that accepts multiple types.
    casting to parameters is resolved in the order they
    are provided."""
    def __new__(cls, *target_types: Sequence[Type]):
        # in case target types is an iterable
        target_types = tuple(t for t in target_types)

        if len(target_types) < 1:
            raise ValueError('Must provide at least one type')

        if any(inspect.isclass(t) and issubclass(t, ConfigNode)
               for t in target_types):
            # TODO: support nested configs
            msg = (f'{cls.__name__} does not currently accept ConfigNode'
                   ' as one of the provided types.')
            raise ValueError(msg)

        class MultiTypeMeta(type):
            types: Tuple[Type]

            def __instancecheck__(cls, __instance: Any) -> bool:
                return isinstance(__instance, cls.types)

            def __subclasscheck__(cls, __subclass: type) -> bool:
                return issubclass(__subclass, cls.types)


        class MultiType(metaclass=MultiTypeMeta):
            types = target_types

            def __new__(cls, to_cast):
                if not isinstance(to_cast, cls.types):

                    # this is used to
                    exception: Union[Exception, None] = None

                    # we try to cast one type at the time,
                    # saving
                    for t in cls.types:
                        try:
                            # we immediately return in case
                            # casting is successful
                            return t(to_cast)
                        except Exception as e:
                            exception = e

                    if exception is not None:
                        raise exception

        class ConfigTypedParam(cls):
            type = MultiType
        return ConfigTypedParam

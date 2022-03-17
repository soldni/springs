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

            def __str__(self):
                types_repr = ", ".join(repr(t) for t in self.types)
                return f'{self.__class__.__name__}(types_repr)'

            def __repr__(self):
                return self.__str__()

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

        target_type_repr = ', '.join(t.__name__ for t in target_types)

        class ConfigTypedParam(cls):
            # the call to type fn is hacky, but allows this class to
            # have a custom name that includes the types
            type = type(f'MultiType({target_type_repr})', (MultiType, ), {})

        return ConfigTypedParam

import inspect
from typing import Any, Sequence, Tuple, Type, Union

from .node import ConfigNode, ConfigParam


class _MultiType:
    def __init__(self, types):
        self.types = types

    def __instancecheck__(cls, __instance: Any) -> bool:
        return isinstance(__instance, cls.types)

    def __str__(self):
        types_repr = ", ".join(repr(t) for t in self.types)
        return f'{self.__class__.__name__}({types_repr})'

    def __repr__(self):
        return self.__str__()

    def __call__(self, to_cast):
        if not isinstance(to_cast, self.types):

            # this is used to throw an exception if we
            # cant cast. We can't immediately throw an exception,
            # we need to try to cast to all types before giving up
            exception: Union[Exception, None] = None

            # we try to cast one type at the time
            for t in self.types:
                try:
                    # we immediately return in case
                    # casting is successful
                    return t(to_cast)
                except Exception as e:
                    exception = e

            if exception is not None:
                raise exception



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

        self.type = _MultiType(target_types)

import inspect
from typing import Callable, Type, Union

from .node import ConfigNode


RegistrableType = Union[Type[ConfigNode], Callable]


class MetaConfigRegistry(Type):
    def __contains__(cls, name) -> bool:
        return name in getattr(cls, '__registry__', {})


class ConfigRegistry(metaclass=MetaConfigRegistry):
    __registry__ = {}

    @classmethod
    def add(cls: Type['ConfigRegistry'],
            config_node_cls: RegistrableType) -> RegistrableType:
        is_node_config = (inspect.isclass(config_node_cls) and
                          issubclass(config_node_cls, ConfigNode))
        is_callable = isinstance(config_node_cls, Callable)

        if not(is_node_config or is_callable):
            msg = (f'`config_node_cls` must be a ConfigNode '
                   f'class or callable fn, not `{type(config_node_cls)}`')
            raise TypeError(msg)

        name = config_node_cls.__name__

        if name in cls.__registry__:
            raise ValueError(f'A config of name "{name}" already exists')

        cls.__registry__[name] = config_node_cls
        return config_node_cls

    @classmethod
    def get(cls: Type['ConfigRegistry'], name: str) -> RegistrableType:
        if name not in cls.__registry__:
            raise KeyError(f'`{name}` is not in the registry')
        return cls.__registry__[name]

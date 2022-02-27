from functools import singledispatchmethod
import inspect
from typing import Type, Callable, Generic, TypeVar, Union

from espresso_config.node import ConfigNode

CR = TypeVar('CR', bound='ConfigRegistry')


class ConfigRegistry(Generic[CR]):
    __registry__ = {}

    @classmethod
    def add(cls, config_node_cls: Type[ConfigNode]) -> ConfigNode:
        if not(inspect.isclass(config_node_cls) and
               issubclass(config_node_cls, ConfigNode)):
            msg = (f'`config_node_cls` must be a ConfigNode '
                   f'class, not `{type(config_node_cls)}`')
            raise TypeError(msg)

        name = config_node_cls.__name__

        if name in cls.__registry__:
            raise ValueError(f'A config of name "{name}" already exists')

        cls.__registry__[name] = config_node_cls
        return config_node_cls

    @classmethod
    def get(cls, name: str) -> ConfigNode:
        if name not in cls.__registry__:
            raise KeyError(f'`{name}` is not in the registry')
        return cls.__registry__[name]

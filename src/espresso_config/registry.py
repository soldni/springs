import inspect
from typing import Callable, Generic, Type, TypeVar, Union

from .functional import config_from_dict
from .node import ConfigNode, ConfigParam

CR = TypeVar('CR', bound='ConfigRegistry')
RegistrableType = Union[Type[ConfigNode],Callable]


class ConfigRegistry(Generic[CR]):
    __registry__ = {}

    @classmethod
    def add(cls, config_node_cls: RegistrableType) -> ConfigNode:
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
    def get(cls, name: str) -> ConfigNode:
        if name not in cls.__registry__:
            raise KeyError(f'`{name}` is not in the registry')
        return cls.__registry__[name]

    @classmethod
    def auto(cls, cls_: type) -> ConfigNode:

        # import here to avoid circular imports
        from .instantiate import instantiate

        # get specs for this class
        module = inspect.getmodule(cls_)
        spec = inspect.getfullargspec(cls_)

        # exclude self
        param_names = spec.args[1:]
        param_defaults = spec.defaults or []

        param_annotations = {k: ConfigParam(v) for k, v
                             in spec.annotations.items()}
        param_annotations[instantiate.TARGET] = ConfigParam(str)

        # we need to zip from the back because kwargs are always at
        # the end! So if only 2 out of 4 parameters have keyword args,
        # spec.defaults will be of length 2, but param_names will be
        # of length 4, which the keyword'ed arguments being the last
        # 2. Therefore, we iterate from the back both lists; zip will
        # take care of zipping to the shortest.
        param_defaults = dict(zip(param_names[::-1], param_defaults[::-1]))

        if module.__name__ == '__main__':
            msg = ('Cannot auto-generate configurations for '
                   f'`{cls_}` because it is in __main__.')
            raise ValueError(msg)

        # setting up the default _target_ here for autoinstantiation.
        param_defaults[instantiate.TARGET] = \
            f'{module.__name__}.{cls_.__name__}'

        config_cls = config_from_dict.cls(config=param_defaults,
                                          annotations=param_annotations,
                                          name=cls_.__name__)

        # After adding the configuration to the registry, we
        # simply return the class itself
        cls.add(config_cls)
        return cls_

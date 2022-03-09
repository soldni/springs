import inspect
from typing import Type, Callable, Generic, TypeVar, Union

from espresso_config.node import ConfigNode, ConfigParam

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
        # get specs for this class
        module = inspect.getmodule(cls_)
        spec = inspect.getfullargspec(cls_)

        # exclude self
        param_names = spec.args[1:]

        # we need to zip from the back because kwargs are always at
        # the end! So if only 2 out of 4 parameters have keyword args,
        # spec.defaults will be of length 2, but param_names will be
        # of length 4, which the keyword'ed arguments being the last
        # 2. Therefore, we iterate from the back both lists; zip will
        # take care of zipping to the shortest.
        param_defaults = dict(zip(param_names[::-1], spec.defaults[::-1]))

        # setting up the default _target_ here for autoinstantiation.
        param_defaults['_target_'] = f'{module.__name__}.{cls_.__name__}'

        # Small function to let us look up a suitable type for a
        # parameter by either looking at type annotations, or by
        # checking the defaults; if anything fails; return a no-op
        # lambda as pseudo-default.
        def _get_ann(p_name: str) -> Callable:
            if p_name in spec.annotations:
                return spec.annotations[p_name]
            if p_name in param_defaults:
                return type(param_defaults[p_name])
            else:
                return lambda p_value: p_value

        # setting up type annotations, including for target
        param_annotations = {p: ConfigParam(_get_ann(p))
                             for p in param_names}
        param_annotations['_target_'] = ConfigParam(str)

        # get node class and set up defaults and annotations
        node_cls = type(cls_.__name__, (ConfigNode,), {})
        [setattr(node_cls, p, d) for p, d in param_defaults.items()]
        setattr(node_cls, '__annotations__', param_annotations)

        # add new node to registry and return it
        return cls.add(node_cls)

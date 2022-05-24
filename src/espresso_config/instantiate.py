import copy
import functools
import importlib
import inspect
import itertools

from typing import Any, Callable, Dict, Sequence, Type, Union

from yaml import warnings

from .exceptions import ConfigInstantiateError
from .utils import clean_multiline
from .parser import YamlParser
from .node import ConfigNode, ConfigFlexNode


class InitLater(functools.partial):
    def get_kw(self: 'InitLater', *args, **kwargs):
        """Shortcut for accessing parameters that have been
        provided to an InitLater object"""
        return self.keywords.get(*args, **kwargs)

    def pop_kw(self: 'InitLater', *args, **kwargs):
        """Shortcut for popping parameters that have been
        provided to an InitLater object"""
        return self.keywords.pop(*args, **kwargs)

    @staticmethod
    def _no_op():
        ...

    @classmethod
    def no_op(cls: Type['InitLater']) -> 'InitLater':
        """Create an init later that does nothing.
        Useful for when trying to instantiate from None."""
        return cls(cls._no_op)

    def __bool__(self: 'InitLater') -> bool:
        # this allows us to check if the InitLater object
        # is "True" (that is, it is a real wrapped function),
        # or if it is "False" (it's a no-op)
        return self.func != self._no_op

    def __call__(self: 'InitLater', /, *args, **kwargs):
        # recursively call deferred initialization if
        # we encounter another InitLater
        args = [v() if isinstance(v, InitLater) else v
                for v in itertools.chain(self.args, args)]
        kwargs = {k: v() if isinstance(v, InitLater) else v
                  for k, v in {**self.keywords, **kwargs}.items()}
        try:
            return self.func(*args, **kwargs)
        except Exception as e:
            ex_name = type(e).__name__
            fn_name = repr(self.func)
            msg = clean_multiline(f'''
                An error occurred while trying to initialize {fn_name}
                with arguments "{args}" and kwargs "{kwargs}":
                {ex_name}("{' '.join(map(str, e.args))}")
            ''')
            raise ConfigInstantiateError(msg).with_traceback(e.__traceback__)


@YamlParser.register()
class TargetType:
    @staticmethod
    def is_module(path: str) -> bool:
        try:
            spec = importlib.util.find_spec(path)
            return spec is not None
        except ModuleNotFoundError:
            return False

    def __repr__(self: 'TargetType') -> str:
        return f'{type(self).__name__}({str(self)})'

    def __str__(self: 'TargetType') -> str:
        return self.to_yaml(self)

    @classmethod
    def to_yaml(cls: Type['TargetType'], target_type_obj: 'TargetType') -> str:
        callable_ = target_type_obj.callable
        if inspect.isclass(callable_):
            object_name = callable_.__name__
            module_name = inspect.getmodule(callable_).__name__
        else:
            if hasattr(callable_, '__self__'):
                # method of a function
                module_name = inspect.getmodule(callable_.__self__).__name__
                object_name = '{}.{}'.format(
                    callable_.__self__.__name__ if
                    inspect.isclass(callable_.__self__)
                    else callable_.__self__.__class__.__name__,
                    callable_.__name__
                )
            else:
                module_name = inspect.getmodule(callable_).__name__
                object_name = callable_.__name__

        return f'{module_name}.{object_name}'

    @classmethod
    def get_callable(cls: Type['TargetType'], path: str) -> Callable:
        if cls.is_module(path):
            return importlib.import_module(path)
        elif '.' in path:
            m_name, c_name = path.rsplit('.', 1)
            if cls.is_module(m_name):
                container = importlib.import_module(m_name)
            else:
                container = cls.get_callable(m_name)
            callable_ = getattr(container, c_name, None)
        else:
            callable_ = globals().get(path, __builtins__.get(path, None))

        if callable_ is None:
            raise ImportError(f'Cannot find callable at {path}')

        return callable_

    def __init__(self: 'TargetType', path_or_callable: Union[str, Callable]):
        if isinstance(path_or_callable, str):
            path_or_callable = self.get_callable(path_or_callable)
        self.callable = path_or_callable

    def __call__(self, *args, **kwargs):
        return self.callable(*args, **kwargs)


class init:
    TARGET: str = '_target_'

    @classmethod
    def callable(cls: Type['init'],
                 config: Union[Dict[str, Any], ConfigNode]) -> Callable:

        if not isinstance(config, ConfigNode):
            # in case the config is not a configuration node, but a
            # simple dictionary, we attempt making a config node.
            try:
                config = ConfigFlexNode(config)
            except Exception as e:
                msg = f'Cannot get config from object of type `{type(config)}`'
                raise ValueError(msg) from e

        try:
            target = config[cls.TARGET]
        except KeyError:
            raise KeyError(f'Config `{config}` has no `{cls.TARGET}` key!')

        if not isinstance(target, TargetType):
            target = TargetType(target)

        return target

    @classmethod
    def later(
        cls: Type['init'],
        config: Union[Dict[str, Any], ConfigNode, None] = None,
        _recursive_: bool = True,
        **kwargs: Dict[str, Any]
    ) -> InitLater:
        """Return a InitLater object to be used to instantitate a
        new class or call a function"""

        # if no config is provided, we return a function
        if config is None:
            return InitLater.no_op()

        config_node = (ConfigFlexNode(config)
                       if isinstance(config, dict) else
                       copy.deepcopy(config))

        if len(kwargs) > 0:
            config_node = config_node << ConfigFlexNode(kwargs)

        if cls.TARGET not in config_node:
            msg = (f'Cannot instantiate from `{config_node}`: '
                   f'`{cls.TARGET}` keyword missing')
            raise ValueError(msg)

        fn = cls.callable(config_node)

        def _recursive_init(param):
            must_recursive_init = (_recursive_ and
                                   isinstance(param, (ConfigNode, dict))
                                   and cls.TARGET in param)
            if must_recursive_init:
                param = cls.later(config=param, _recursive_=True)
            return param

        init_call_dict = {k: _recursive_init(v) for k, v in config_node
                          if k != cls.TARGET}

        return InitLater(fn, **init_call_dict)

    @classmethod
    def now(
        cls: Type['init'],
        config: Union[ConfigNode, dict] = None,
        _recursive_: bool = True,
        **kwargs: Dict[str, Any]
    ) -> object:
        """Create a later, but initialize it now!"""

        if config is None:
            return None

        return cls.later(config=config, _recursive_=_recursive_, **kwargs)()

    def __new__(cls: Type['init'],
                *args: Sequence[Any],
                **kwargs: Dict[str, Any]) -> object:
        """Alias for `init.now`"""
        return cls.now(*args, **kwargs)


class instantiate(init):

    @staticmethod
    def _deprecation_warning() -> None:
        raise warnings.warn('`instantiate` is deprecated, use `init` instead')

    @classmethod
    def now(cls, *args, **kwargs):
        cls._deprecation_warning()
        return super().now(*args, **kwargs)

    @classmethod
    def later(cls, *args, **kwargs):
        cls._deprecation_warning()
        return super().later(*args, **kwargs)

    @classmethod
    def callable(cls, *args, **kwargs):
        cls._deprecation_warning()
        return super().callable(*args, **kwargs)

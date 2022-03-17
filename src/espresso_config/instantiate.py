import copy
import functools
import importlib
import itertools
from typing import Any, Callable, Dict, Sequence, Type, TypeVar, Union

from .functional import config_from_dict
from .node import ConfigNode, ConfigNodeProps, Generic

IT = TypeVar('IT', bound='InitLater')
GC = TypeVar('GC', bound='get_callable')
IN = TypeVar('IN', bound='instantiate')


class InitLater(functools.partial, Generic[IT]):
    def get_kw(self, *args, **kwargs):
        """Shortcut for accessing parameters that have been
        provided to an InitLater object"""
        return self.keywords.get(*args, **kwargs)

    def pop_kw(self, *args, **kwargs):
        """Shortcut for popping parameters that have been
        provided to an InitLater object"""
        return self.keywords.pop(*args, **kwargs)

    @staticmethod
    def _no_op():
        ...

    @classmethod
    def no_op(cls) -> IT:
        """Create an init later that does nothing.
        Useful for when trying to instantiate from None."""
        return cls(cls._no_op)

    def __bool__(self) -> bool:
        # this allows us to check if the InitLater object
        # is "True" (that is, it is a real wrapped function),
        # or if it is "False" (it's a no-op)
        return self.func != self._no_op

    def __call__(self, /, *args, **kwargs):
        # recursively call deferred initialization if
        # we encounter another InitLater
        args = [v() if isinstance(v, InitLater) else v
                for v in itertools.chain(self.args, args)]
        kwargs = {k: v() if isinstance(v, InitLater) else v
                    for k, v in {**self.keywords, **kwargs}.items()}
        try:
            return self.func(*args, **kwargs)
        except Exception as e:
            msg = (f'An error occurred while trying to '
                   f'initialize {self.func.__name__} with '
                   f'arguments {args} and kwargs {kwargs}.')
            raise type(e)(msg) from e



class get_callable:
    @staticmethod
    def is_module(path: str) -> bool:
        try:
            spec = importlib.util.find_spec(path)
            return spec is not None
        except ModuleNotFoundError:
            return False

    @classmethod
    def _get_callable(cls: Type[GC], path: str) -> Callable:
        if cls.is_module(path):
            return importlib.import_module(path)
        elif '.' in path:
            m_name, c_name = path.rsplit('.', 1)
            if cls.is_module(m_name):
                container = importlib.import_module(m_name)
            else:
                container = get_callable(m_name)
            return getattr(container, c_name)
        else:
            return globals().get(path, __builtins__.get(path, None))

    def __new__(cls: Type[GC], path: str) -> Callable:
        cl_ = cls._get_callable(path)

        if cl_ is None:
            raise ModuleNotFoundError(f'Could not find `{path}`')
        return cl_


class instantiate:
    TARGET: str = '_target_'

    @classmethod
    def later(
        cls: Type[IN],
        config: Union[Dict[str, Any], ConfigNode, None] = None,
        _recursive_: bool = True,
        **kwargs: Dict[str, Any]
    ) -> InitLater:
        """Return a InitLater object to be used to instantitate a
        new class or call a function"""

        # if no config is provided, we return a function
        if config is None:
            return InitLater.no_op()

        config_node = (config_from_dict(config, flex=True)
                       if isinstance(config, dict) else
                       copy.deepcopy(config))

        if len(kwargs) > 0:
            config_node = config_node << config_from_dict(kwargs, flex=True)

        if cls.TARGET not in config_node:
            msg = (f'Cannot instantiate from `{config_node}`: '
                   f'`{cls.TARGET}` keyword missing')
            raise ValueError(msg)

        _target_ = ConfigNodeProps.get_props(config_node).pop(cls.TARGET)
        fn = get_callable(_target_)

        def _recursive_init(param):
            if (_recursive_ and
                isinstance(param, (ConfigNode, dict))
                and cls.TARGET in param):
                param = cls.later(config=param, _recursive_=True)
            return param

        init_call_dict = {k: _recursive_init(v) for k, v in config_node}

        return InitLater(fn, **init_call_dict)

    @classmethod
    def now(
        cls: Type[IN],
        config: Union[ConfigNode, dict] = None,
        _recursive_: bool = True,
        **kwargs: Dict[str, Any]
    ) -> object:
        """Create a later, but initialize it now!"""

        if config is None:
            return None

        return cls.later(config=config, _recursive_=_recursive_, **kwargs)()

    def __new__(cls: Type[IN],
                *args: Sequence[Any],
                **kwargs: Dict[str, Any]) -> object:
        """Alias for `instantitate.now`"""
        return cls.now(*args, **kwargs)

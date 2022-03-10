import copy
import importlib
import functools
from typing import Any, Dict, TypeVar, Union

from .node import ConfigNodeProps, ConfigNode, Generic
from .functional import config_from_dict


IT = TypeVar('IT', bound='InitLater')

class InitLater(functools.partial, Generic[IT]):
    def get_kw(self, *args, **kwargs):
        """Shortcut for accessing parameters that have been
        provided to an InitLater object"""
        return self.keywords.get(*args, **kwargs)

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

    def __call__(self, /, *args, **keywords):
        # recursively call deferred initialization if
        # we encounter another InitLater
        args = [v() if isinstance(v, InitLater) else v for v in args]
        keywords = {k: v() if isinstance(v, InitLater) else v
                    for k, v in {**self.keywords, **keywords}.items()}
        return self.func(*self.args, *args, **keywords)


class get_callable:
    @staticmethod
    def is_module(path):
        try:
            spec = importlib.util.find_spec(path)
            return spec is not None
        except ModuleNotFoundError:
            return False

    @classmethod
    def _get_callable(cls, path):
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

    def __new__(cls, path):
        cl_ = cls._get_callable(path)

        if cl_ is None:
            raise ModuleNotFoundError(f'Could not find `{path}`')
        return cl_


class instantitate:
    TARGET = '_target_'

    @classmethod
    def later(
        cls,
        config: Union[Dict[str, Any], ConfigNode, None] = None,
        _recursive_: bool = True,
        **kwargs
    ) -> InitLater:
        """Return a InitLater object to be used to instantitate a
        new class or call a function"""

        # if no config is provided, we return a functino
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
        cls,
        config: Union[ConfigNode, dict] = None,
        _recursive_: bool = True,
        **kwargs
    ) -> object:
        """Create a later, but initialize it now!"""

        if config is None:
            return None

        return cls.later(config=config, _recursive_=_recursive_, **kwargs)()

    def __new__(cls, *args, **kwargs) -> object:
        """Alias for `instantitate.now`"""
        return cls.now(*args, **kwargs)

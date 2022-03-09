import copy
import importlib
import functools
from typing import Any, Callable, Dict, Type, TypeVar, Union

from .node import ConfigNodeProps, ConfigNode


class InitLater(functools.partial):
    def get_kw(self, *args, **kwargs):
        return self.keywords.get(*args, **kwargs)

    def __bool__(self) -> bool:
        return len(self.keywords) > 0

    def __call__(self, /, *args, **keywords):
        # recursively call deferred initialization if
        # we encounter another InitLater
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

    @staticmethod
    def _no_op():
        ...

    @classmethod
    def later(
        cls,
        config: Dict[str, Any] = None,
        _recursive_: bool = True,
        **kwargs
    ) -> InitLater:
        """For now we use hydra instead of doing the lookup ourselves;
        we will fix it later"""
        if config is None:
            return InitLater(cls._no_op)

        if isinstance(config, ConfigNode):
            params = ConfigNodeProps.get_props(config).to_dict()
        elif isinstance(config, dict):
            params = copy.deepcopy(config)
        else:
            msg = (f'`config` is of type `{type(config)}`, '
                   'but it should be `ConfigNode` or dict.')
            raise TypeError(msg)

        # merge overrides and parameters from config here.
        params.update(kwargs)

        if cls.TARGET not in params:
            msg = f'Cannot instantiate from `{params}`: `{cls.TARGET}` keyword missing'
            raise ValueError(msg)

        fn = get_callable(params.pop(cls.TARGET))
        if _recursive_:
            params = {k: (cls.later(config=v, _recursive_=True)
                          if (isinstance(v, dict) and cls.TARGET in v)
                          else v)
                     for k, v in params.items()}

        return InitLater(fn, **params)

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

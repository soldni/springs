import copy
import importlib
import functools
from typing import Any, Callable, Dict, Type, TypeVar, Union

from .node import ConfigNodeProps, ConfigNode
from .functional import config_from_dict


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
        config: Union[Dict[str, Any], ConfigNode, None] = None,
        _recursive_: bool = True,
        **kwargs
    ) -> InitLater:
        """For now we use hydra instead of doing the lookup ourselves;
        we will fix it later"""
        if config is None:
            return InitLater(cls._no_op)

        config = (config_from_dict(config, flex=True)
                  if isinstance(config, dict) else
                  copy.deepcopy(config))

        if len(kwargs) > 0:
            config = config << config_from_dict(kwargs, flex=True)

        if cls.TARGET not in config:
            msg = f'Cannot instantiate from `{config}`: `{cls.TARGET}` keyword missing'
            raise ValueError(msg)

        fn = get_callable(ConfigNodeProps.get_props(config).pop(cls.TARGET))

        def _recursive_init(param):
            if (_recursive_ and
                isinstance(param, (ConfigNode, dict))
                and cls.TARGET in param):
                param = cls.later(config=param, _recursive_=True)
            return param

        init_call_dict = {k: _recursive_init(v) for k, v in config}

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

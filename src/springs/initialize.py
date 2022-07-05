import functools
import importlib
import importlib.util
import inspect
import itertools
from typing import Any, Callable, Optional, Protocol, Type, TypeVar

from omegaconf import DictConfig

from .core import ConfigType, cast, merge
from .utils import clean_multiline


class InitLater(functools.partial):

    # inherits slots from functools.partial
    __slots__ = "type_",

    def __new__(cls, func, type_: Optional[type] = None, /, *args, **keywords):
        cl = super().__new__(cls, func, *args, **keywords)
        cl.type_ = type_
        return cl

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
        args = tuple(v() if isinstance(v, InitLater) else v
                     for v in itertools.chain(self.args, args))
        kwargs = {k: v() if isinstance(v, InitLater) else v
                  for k, v in {**self.keywords, **kwargs}.items()}
        try:
            out = self.func(*args, **kwargs)

            # if type is provided, then we check if the object that
            # has been initialized here is of the expected type.
            # note that this only works for top-level init, and
            # does not recursively check.

            # there are some exceptions, for example we do type check
            # iff we have received a class, and the class is not a protocol
            do_type_check = (
                self.type_ is not None
                and inspect.isclass(self.type_)
                and not isinstance(self.type_, Protocol)
            )

            if do_type_check and not isinstance(out, self.type_):
                msg = (f"Initialized object `{out}` is not the right type: "
                       f"expected `{self.type_}`, got {type(out)}")
                raise TypeError(msg)

            return out
        except Exception as e:
            ex_name = type(e).__name__
            fn_name = repr(self.func)
            msg = clean_multiline(f'''
                An error occurred while trying to initialize {fn_name}
                with arguments "{args}" and kwargs "{kwargs}":
                {ex_name}("{' '.join(map(str, e.args))}")
            ''')
            raise RuntimeError(msg).with_traceback(e.__traceback__)


class Target:
    @staticmethod
    def _is_module(path: str) -> bool:
        try:
            spec = importlib.util.find_spec(path)
            return spec is not None
        except ModuleNotFoundError:
            return False

    @classmethod
    def to_string(cls: Type['Target'], callable: Any) -> str:
        if inspect.isclass(callable):
            return f'{callable.__module__}.{callable.__name__}'
        elif inspect.ismethod(callable):
            return f'{cls.to_string(callable.__self__)}.{callable.__name__}'
        elif inspect.isfunction(callable):
            return f'{callable.__module__}.{callable.__name__}'
        else:
            raise TypeError(f'`{callable}` is not a callable')

    @classmethod
    def from_string(cls: Type['Target'], path: str) -> Any:
        if cls._is_module(path):
            return importlib.import_module(path)
        elif '.' in path:
            m_name, c_name = path.rsplit('.', 1)
            if cls._is_module(m_name):
                container = importlib.import_module(m_name)
            else:
                container = cls.from_string(m_name)
            callable_ = getattr(container, c_name, None)
        else:
            callable_ = globals().get(path, getattr(__builtins__, path, None))

        if callable_ is None:
            raise ImportError(f'Cannot find callable at {path}')

        return callable_


InitT = TypeVar('InitT')
CallableT = TypeVar('CallableT', bound=Callable)


class init:
    TARGET: str = '_target_'

    @classmethod
    def callable(cls: Type['init'],
                 config: ConfigType,
                 _type_: Optional[CallableT] = None) -> CallableT:

        config = cast(config)

        try:
            target: str = config[cls.TARGET]
        except KeyError:
            raise KeyError(f'Config `{config}` has no `{cls.TARGET}` key!')

        return Target.from_string(target)

    @classmethod
    def later(
        cls: Type['init'],
        config: Optional[ConfigType] = None,
        _type_: Optional[Type[InitT]] = None,
        _recursive_: bool = True,
        **kwargs: Any
    ) -> Callable[..., InitT]:
        """Return a InitLater object to be used to instantiate a
        new class or call a function"""

        # if no config is provided, we return a function
        if config is None:
            return InitLater.no_op()

        config_node = cast(config)

        if len(kwargs) > 0:
            config_node = merge(config_node, cast(kwargs))

        if cls.TARGET not in config_node:
            msg = (f'Cannot instantiate from `{config_node}`: '
                   f'`{cls.TARGET}` keyword missing')
            raise ValueError(msg)

        fn = cls.callable(config_node)      # type: ignore

        def _recursive_init(param):
            must_recursive_init = (_recursive_ and
                                   isinstance(param, (DictConfig, dict))
                                   and cls.TARGET in param)
            if must_recursive_init:
                param = cls.later(config=param, _recursive_=True)
            return param

        init_call_dict = {str(k): _recursive_init(v)
                          for k, v in config_node.items()
                          if k != cls.TARGET}

        return InitLater(fn, _type_, **init_call_dict)

    @classmethod
    def now(
        cls: Type['init'],
        config: Optional[ConfigType] = None,
        _type_: Optional[Type[InitT]] = None,
        _recursive_: bool = True,
        **kwargs: Any
    ) -> InitT:
        """Create a later, but initialize it now!"""
        init_call = cls.later(config=config,
                              _type_=_type_,
                              _recursive_=_recursive_,
                              **kwargs)
        return init_call()

    def __new__(
        cls: Type['init'],
        config: Optional[ConfigType] = None,
        _type_: Optional[Type[InitT]] = None,
        _recursive_: bool = True,
        **kwargs: Any
    ) -> InitT:
        """Alias init(...) to init.now(...)"""
        return cls.now(config=config,
                       _type_=_type_,
                       _recursive_=_recursive_,
                       **kwargs)

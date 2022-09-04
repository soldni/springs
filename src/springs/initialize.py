import functools
import importlib
import importlib.util
import inspect
import itertools
from dataclasses import is_dataclass
from types import ModuleType
from typing import (
    Any,
    Callable,
    Generic,
    Optional,
    Type,
    TypeVar,
    Union,
    overload,
)

from get_annotations import get_annotations
from omegaconf import DictConfig, OmegaConf

from .core import cast
from .utils import SpringsWarnings, clean_multiline


class InitLater(functools.partial):

    # inherits slots from functools.partial
    __slots__ = ("type_",)

    # must be explicitly defined to avoid mypy error
    type_: Union[Type[Any], None]

    def __new__(
        cls,
        func: Callable,
        _type_: Optional[type] = None,
        /,
        *args,
        **keywords,
    ):
        cl = super().__new__(cls, func, *args, **keywords)
        cl.type_ = _type_
        return cl

    def get_kw(self: "InitLater", *args, **kwargs) -> Any:
        """Shortcut for accessing parameters that have been
        provided to an InitLater object"""
        return self.keywords.get(*args, **kwargs)

    def pop_kw(self: "InitLater", *args, **kwargs) -> Any:
        """Shortcut for popping parameters that have been
        provided to an InitLater object"""
        return self.keywords.pop(*args, **kwargs)

    @staticmethod
    def _no_op():
        ...

    @classmethod
    def no_op(cls: Type["InitLater"]) -> "InitLater":
        """Create an init later that does nothing.
        Useful for when trying to instantiate from None."""
        return cls(cls._no_op)

    def __bool__(self: "InitLater") -> bool:
        # this allows us to check if the InitLater object
        # is "True" (that is, it is a real wrapped function),
        # or if it is "False" (it's a no-op)
        return self.func != self._no_op

    def __call__(self: "InitLater", /, *args, **kwargs):
        # recursively call deferred initialization if
        # we encounter another InitLater
        args = tuple(
            v() if isinstance(v, InitLater) else v
            for v in itertools.chain(self.args, args)
        )
        kwargs = {
            k: v() if isinstance(v, InitLater) else v
            for k, v in {**self.keywords, **kwargs}.items()
        }
        try:
            out = self.func(*args, **kwargs)

            # if type is provided, then we check if the object that
            # has been initialized here is of the expected type.
            # note that this only works for top-level init, and
            # does not recursively check.

            try:
                # We only type check if the type is provided
                if self.type_ is not None:
                    type_check_out = isinstance(out, self.type_)
                else:
                    type_check_out = True
            except TypeError:
                # Instance check fails if we can't check for type for
                # some reason, e.g. if self.type_ is None, self.type_ is a
                # Protocol or self._type is an instance of a class.
                #
                # If the instance check fails, we assume that the type check
                # went through, and return the object
                type_check_out = True

            if not type_check_out:
                msg = (
                    f"Initialized object `{out}` is not the right type: "
                    f"expected `{self.type_}`, got {type(out)}"
                )
                raise TypeError(msg)

            return out
        except Exception as e:
            ex_name = type(e).__name__
            fn_name = repr(self.func)
            msg = clean_multiline(
                f"""
                An error occurred while trying to initialize {fn_name}
                with arguments "{args}" and kwargs "{kwargs}":
                {ex_name}("{' '.join(map(str, e.args))}")
            """
            )
            raise RuntimeError(msg).with_traceback(e.__traceback__)


class Target:
    @staticmethod
    def _is_module(path: str) -> bool:
        try:
            spec = importlib.util.find_spec(path)
            return spec is not None
        except ModuleNotFoundError:
            return False

    @staticmethod
    def get_config_module(config: Any) -> Union[ModuleType, None]:
        """Returns the package of the type of config if the configuration
        is a structured config (that is, derived from a dataclass/attr.s,
        None otherwise"""
        if isinstance(config, DictConfig):
            config_type = OmegaConf.get_type(config)

            if is_dataclass(config_type):
                return inspect.getmodule(config_type)

        return None

    @classmethod
    def to_string(cls: Type["Target"], callable: Any) -> str:
        if inspect.isclass(callable):
            return f"{callable.__module__}.{callable.__name__}"
        elif inspect.ismethod(callable):
            return f"{cls.to_string(callable.__self__)}.{callable.__name__}"
        elif inspect.isfunction(callable):
            return f"{callable.__module__}.{callable.__name__}"
        else:
            raise TypeError(f"`{callable}` is not a callable")

    @classmethod
    def from_string(
        cls: Type["Target"], path: str, module: Optional[ModuleType] = None
    ) -> Any:
        """Returns a callable from a string path. If path is relative, then
        the module is used to resolve the path.

        Args:
            path (str): dot-separated path to the callable, e.g.
                "module.function"
            module (Optional[ModuleType]): module to use to resolve the path
                if the path is relative. If None, it is assumed that the
                path is absolute.
        """

        callable_ = None

        if path.startswith("."):
            if isinstance(module, ModuleType):
                path = f"{module.__package__}{path}"
            else:
                raise ImportError(f"Cannot resolve relative path {path}")

        if path.startswith("__main__."):
            # special case for any method that might have been defined in
            # the same file as the code entry point. For this case, we
            # first import `__main__`, and then look for the method there

            import __main__

            _, *method_name = path.rsplit(".")
            method_container = __main__

            while method_name:
                local_method_name = method_name.pop(0)

                if hasattr(method_container, local_method_name):
                    method_container = getattr(
                        method_container, local_method_name
                    )
                else:
                    # couldn't find the method
                    break

            # if we exhausted the method name, then we found the method
            callable_ = method_container if len(method_name) == 0 else None
        elif cls._is_module(path):
            return importlib.import_module(path)
        elif "." in path:
            m_name, c_name = path.rsplit(".", 1)
            if cls._is_module(m_name):
                container = importlib.import_module(m_name)
            else:
                container = cls.from_string(m_name)
            callable_ = getattr(container, c_name, None)
        else:
            # the if isinstance(..., dict) for builtin is so that mypy
            # does not complain, because __builtins__ is annotated as Any
            callable_ = globals().get(
                path,
                __builtins__.get(path, None)
                if isinstance(__builtins__, dict)
                else None,
            )

        if callable_ is None:
            raise ImportError(f"Cannot find callable at {path}")

        return callable_


InitT = TypeVar("InitT")
InitNestedT = TypeVar("InitNestedT")
CallableT = TypeVar("CallableT", bound=Callable)


class init(Generic[InitT, CallableT]):
    TARGET: str = "_target_"

    @classmethod
    def callable(
        cls: Type["init"],
        _config_: Optional[Any] = None,
        _type_: Optional[CallableT] = None,
        _recursive_: Optional[Any] = None,
        target: Optional[str] = None,
    ) -> CallableT:
        """Finds a callable function corresponding to the given `target`
        in the config. If no `target` is provided, it looks for `_target_`
        inside the config, raising a KeyError if not found.

        Args:
            config (Optional[DictConfig], optional): A DictConfig configuration
                to use. Defaults to None. config is expected to have at least
                one attribute named `_target_` which contains the path to
                the callable to instantiate.
            target (Optional[str], optional): The name of the target method
                to find. If not provided, it will look for `_target_` in the
                config. Defaults to None.
            _type_ (Optional[Type[InitT]], optional): Expected type of the
                object to instantiate. If provided, a type check is run on
                the instantiated object, raising a TypeError types don't match.
                If not provided, no type check is run. Defaults to None.

        Returns:
            A callable function that can be used to instantiate an object.
        """

        if target is not None and _config_ is not None:
            raise ValueError("Cannot specify both `target` and `config`")
        elif target is None:
            _config_ = cast(_config_)
            try:
                target = str(_config_[cls.TARGET])
            except KeyError:
                raise KeyError(
                    f"Config `{_config_}` has no `{cls.TARGET}` key!"
                )

        config_module = Target.get_config_module(_config_)
        return Target.from_string(target, config_module)

    @overload
    @classmethod
    def later(
        cls: Type["init"],
        _config_: Any,
        _type_: Type[InitT],
        _recursive_: bool = True,
        /,
        **kwargs: Any,
    ) -> Callable[..., InitT]:
        ...

    @overload
    @classmethod
    def later(
        cls: Type["init"],
        _config_: Optional[Any] = None,
        _type_: Optional[Type[InitT]] = None,
        _recursive_: bool = True,
        /,
        **kwargs: Any,
    ) -> Any:
        ...

    @classmethod
    def later(
        cls: Type["init"],
        _config_: Optional[Any] = None,
        _type_: Optional[Type[InitT]] = None,
        _recursive_: bool = True,
        /,
        **kwargs: Any,
    ) -> Callable[..., InitT]:
        """Returns a `functools.partial` object that can be used to initialize
        the object at a later time. The partial object can receive additional
        keyword arguments that are not initially available when calling
        `init.later`.

        Args:
            config (Optional[DictConfig], optional): A DictConfig configuration
                to use. Defaults to None. config is expected to have at least
                one attribute named `_target_` which contains the path to
                the callable to instantiate.
            _type_ (Optional[Type[InitT]], optional): Expected type of the
                object to instantiate. If provided, a type check is run on
                the instantiated object, raising a TypeError types don't match.
                If not provided, no type check is run. Defaults to None.
            kwargs (Dict[str, Any], optional): Keyword arguments to pass to the
                constructor for the object specified in the config. Defaults to
                an empty dictionary.

        Returns:
            An callable that returns an object of type `_type_`.
        """
        SpringsWarnings.missing_type(fn_name="init.later", type_=_type_)

        # if no config is provided, we return a function
        if _config_ is None:
            return InitLater.no_op()

        # ensure we are working with a ConfigDict
        config_node = cast(_config_)

        # try to get the target callable from either the config
        # or keyword arguments passed to the init function
        if cls.TARGET in config_node:
            fn = cls.callable(_config_=config_node, _type_=_type_)
        elif cls.TARGET in kwargs:
            fn = cls.callable(target=kwargs[cls.TARGET], _type_=_type_)
        else:
            raise ValueError(
                f"Cannot instantiate from `{config_node}` and "
                f"`{kwargs}`: `{cls.TARGET}` keyword missing"
            )

        def _recursive_init(
            param: Union[dict, DictConfig, None], type_: Optional[type] = None
        ) -> Any:
            """Given one of the parameters for the object that we are
            trying to instantiate, plus optionally its expected type, this
            function will try to instantiate the parameter if it is a nested
            config AND if _recursive_ is True.
            """
            must_recursive_init = (
                # we are operating in recursive mode
                _recursive_
                # the parameter is a nested config
                and isinstance(param, (DictConfig, dict))
                # the nested config has a TARGET property
                and cls.TARGET in param
            )
            if must_recursive_init:
                # we initialize recursively
                return cls.later(param, type_, _recursive_)
            else:
                # we simply return the parameter
                return param

        def _find_child_type(
            cls_: Union[None, type], attr_name: str
        ) -> Union[None, type]:
            """Given the type the object we are initializing is expected to be,
            as well as the name of the attribute we are about to pass to its
            initializer, this function figures out the expected type using
            a combination of class annotations and __init__ annotations.

            If the type the attribute should be cannot be determined, it
            simply returns None.

            An example:

            ```python
            class Test1:
                def __init__(self, a: int):
                    ...

            print(_find_child_type(Test1, "a")) # prints "int"

            class Test2:
                a: float

                def __init__(self, a):
                    ...

            print(_find_child_type(Test2, "a")) # prints "float"

            class Test3:
                def __init__(self, a):
                    ...

            print(_find_child_type(Test3, "a")) # prints "None"
            ```
            """

            if cls_ is None:
                # if the class is None, we don't perform any checks
                return None

            if attr_name in (parent_anns := get_annotations(cls_)):
                return parent_anns[attr_name]

            if attr_name in (
                parent_anns := inspect.getfullargspec(cls_).annotations
            ):
                return parent_anns[attr_name]

            # this is the case where we cannot resolve anything
            return None

        init_call_dict = {
            str(k): _recursive_init(
                param=v, type_=_find_child_type(cls_=_type_, attr_name=str(k))
            )
            for k, v in {**config_node, **kwargs}.items()
            if k != cls.TARGET
        }

        return InitLater(fn, _type_, **init_call_dict)

    @overload
    @classmethod
    def now(
        cls: Type["init"],
        _config_: Any,
        _type_: Type[InitT],
        _recursive_: bool = True,
        /,
        **kwargs: Any,
    ) -> InitT:
        ...

    @overload
    @classmethod
    def now(
        cls: Type["init"],
        _config_: Optional[Any] = None,
        _type_: Optional[Type[InitT]] = None,
        _recursive_: bool = True,
        /,
        **kwargs: Any,
    ) -> Any:
        ...

    @classmethod
    def now(
        cls: Type["init"],
        _config_: Optional[Any] = None,
        _type_: Optional[Type[InitT]] = None,
        _recursive_: bool = True,
        /,
        **kwargs: Any,
    ) -> InitT:
        """Instantiate a class or call a function from a configuration.

        Args:
            config (Optional[DictConfig], optional): A DictConfig configuration
                to use. Defaults to None. config is expected to have at least
                one attribute named `_target_` which contains the path to
                the callable to instantiate.
            _type_ (Optional[Type[InitT]], optional): Expected type of the
                object to instantiate. If provided, a type check is run on
                the instantiated object, raising a TypeError types don't match.
                If not provided, no type check is run. Defaults to None.
            kwargs (Dict[str, Any], optional): Keyword arguments to pass to the
                constructor for the object specified in the config. Defaults to
                an empty dictionary.

        Returns:
            An object of type `_type_`.
        """
        SpringsWarnings.missing_type(fn_name="init.now", type_=_type_)

        # notice the use of non-keyword arguments here for config,
        # _type_, and _recursive_. This is because `later` has a `/`
        # in its signature, which is required to ensure that **kwargs
        # works well with type annotations.
        init_call: Callable[..., InitT] = cls.later(
            _config_, _type_, _recursive_, **kwargs
        )
        return init_call()

    """Convenience shortcut for `init.now`"""
    __new__: Callable[..., InitT] = now  # type: ignore

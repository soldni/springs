import sys
import types
from collections import abc
from dataclasses import fields, is_dataclass
from typing import (Any, NamedTuple, Optional, Tuple, Type, Union, get_args,
                    get_origin)
import warnings

from omegaconf import DictConfig, ListConfig, OmegaConf

try:
    from omegaconf._utils import get_type_hint as _get_type_hint
except ImportError:
    _get_type_hint = None


def get_type_hint(obj: Any, key: Any = None) -> Optional[Type[Any]]:
    if _get_type_hint:
        return _get_type_hint(obj, key)
    else:
        warnings.warn('get_type_hint could not be imported from '
                      'omegaconf._utils, falling back to OmegaConf.get_type')
        return OmegaConf.get_type(obj, key)


NoneType: Type[None] = type(None)


def is_union_annotation(type_: Any) -> bool:
    """Check wether `type_` is equivalent to `typing.Union[T, ...]`

    From https://github.com/omry/omegaconf/blob/e95c2c76d2545a844794682108ded57fbf98f042/omegaconf/_utils.py#L195"""  # noqa: E501
    if sys.version_info >= (3, 10):
        if isinstance(type_, types.UnionType):
            return True
    return getattr(type_, "__origin__", None) is Union


def resolve_optional(type_: Any) -> Tuple[bool, Any]:
    """Check whether `type_` is equivalent to `typing.Optional[T]`
    for some T.

    From https://github.com/omry/omegaconf/blob/e95c2c76d2545a844794682108ded57fbf98f042/omegaconf/_utils.py#L202"""  # noqa: E501
    if is_union_annotation(type_):
        args = type_.__args__
        if NoneType in args:
            optional = True
            args = tuple(a for a in args if a is not NoneType)
        else:
            optional = False
        if len(args) == 1:
            return optional, args[0]
        elif len(args) >= 2:
            return optional, Union[args]    # type: ignore
        else:
            assert False

    if type_ is Any:
        return True, Any

    if type_ in (None, NoneType):
        return True, NoneType

    return False, type_


class MappingType(NamedTuple):
    key: Any
    val: Any


def resolve_mapping(type_: Any) -> Union[None, MappingType]:
    origin = get_origin(type_)

    if origin is not None and issubclass(origin, abc.Mapping):
        return MappingType(*get_args(type_))

    return None


def resolve_sequence(type_: Any) -> Union[None, Type]:
    origin = get_origin(type_)

    if origin is not None and issubclass(origin, abc.Sequence):
        return MappingType(*get_args(type_))

    return None


def safe_select(
    config: DictConfig,
    key: str,
    interpolate: bool = True
) -> Any:
    """Selects a key from a config, but returns None if the key
        is missing or the key resolution fails."""

    if key in config and \
            OmegaConf.is_interpolation(config, key) and \
            not interpolate:
        return OmegaConf.to_container(config).get(key, None)    # type: ignore

    if (key not in config) or OmegaConf.is_missing(config, key):
        return None
    elif OmegaConf.is_interpolation(config, key):
        if interpolate:
            return OmegaConf.select(
                cfg=config,
                key=key,
                throw_on_resolution_failure=False
            )
        else:
            di: dict = OmegaConf.to_container(config)   # type: ignore
            return di.get(key, None)
    else:
        return OmegaConf.select(cfg=config, key=key)


def get_type(config_node: Union[DictConfig, ListConfig],
             key: Optional[Union[int, str]] = None) -> Union[type, None]:
    """Tries to infer the type of a config node key. Reurns None if
    the type cannot be inferred."""

    if not isinstance(config_node, (DictConfig, ListConfig)):
        raise ValueError('Expected a DictConfig or ListConfig object, '
                         f'got {type(config_node)} instead')

    if key is None:
        return OmegaConf.get_type(config_node)

    if isinstance(config_node, DictConfig):
        typ_ = OmegaConf.get_type(config_node, str(key))

        if typ_ is not None:
            return typ_

        node_type = OmegaConf.get_type(config_node)
        node_type_hint = get_type_hint(config_node)

        if is_dataclass(node_type):
            for field in fields(node_type):
                if field.name == key:
                    typ_ = field.type
                    break
            _, typ_ = resolve_optional(typ_)

        elif node_type_hint := resolve_mapping(node_type_hint):
            # we return the default type that was given to all type hints
            typ_ = node_type_hint.val

        return typ_

    elif isinstance(config_node, ListConfig):
        if not isinstance(key, int):
            raise ValueError(f'Expected an int key, got {type(key)} instead')

        if 0 <= key < len(config_node):
            # you asked for type of an existing element
            return OmegaConf.get_type(config_node[key])
        else:
            # type of a non-existing element, so we rely on type hint
            # if available
            node_type_hint = get_type_hint(config_node)
            return resolve_sequence(node_type_hint)

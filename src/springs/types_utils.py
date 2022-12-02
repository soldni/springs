import sys
import types
import warnings
from collections import abc
from dataclasses import fields, is_dataclass
from typing import Any, NamedTuple, Optional, Tuple, Type, Union
from typing import cast as typecast
from typing import get_args, get_origin

from omegaconf import DictConfig, ListConfig, OmegaConf
from omegaconf.base import DictKeyType
from omegaconf.errors import OmegaConfBaseException

try:
    from omegaconf._utils import get_type_hint as _get_type_hint

    GET_TYPE_HINT_AVAILABLE = True
except ImportError:
    GET_TYPE_HINT_AVAILABLE = False


def get_type_hint(obj: Any, key: Any = None) -> Optional[Type[Any]]:
    if GET_TYPE_HINT_AVAILABLE:
        return _get_type_hint(obj, key)
    else:
        warnings.warn(
            "get_type_hint could not be imported from "
            "omegaconf._utils, falling back to OmegaConf.get_type"
        )
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
            return optional, Union[args]  # type: ignore
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


def resolve_mapping(type_: Optional[type]) -> Union[None, MappingType]:
    if type_ is None:
        return None

    origin = get_origin(type_)

    if origin is not None and issubclass(origin, abc.Mapping):
        return MappingType(*get_args(type_))

    return None


def resolve_tuple(type_: Optional[type]) -> Union[None, Tuple[Type, ...]]:
    if type_ is None:
        return None

    origin = get_origin(type_)

    if origin is not None and issubclass(origin, abc.Sequence):
        return get_args(type_)

    return None


def resolve_sequence(type_: Optional[type]) -> Union[None, type]:
    types_as_tuple = resolve_tuple(type_)
    if types_as_tuple is not None:
        if len(types_as_tuple) > 1:
            raise ValueError(
                "Tuple with more than one element is not a "
                "supported sequence type"
            )
        return types_as_tuple[0]
    else:
        return None


def safe_select(
    config: Union[DictConfig, ListConfig],
    key: DictKeyType,
    interpolate: bool = True,
) -> Union[DictConfig, ListConfig, None]:
    """Selects a key from a config, but returns None if the key
    is missing or the key resolution fails."""

    if not isinstance(config, (DictConfig, ListConfig)):
        raise TypeError(
            f"safe_select only works with DictConfig and ListConfig, "
            f"but got {type(config)}"
        )

    # we need to check if the is present in the config; the check varies
    # slightly depending on whether the config is a DictConfig or a ListConfig.
    key_does_exist = (isinstance(config, DictConfig) and key in config) or (
        isinstance(config, ListConfig)
        and typecast(int, key) < len(typecast(ListConfig, config))
    )

    if (
        key_does_exist
        and OmegaConf.is_interpolation(config, typecast(Union[int, str], key))
        and not interpolate
    ):
        # by calling to_container, we force the key will
        # not be interpolated
        container = OmegaConf.to_container(config)
        if isinstance(container, list):
            return container[typecast(int, key)]
        elif isinstance(container, dict):
            return container[typecast(str, key)]
        else:
            return None

    if (not key_does_exist) or OmegaConf.is_missing(config, key):
        # if the key is missing, we return None
        return None
    elif OmegaConf.is_interpolation(config, typecast(Union[int, str], key)):
        # interpolation is enabled if we reach this point
        if isinstance(config, DictConfig):
            return OmegaConf.select(
                cfg=config,
                key=typecast(str, key),
                throw_on_resolution_failure=False,
            )
        elif isinstance(config, ListConfig):
            try:
                return config[typecast(int, key)]
            except OmegaConfBaseException:
                return None
        else:
            di: dict = OmegaConf.to_container(config)  # type: ignore
            return di.get(key, None)
    elif isinstance(config, DictConfig):
        return OmegaConf.select(cfg=config, key=typecast(str, key))
    else:
        return config[typecast(int, key)]


def get_type(
    config_node: Union[DictConfig, ListConfig],
    key: Optional[Union[int, str]] = None,
) -> Union[type, None]:
    """Tries to infer the type of a config node key. Returns None if
    the type cannot be inferred."""

    if not isinstance(config_node, (DictConfig, ListConfig)):
        raise ValueError(
            "Expected a DictConfig or ListConfig object, "
            f"got {type(config_node)} instead"
        )

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

        elif resolved_node_type_hint := resolve_mapping(node_type_hint):
            # we return the default type that was given to all type hints
            typ_ = (
                resolved_node_type_hint.val
                if resolved_node_type_hint is not None
                else None
            )

        return typ_

    elif isinstance(config_node, ListConfig):
        if not isinstance(key, int):
            raise ValueError(f"Expected an int key, got {type(key)} instead")

        if 0 <= key < len(config_node):
            # you asked for type of an existing element
            return OmegaConf.get_type(config_node[key])
        else:
            # type of a non-existing element, so we rely on type hint
            # if available
            node_type_hint = get_type_hint(config_node)
            resolved_node_type_hint_seq = resolve_sequence(node_type_hint)

            # gets around the fact that we might not be able resolve
            return resolved_node_type_hint_seq
    else:
        raise ValueError(
            "Expected a DictConfig or ListConfig object, "
            f"got {type(config_node)} instead"
        )

from collections import abc
from copy import deepcopy
from abc import ABC, ABCMeta
from dataclasses import dataclass, is_dataclass
from inspect import isclass
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Sequence, Type, Union

from omegaconf import MISSING, DictConfig, ListConfig, OmegaConf
from omegaconf.omegaconf import DictKeyType

from .flexyclasses import FlexyClassMeta


class _DataClassMeta(ABCMeta):
    def __subclasscheck__(cls: '_DataClassMeta', subclass: Any) -> bool:
        return isclass(subclass) and is_dataclass(subclass)


class _DataClass(ABC, metaclass=_DataClassMeta):
    """Generic prototype for a dataclass"""

    __dataclass_fields__: Dict[str, Any]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        ...

    def __instancecheck__(self, __instance: Any) -> bool:
        return is_dataclass(__instance)


########################################


ConfigType = Union[
    DictConfig,
    Dict[DictKeyType, Any],
    Dict[str, Any],
    str,
    _DataClass,
    FlexyClassMeta,
    Path,
    None
]


def cast(config: ConfigType, copy: bool = False) -> DictConfig:
    if isinstance(config, _DataClass):
        return from_dataclass(config)
    elif isclass(config) and issubclass(type(config), FlexyClassMeta):
        return from_flexyclass(config)  # type: ignore
    elif isinstance(config, dict):
        return from_dict(config)
    elif isinstance(config, str):
        return from_string(config)
    elif config is None:
        return from_none(config)
    elif isinstance(config, DictConfig):
        return deepcopy(config) if copy else config
    elif isinstance(config, Path):
        return from_file(config)
    else:
        raise TypeError(f'Cannot cast `{type(config)}` to DictConfig')


def from_none(*args: Any, **kwargs: Any) -> DictConfig:
    """Returns an empty dict config"""
    return OmegaConf.create()


def from_dataclass(config: Union[Type[_DataClass], _DataClass]) -> DictConfig:
    """Cast a dataclass to a structured omega config"""
    if not is_dataclass(config):
        raise TypeError(f'`{config}` is not a dataclass!')

    config = OmegaConf.structured(config)
    if not isinstance(config, DictConfig):
        raise TypeError(f'Cannot create dict config from `{config}`')
    return config


def from_flexyclass(
    config: Union[dict, FlexyClassMeta],
    **overrides: Any
) -> DictConfig:

    if isclass(config):
        if issubclass(type(config), FlexyClassMeta):
            return from_dict(dict(config(**overrides)))
        else:
            raise TypeError(f'`{config}` was not decorated with @flexyclass')
    else:
        if isinstance(config, dict):
            return from_dict(dict(config))
        else:
            raise TypeError(f'`{config}` is not a flexy class instance!')


def from_dict(
    config: Union[Dict[DictKeyType, Any], Dict[str, Any]]
) -> DictConfig:
    """Create a config from a dict"""
    if not isinstance(config, dict):
        raise TypeError(f'`{config}` is not a dict!')

    parsed_config = OmegaConf.create(config)

    if not isinstance(parsed_config, DictConfig):
        raise ValueError(f'Config `{config}` is not a DictConfig!')
    return OmegaConf.create(config)


def from_string(config: str) -> DictConfig:
    """Load a config from a string"""
    if not isinstance(config, str):
        raise TypeError(f'`{config}` is not a string!')

    parsed_config = OmegaConf.create(config)

    if not isinstance(parsed_config, DictConfig):
        raise ValueError(f'Config `{config}` is not a DictConfig!')
    return parsed_config


def from_file(path: Union[str, Path]) -> DictConfig:
    """Load a config from a file"""
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f'Cannot file configuration at {path}')
    config = OmegaConf.load(path)

    if not isinstance(config, DictConfig):
        raise ValueError(f'Config loaded from {path} is not a DictConfig!')

    return config


def from_options(opts: Sequence[str]) -> DictConfig:
    """Create a config from a list of options"""
    if (
        not isinstance(opts, abc.Sequence) or
        not all(isinstance(o, str) for o in opts)
    ):
        raise TypeError(f'`{opts}` is not a list of strings!')

    config = OmegaConf.from_dotlist(list(opts))
    if not isinstance(config, DictConfig):
        raise TypeError(f"input is not a sequence of strings, but `{opts}")
    return config


def to_yaml(config: Union[DictConfig, _DataClass, Type[_DataClass]]) -> str:
    """Convert a omegaconf config to a YAML string"""
    if not isinstance(config, DictConfig):
        config = from_dataclass(config)
    return OmegaConf.to_yaml(config)


def to_dict(
    config: Union[DictConfig, _DataClass, Type[_DataClass]]
) -> Dict[DictKeyType, Any]:
    """Convert a omegaconf config to a Python primitive type"""
    if isinstance(config, _DataClass):
        config = from_dataclass(config)
    container = OmegaConf.to_container(config)

    if not isinstance(container, dict):
        raise TypeError(f'`{container}` is not a dict!')

    return container


########################################


@dataclass
class ParamSpec:
    key: Union[str, int]
    path: str
    value: Any
    node: Optional[Union[DictConfig, ListConfig]]

    def is_missing(self) -> bool:
        return self.value is MISSING

    def is_interpolation(self) -> bool:
        if self.node is not None:
            return OmegaConf.is_interpolation(self.node, self.key)
        return False


def _traverse_config_list(config_node: ListConfig) -> Iterator[ParamSpec]:
    for i, item in enumerate(config_node):
        if isinstance(item, (DictConfig, ListConfig)):
            for p_spec in traverse(item):
                yield ParamSpec(key=p_spec.key,
                                path=f'[{i}].{p_spec.path}',
                                value=p_spec.value,
                                node=p_spec.node)
        else:
            yield ParamSpec(key=i,
                            path=f'[{i}]',
                            value=item,
                            node=config_node)


def _traverse_config_dict(config_node: DictConfig) -> Iterator[ParamSpec]:
    for key in config_node.keys():
        if OmegaConf.is_missing(config_node, key):
            value = MISSING
        elif OmegaConf.is_interpolation(config_node, str(key)):
            # OmegaConf.to_container returns non-interpolated values,
            # so we can get the value before interpolation
            value = OmegaConf.to_container(
                config_node)[key]   # type: ignore
        else:
            value = config_node[key]

        if isinstance(value, (DictConfig, ListConfig)):
            for p_spec in traverse(value):
                yield ParamSpec(key=p_spec.key,
                                path=f'{key}.{p_spec.path}',
                                value=p_spec.value,
                                node=p_spec.node)
        else:
            yield ParamSpec(key=str(key),
                            path=str(key),
                            value=value,
                            node=config_node)


def traverse(
    config_node: Union[DictConfig, ListConfig]
) -> Iterator[ParamSpec]:
    """Returns all keys for a config node"""

    if isinstance(config_node, ListConfig):
        yield from _traverse_config_list(config_node)
    elif isinstance(config_node, DictConfig):
        yield from _traverse_config_dict(config_node)
    else:
        raise TypeError(f'Cannot traverse `{config_node}`; DictConfig or '
                        f'ListConfig expected, but got `{type(config_node)}`.')


########################################


def validate(config_node: ConfigType) -> DictConfig:
    """Check if all attributes are resolve and not missing"""

    if not isinstance(config_node, DictConfig):
        raise TypeError(f'`{config_node}` is not a DictConfig!')

    for spec in traverse(config_node):
        if OmegaConf.is_missing(spec.node, spec.key):
            raise ValueError(f'Missing value for `{spec.path}`')
        if OmegaConf.is_interpolation(spec.node, spec.key):
            try:
                getattr(spec.node, str(spec.key))
            except Exception:
                raise ValueError(f'Interpolation for `{spec.path}` '
                                 'not resolved')

    config_node = deepcopy(config_node)
    OmegaConf.resolve(config_node)
    return config_node


def merge(*configs: ConfigType) -> DictConfig:
    """Merges multiple configurations into one."""

    if not configs:
        # no configs were provided, return an empty config
        return from_none()

    # make sure all configs are DictConfigs
    merged_config, *other_configs = (cast(config) for config in configs)

    # do the actual merging; this will also check if types are compatible
    for other_config in other_configs:
        merged_config = OmegaConf.merge(merged_config, other_config)

    #  raise error if we end up with something that is not a dict config
    if not isinstance(merged_config, DictConfig):
        raise TypeError(f'While merging {configs}, the resulting config is '
                        f'{type(merged_config)} instead of DictConfig.')

    return cast(merged_config)

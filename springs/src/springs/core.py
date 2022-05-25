import copy
from dataclasses import dataclass, is_dataclass, field      # noqa: F401
from typing import (Callable, Iterator, Optional, Protocol, Dict,
                    Type, Union, Any, TypeVar)

from omegaconf import DictConfig, OmegaConf, MISSING, open_dict

from .utils import NoneCtx

# for return type
RT = TypeVar('RT')


class DataClass(Protocol):
    # from https://stackoverflow.com/a/55240861
    __dataclass_fields__: Dict[str, Any]

    def __instancecheck__(self, __instance: Any) -> bool:
        return is_dataclass(__instance)


@dataclass
class ParamSpec:
    name: str
    path: str
    value: Any
    node: Optional[DictConfig]


def traverse(config_node: DictConfig) -> Iterator[ParamSpec]:
    """Returns all keys for a config node"""
    # if isinstance(config_node, DictConfig):
    #     yield from traverse(OmegaConf.to_container(config_node))
    # print(config_node)
    # else:
    for key in config_node.keys():
        if OmegaConf.is_missing(config_node, key):
            value = MISSING
        elif OmegaConf.is_interpolation(config_node, str(key)):
            value = OmegaConf.to_container(config_node)[key]   # type: ignore
        else:
            value = config_node[key]

        if isinstance(value, DictConfig):
            for p in traverse(value):
                yield ParamSpec(name=p.name,
                                path=f'{key}.{p.path}',
                                value=p.value,
                                node=p.node)
        else:
            yield ParamSpec(name=str(key),
                            path=str(key),
                            value=value,
                            node=config_node)


def validate(config_node: Any) -> DictConfig:
    """Check if all attributes are resolve and not missing"""

    if not isinstance(config_node, DictConfig):
        raise TypeError(f'`{config_node}` is not a DictConfig!')

    for spec in traverse(config_node):
        if OmegaConf.is_missing(spec.node, spec.name):
            raise ValueError(f'Missing value for `{spec.path}`')
        if OmegaConf.is_interpolation(spec.node, spec.name):
            try:
                getattr(spec.node, spec.name)
            except Exception:
                raise ValueError(f'Interpolation for `{spec.path}` '
                                 'not resolved')

    config_node = copy.deepcopy(config_node)
    OmegaConf.resolve(config_node)
    return config_node


def config_from_dict(
    config: Union[DictConfig, Dict[str, Any], None]
) -> DictConfig:
    if config is None:
        new_config = OmegaConf.create()
    elif not isinstance(config, DictConfig):
        try:
            new_config = OmegaConf.create(config)
        except Exception as e:
            msg = f'Cannot get config from object of type `{type(config)}`'
            raise ValueError(msg) from e
    else:
        new_config = config

    if not isinstance(new_config, DictConfig):
        raise ValueError(f'Config `{config}` is not a DictConfig!')

    return new_config


def config_from_string(
    config: str,
    config_cls: Optional[Type[DataClass]] = None,
    strict_input: bool = False
) -> DictConfig:

    parsed_config = OmegaConf.create(config)

    if config_cls is not None:
        base_config = OmegaConf.structured(config_cls)
        with (NoneCtx() if strict_input else open_dict(base_config)):
            parsed_config = OmegaConf.merge(base_config, parsed_config)

    if isinstance(parsed_config, DictConfig):
        return parsed_config
    else:
        raise TypeError(f'Could not create config from string `{config}`')


def to_yaml(config: Union[DictConfig, Dict[str, Any]]) -> str:
    config = config_from_dict(config)
    return OmegaConf.to_yaml(config)


def register(
    name: str,
    use_cache: bool = False
) -> Callable[[Callable[..., RT]], Callable[..., RT]]:

    def _register(func: Callable[..., RT]) -> Callable[..., RT]:
        # will raise an error if the resolver is already registered
        OmegaConf.register_new_resolver(
            name=name, resolver=func, use_cache=use_cache, replace=False
        )
        return func

    return _register

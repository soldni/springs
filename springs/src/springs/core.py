import copy
from dataclasses import dataclass, field, is_dataclass     # noqa: F401
from contextlib import contextmanager, ExitStack
from pathlib import Path
from typing import (Any, Callable, Dict, Iterator, Optional, Protocol,
                    Sequence, Type, TypeVar, Union)

from omegaconf import MISSING, DictConfig, open_dict, OmegaConf
from omegaconf.basecontainer import BaseContainer


# for return type
RT = TypeVar('RT')


class DataClass(Protocol):
    # from https://stackoverflow.com/a/55240861
    __dataclass_fields__: Dict[str, Any]

    def __instancecheck__(self, __instance: Any) -> bool:
        return is_dataclass(__instance)


ConfigType = Union[DictConfig, Dict[str, Any], Type[DataClass], str, DataClass]


@dataclass
class ParamSpec:
    name: str
    path: str
    value: Any
    node: Optional[DictConfig]


def traverse(config_node: ConfigType) -> Iterator[ParamSpec]:
    """Returns all keys for a config node"""

    config_node = cast(config_node)

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


def validate(config_node: ConfigType) -> DictConfig:
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


def cast(config: Any) -> DictConfig:
    if is_dataclass(config):
        return from_dataclass(config)
    elif isinstance(config, dict):
        return from_dict(config)
    elif isinstance(config, str):
        return from_string(config)
    elif isinstance(config, DictConfig):
        return config
    else:
        raise TypeError(f'Cannot cast `{type(config)}` to DictConfig')


def from_options(opts: Sequence[str]) -> DictConfig:
    config = OmegaConf.from_dotlist(list(opts))
    if not isinstance(config, DictConfig):
        raise TypeError(f"input is not a sequence of strings, but `{opts}")
    return config


def from_dataclass(config: ConfigType) -> DictConfig:
    if not(is_dataclass(config)):
        msg = '`config_node` must be be decorated as a dataclass'
        raise ValueError(msg)
    config = OmegaConf.structured(config)
    if not isinstance(config, DictConfig):
        raise TypeError(f'Cannot create dict config from `{config}`')

    return config


def from_file(path: Optional[Path] = None) -> DictConfig:
    if path is not None:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f'Cannot file configuration at {path}')
        config = OmegaConf.load(str(path))
    else:
        config = from_dict(None)

    if not isinstance(config, DictConfig):
        raise ValueError(f'Config loaded from {path} is not a DictConfig!')

    return config


def from_none() -> DictConfig:
    """Returns an empty dict config"""
    return OmegaConf.create()


def from_dict(
    config: Optional[Union[DictConfig, Dict[str, Any]]] = None
) -> DictConfig:
    if config is None:
        new_config = from_none()
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


def from_string(
    config: str,
    config_cls: Optional[Type[DataClass]] = None,
) -> DictConfig:

    parsed_config = OmegaConf.create(config)
    if not isinstance(parsed_config, DictConfig):
        raise ValueError(f'Config `{config}` is not a DictConfig!')

    if config_cls is not None:
        base_config = OmegaConf.structured(config_cls)
        parsed_config = merge(base_config, parsed_config)

    if not isinstance(parsed_config, DictConfig):
        raise TypeError(f'Could not create config from string `{config}`')
    return parsed_config


def to_yaml(config: Union[DictConfig, Dict[str, Any]]) -> str:
    config = from_dict(config)
    return OmegaConf.to_yaml(config)


def to_dict(config: Union[DictConfig, Dict[str, Any]]) -> Dict[str, Any]:
    config = from_dict(config)
    return OmegaConf.to_container(config)


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


def all_resolvers() -> Sequence[str]:
    return [str(k) for k in BaseContainer._resolvers.keys()]


def _safe_select(config: DictConfig, key: str) -> Any:
    """Selects a key from a config, but returns None if the key is missing
    or the key resolution fails."""
    return OmegaConf.select(
        cfg=config,
        key=key,
        throw_on_missing=False,
        throw_on_resolution_failure=False
    )


@contextmanager
def rec_open_dict(config: Any) -> Iterator[DictConfig]:
    """Recursively opens all dict for writing in a config."""
    try:
        with ExitStack() as stack:
            open_config: DictConfig = \
                 stack.enter_context(open_dict(config))     # type: ignore
            for key in open_config:
                if OmegaConf.is_dict(open_config):
                    node = _safe_select(open_config, str(key))
                else:
                    node = key
                if OmegaConf.is_config(node):
                    stack.enter_context(rec_open_dict(node))
            yield open_config
    finally:
        ...


def _init_new_nodes(merge_into: DictConfig, merge_from: DictConfig) -> None:
    """Sometimes, when merging, new nodes appear in the configuration
    we are merging from; we need to make sure these nodes are properly
    initialized in the configuration we are merging into, or else merging
    will fail."""

    for key in merge_from:
        key = str(key)  # linter gets confused without this casting

        merge_from_value = _safe_select(merge_from, key)
        merge_into_value = _safe_select(merge_into, key)
        merge_into_type = OmegaConf.get_type(merge_into, key)

        if isinstance(merge_from_value, DictConfig):
            if isinstance(merge_into_value, DictConfig):
                # both configs have nodes at this location, so we need to
                # recursively initialize new nodes down in the tree.
                _init_new_nodes(merge_into_value, merge_from_value)

            elif merge_into_type and is_dataclass(merge_into_type):
                # the merge_into node is not a configuration, but it could
                # be one, since its type is a dataclass. Therefore, we first
                # initialize this its node with an empty dataclass, which
                # will then cause no issue when merging.
                setattr(merge_into, key, from_dataclass(merge_into_type))

                # now that we have a proper dataclass here, we again
                # recursively see if there are any new nodes to initialize.
                _init_new_nodes(merge_into_value, merge_from_value)

            elif key in merge_into:
                # Total mismatch of types; better to just delete the node
                # from the merge_into config so it can be fully replaced by
                # the merge_from config.
                delattr(merge_into, key)

        elif isinstance(merge_into_value, DictConfig):
            # the merge_into node has a config here, but the merge_from node
            # has something completely different in mind. The only way to
            # get around it is by completely nuking the original node.
            delattr(merge_into, key)


def merge(*configs: ConfigType) -> DictConfig:
    """Merges multiple configurations into one."""

    if not configs:
        # no configs were provided, return an empty config
        return from_none()

    # make sure all configs are DictConfigs
    merged_config, *other_configs = configs

    for other_config in other_configs:
        with rec_open_dict(merged_config):
            _init_new_nodes(cast(merged_config), cast(other_config))
            merged_config = OmegaConf.merge(merged_config, other_config)

    return cast(merged_config)

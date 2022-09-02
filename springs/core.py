from collections import abc
from copy import deepcopy
from dataclasses import is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple, Union

from omegaconf import DictConfig, ListConfig, OmegaConf
from omegaconf.omegaconf import DictKeyType

from .flexyclasses import unlock_all_flexyclasses
from .traversal import ParamSpec, traverse
from .types import get_type, safe_select


@unlock_all_flexyclasses
def cast(config: Any, copy: bool = False) -> DictConfig:
    if is_dataclass(config):
        parsed_config = from_dataclass(config)
    elif isinstance(config, dict):
        parsed_config = from_dict(config)
    elif isinstance(config, str):
        parsed_config = from_string(config)
    elif config is None:
        parsed_config = from_none(config)
    elif isinstance(config, DictConfig):
        parsed_config = deepcopy(config) if copy else config
    elif isinstance(config, Path):
        parsed_config = from_file(config)
    else:
        raise TypeError(f"Cannot cast `{type(config)}` to DictConfig")

    return parsed_config


@unlock_all_flexyclasses
def from_none(*args: Any, **kwargs: Any) -> DictConfig:
    """Returns an empty dict config"""
    return OmegaConf.create()


@unlock_all_flexyclasses
def from_dataclass(config: Any) -> DictConfig:
    """Cast a dataclass to a structured omega config"""
    if config is None:
        return from_none()

    if not is_dataclass(config):
        raise TypeError(f"`{config}` is not a dataclass!")

    parsed_config = OmegaConf.structured(config)

    if not isinstance(parsed_config, DictConfig):
        raise TypeError(f"Cannot create dict config from `{config}`")
    return parsed_config


@unlock_all_flexyclasses
def from_dict(
    config: Union[Dict[DictKeyType, Any], Dict[str, Any]]
) -> DictConfig:
    """Create a config from a dict"""
    if not isinstance(config, dict):
        raise TypeError(f"`{config}` is not a dict!")

    parsed_config = OmegaConf.create(config)

    if not isinstance(parsed_config, DictConfig):
        raise ValueError(f"Config `{config}` is not a DictConfig!")
    return OmegaConf.create(config)


@unlock_all_flexyclasses
def from_string(config: str) -> DictConfig:
    """Load a config from a string"""
    if not isinstance(config, str):
        raise TypeError(f"`{config}` is not a string!")

    parsed_config = OmegaConf.create(config)

    if not isinstance(parsed_config, DictConfig):
        raise ValueError(f"Config `{config}` is not a DictConfig!")
    return parsed_config


@unlock_all_flexyclasses
def from_file(path: Union[str, Path]) -> DictConfig:
    """Load a config from a file"""
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Cannot file configuration at {path}")
    config = OmegaConf.load(path)

    if not isinstance(config, DictConfig):
        raise ValueError(f"Config loaded from {path} is not a DictConfig!")

    return config


@unlock_all_flexyclasses
def from_options(opts: Sequence[str]) -> DictConfig:
    """Create a config from a list of options"""
    if not isinstance(opts, abc.Sequence) or not all(
        isinstance(o, str) for o in opts
    ):
        raise TypeError(f"`{opts}` is not a list of strings!")

    config = OmegaConf.from_dotlist(list(opts))
    if not isinstance(config, DictConfig):
        raise TypeError(f"input is not a sequence of strings, but `{opts}")
    return config


def to_yaml(config: Any) -> str:
    """Convert a omegaconf config to a YAML string"""
    if not isinstance(config, DictConfig):
        config = from_dataclass(config)
    return OmegaConf.to_yaml(config)


def to_dict(config: Any) -> Dict[DictKeyType, Any]:
    """Convert a omegaconf config to a Python primitive type"""
    if is_dataclass(config):
        config = from_dataclass(config)
    container = OmegaConf.to_container(config)

    if not isinstance(container, dict):
        raise TypeError(f"`{container}` is not a dict!")

    return container


########################################


def safe_validate(config_node: Any) -> Tuple[DictConfig, List[ParamSpec]]:
    """Check if all attributes are resolve and not missing

    If resolution fails, second element of return tuple contains
    missing keys."""

    missing = []

    if not isinstance(config_node, DictConfig):
        raise TypeError(f"`{config_node}` is not a DictConfig!")

    for spec in traverse(config_node):
        if spec.key is None:
            raise RuntimeError(
                "You should not be here! Something went "
                "wrong in the core Springs library."
            )

        if OmegaConf.is_missing(spec.parent, spec.key):
            raise ValueError(f"Missing value for `{spec.path}`")
        if OmegaConf.is_interpolation(spec.parent, spec.key):
            try:
                getattr(spec.parent, str(spec.key))
            except Exception:
                missing.append(spec)

    if len(missing) == 0:
        # all resolution successful!
        config_node = deepcopy(config_node)
        OmegaConf.resolve(config_node)

    return config_node, missing


def validate(config_node: Any) -> DictConfig:
    config_node, missing = safe_validate(config_node)
    for spec in missing:
        # this will not run if missing is an empty list
        raise ValueError(f"Interpolation for `{spec.path}` not resolved")
    return config_node


def _pre_merge_fix_type_mismatches(
    merge_into: DictConfig, merge_from: DictConfig
) -> None:
    """Sometimes, when merging, new nodes or attributes appear in the
    configuration we are merging from; we need to make sure these nodes
    are properly initialized in the configuration we are merging into,
    or else merging will fail."""

    node_it = (
        range(len(merge_from))
        if isinstance(merge_from, ListConfig)
        else tuple(merge_from.keys())
    )

    for key in node_it:
        key = str(key)  # linter gets confused without this casting

        merge_from_value = safe_select(merge_from, key, interpolate=False)
        merge_into_value = safe_select(merge_into, key, interpolate=False)
        merge_into_expected_type = get_type(merge_into, key)

        if isinstance(merge_from_value, DictConfig):
            if isinstance(merge_into_value, DictConfig):
                # both configs have nodes at this location, so we need to
                # recursively initialize new nodes down in the tree.

                _pre_merge_fix_type_mismatches(
                    merge_into_value, merge_from_value
                )

            elif merge_into_expected_type:
                if is_dataclass(merge_into_expected_type):
                    # the merge_into node is not a configuration, but it could
                    # be one, since its type is a dataclass. Therefore, we
                    # first initialize this its node with an empty dataclass,
                    # which will then cause no issue when merging.
                    merge_into_value = from_dataclass(merge_into_expected_type)

                    # merge = False ensure replacement
                    OmegaConf.update(
                        cfg=merge_into,
                        key=key,
                        value=merge_into_value,
                        merge=False,
                    )
                    # the cast is necessary to make sure that,
                    # after the update, all flexyclasses are unlocked
                    merge_into = cast(merge_into)

                    # now that we have a proper dataclass here, we again
                    # recursively see if there are any new nodes to initialize.
                    _pre_merge_fix_type_mismatches(
                        merge_into_value, merge_from_value
                    )


def _pre_merge_override_interpolations(
    merge_into: DictConfig, merge_from: DictConfig
) -> None:
    """Merge interpolations from merge_from into merge_into"""

    for key in list(merge_from.keys()):
        key = str(key)  # linter gets confused without this casting

        merge_from_value = safe_select(merge_from, key, interpolate=False)
        merge_into_value = safe_select(merge_into, key, interpolate=False)

        if OmegaConf.is_interpolation(merge_from, key):
            # merge = False ensure replacement
            OmegaConf.update(
                cfg=merge_into, key=key, value=merge_from_value, merge=False
            )
            # the cast is necessary to make sure that,
            # after the update, all flexyclasses are unlocked
            merge_into = cast(merge_into)
            delattr(merge_from, key)

        elif isinstance(merge_from_value, DictConfig) and isinstance(
            merge_into_value, DictConfig
        ):
            _pre_merge_override_interpolations(
                merge_into_value, merge_from_value
            )


def merge(*configs: Any) -> DictConfig:
    """Merges multiple configurations into one."""

    if not configs:
        # no configs were provided, return an empty config
        return from_none()

    if not all(isinstance(c, DictConfig) for c in configs):
        raise TypeError(f"`{configs}` is not a list of DictConfigs!")

    # make sure all configs are DictConfigs
    merged_config, *other_configs = (
        cast(config, copy=True) for config in configs
    )

    # do the actual merging; this will also check if types are compatible
    for other_config in other_configs:

        _pre_merge_fix_type_mismatches(merged_config, other_config)
        _pre_merge_override_interpolations(merged_config, other_config)

        # ignoring type mypy check since merge_config and other_config are
        # DictConfig, so the return type is always DictConfig
        merged_config: DictConfig = OmegaConf.merge(  # type: ignore
            merged_config, other_config
        )

        #  raise error if we end up with something that is not a DictConfig
        if not isinstance(merged_config, DictConfig):
            raise TypeError(
                f"While merging {configs}, the resulting config is"
                f" {type(merged_config)} instead of DictConfig."
            )

    return cast(merged_config)

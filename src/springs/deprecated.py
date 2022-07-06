from contextlib import ExitStack, contextmanager
from dataclasses import is_dataclass
from typing import Iterator, TypeVar, Any

from omegaconf import DictConfig, ListConfig, OmegaConf, open_dict
from omegaconf.base import Container

from .core import from_dataclass, ConfigType, from_none, cast


OpenableType = TypeVar('OpenableType', DictConfig, ListConfig, Container)


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
def rec_open_dict(config: OpenableType) -> Iterator[OpenableType]:
    """Recursively opens all dict for writing in a config."""
    try:
        with ExitStack() as stack:
            open_config = stack.enter_context(open_dict(config))
            for key in open_config:
                if OmegaConf.is_dict(open_config):
                    node = _safe_select(
                        open_config,    # type: ignore
                        str(key)
                    )
                else:
                    node = key
                if OmegaConf.is_config(node):
                    stack.enter_context(rec_open_dict(node))
            yield open_config       # type: ignore
    finally:
        ...


def _init_new_nodes(merge_into: DictConfig, merge_from: DictConfig) -> None:
    """Sometimes, when merging, new nodes or attributes appear in the
    configuration we are merging from; we need to make sure these nodes
    are properly initialized in the configuration we are merging into,
    or else merging will fail."""

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
                setattr(merge_into,
                        key,
                        from_dataclass(merge_into_type))    # type: ignore

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
    merged_config, *other_configs = (cast(config) for config in configs)

    for other_config in other_configs:
        with rec_open_dict(merged_config):
            _init_new_nodes(merged_config, other_config)

            merged_config = OmegaConf.merge(
                merged_config, other_config
            )

            if not isinstance(merged_config, DictConfig):
                raise TypeError(f'Error merging configs: {merged_config} '
                                'is now not a DictConfig')

    return cast(merged_config)

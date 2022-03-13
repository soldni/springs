import os
from inspect import isclass
from typing import Any, Callable, Dict, Type, Union

import yaml

from .node import ConfigFlexNode, ConfigNode, ConfigNodeProps, ConfigParam
from .utils import read_raw_file


def config_to_dict(
    config_node: ConfigNode, *args, **kwargs
) -> Dict[str, Any]:
    """Recursively convert `config_node` to a dictionary"""
    if not isinstance(config_node, ConfigNode):
        msg = f'Expecting ConfigNode object, got {type(config_node)}'
        raise TypeError(msg)
    return ConfigNodeProps.get_props(config_node).to_dict(*args, **kwargs)


def config_to_yaml(config_node: ConfigNode, *args, **kwargs) -> str:
    """Recursively convert `config_node` to a yaml representation"""
    if not isinstance(config_node, ConfigNode):
        msg = f'Expecting ConfigNode object, got {type(config_node)}'
        raise TypeError(msg)
    return ConfigNodeProps.get_props(config_node).to_yaml(*args, **kwargs)


def config_from_string(string: str,
                       config_node_cls: Type[ConfigNode] = None) -> ConfigNode:
    """Load a config from a string with a config in yaml
    format. If a ConfigNode class is provided, then it is used
    to validate the string; if not, the schema is automatically
    inferred from the loaded yaml"""
    parsed_yaml = yaml.safe_load(string)

    if config_node_cls is None:
        return config_from_dict(parsed_yaml)
    elif not(isclass(config_node_cls) and
             issubclass(config_node_cls, ConfigNode)):
        raise TypeError(f'Expecting ConfigNode class, got {config_node_cls}')
    else:
        return config_node_cls(parsed_yaml)


def config_from_file(file_path: Union[os.PathLike, str],
                     *args,
                     config_node_cls: Type[ConfigNode] = None,
                     **kwargs) -> ConfigNode:
    """Same of `config_from_string`, but load from a file path instead"""
    content = read_raw_file(file_path)
    return config_from_string(*args,
                              config_node_cls=config_node_cls,
                              string=content,
                              **kwargs)


class config_from_dict:
    def __new__(cls,
                config: Dict[str, Any],
                annotations: Dict[str, Any] = None,
                name: str = None,
                flex: bool = False):
        """Create a ConfigNode object from a dictionary"""
        return cls.cls(config=config,
                       annotations=annotations,
                       name=name,
                       flex=flex)()

    @classmethod
    def cls(
        cls,
        config: Dict[str, Any],
        annotations: Dict[str, Any] = None,
        name: str = None,
        flex: bool = False
    ) -> Type[ConfigNode]:
        """Create a ConfigNode class from a dictionary"""

        # set to empty dictionary if not provided
        annotations = annotations or {}

        # we need a name, does't have to mean anything and it
        # can be repeated, so we use the mem location of config
        # and annotations here.
        name = name or f'{id(config)}_{id(annotations)}'

        # Small function to let us look up a suitable type for a
        # parameter by either looking at type annotations, or by
        # checking the defaults; if anything fails; return a no-op
        # lambda as pseudo-default.
        def _get_ann(p_name: str) -> Callable:
            if p_name in annotations:
                return annotations[p_name]
            if p_name in config:
                return type(config[p_name])
            else:
                return lambda p_value: p_value

        # setting up type annotations, including for target
        param_annotations = {p: ConfigParam(_get_ann(p)) for p in
                             {*annotations, *config}}

        # get node class and set up defaults and annotations
        node_cls = type(name, (ConfigFlexNode if flex else ConfigNode, ), {})
        [setattr(node_cls, p, d) for p, d in config.items()]
        setattr(node_cls, '__annotations__', param_annotations)

        return node_cls

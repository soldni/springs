import os
from inspect import isclass
from typing import Any, Callable, Dict, Type, Union, Optional

from .node import ConfigNode, ConfigNodeProps, ConfigFlexNode
from .parser import YamlParser
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
    parsed_yaml = YamlParser.load(string)

    if config_node_cls is None:
        return ConfigFlexNode(parsed_yaml)
    elif not(isclass(config_node_cls) and
             issubclass(config_node_cls, ConfigNode)):
        raise TypeError(f'Expecting ConfigNode class, got {config_node_cls}')
    else:
        return config_node_cls(parsed_yaml)


def config_from_file(file_path: Union[os.PathLike, str],
                     *args,
                     config_node_cls: Type[ConfigNode] = None,
                     open_fn: Optional[Callable] = None,
                     **kwargs) -> ConfigNode:
    """Same of `config_from_string`, but load from a file path instead"""
    content = read_raw_file(file_path, open_fn=open_fn)
    return config_from_string(*args,
                              config_node_cls=config_node_cls,
                              string=content,
                              **kwargs)

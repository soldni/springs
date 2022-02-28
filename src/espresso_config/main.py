from email.policy import strict
import os
from typing import Type

import smart_open
import yaml

from .node import ConfigNode, ConfigNodeProps

def config_to_dict(config_node: ConfigNode, *args, **kwargs):
    return ConfigNodeProps.get_props(config_node).to_dict(*args, **kwargs)


def config_to_yaml(config_node: ConfigNode, *args, **kwargs):
    return ConfigNodeProps.get_props(config_node).to_yaml(*args, **kwargs)


def config_from_string(config_node: Type[ConfigNode], string: str) -> ConfigNode:
    return config_node(yaml.safe_load(string))

def config_from_file(config_node: Type[ConfigNode], file_path: str) -> ConfigNode:
    with smart_open.open(file_path, mode='r', encoding='utf-8') as f:
        content = f.read()
    return config_from_file(config_node=config_node, string=content)

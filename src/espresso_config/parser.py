from functools import partial
from typing import Callable, Type
import yaml


class YamlParser:
    __yaml_loader__ = yaml.Loader
    __yaml_dumper__ = yaml.Dumper

    @classmethod
    def load(cls, *args, **kwargs):
        return yaml.load(*args, **kwargs, Loader=cls.__yaml_loader__)

    @classmethod
    def dump(cls, *args, **kwargs):
        return yaml.dump(*args, **kwargs, Dumper=cls.__yaml_dumper__)

    @classmethod
    def _register(cls,
                  node_cls: type,
                  node_type: type,
                  node_load: Callable,
                  node_dump: Callable,
                  node_tag: str):
        node_type = node_type or node_cls

        node_load = (node_load or getattr(node_cls, 'from_yaml', None)
                     or node_cls)
        node_dump = (node_dump or getattr(node_cls, 'to_yaml', None)
                     or repr)
        node_tag = node_tag or f'!{node_cls.__name__}'

        def representer(dumper: yaml.Dumper,
                        data: node_type,
                        tag: str = node_tag,
                        dump_fn: Callable = node_dump) -> str:
            return dumper.represent_scalar(tag, dump_fn(data))

        cls.__yaml_dumper__.add_representer(node_type, representer)

        def constructor(loader: yaml.Loader,
                        node: yaml.ScalarNode,
                        load_fn: Callable = node_load) -> node_cls:
            value = loader.construct_scalar(node)
            return load_fn(value)

        cls.__yaml_loader__.add_constructor(node_tag, constructor)

        return node_cls

    @classmethod
    def register(cls,
                 node_type: type = None,
                 node_load: Callable = None,
                 node_dump: Callable = None,
                 node_tag: str = None) -> partial:

        return partial(cls._register,
                       node_type=node_type,
                       node_load=node_load,
                       node_dump=node_dump,
                       node_tag=node_tag)

    def __new__(cls: Type['YamlParser']) -> Type['YamlParser']:
        return cls

import argparse
import copy
import functools
import os
from inspect import getfullargspec, isclass
from typing import Any, Callable, Dict, Type, Union

import yaml

from .node import ConfigFlexNode, ConfigNode, ConfigNodeProps, ConfigParam
from .utils import read_raw_file, type_evaluator


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
                       *args,
                       config_node_cls: Type[ConfigNode] = None,
                       **kwargs) -> ConfigNode:
    """Load a config from a string with a config in yaml
    format. If a ConfigNode class is provided, then it is used
    to validate the string; if not, the schema is automatically
    inferred from the loaded yaml"""
    parsed_yaml = yaml.safe_load(string, *args, **kwargs)

    if config_node_cls is None:
        return config_from_dict(parsed_yaml)
    elif not(isclass(config_node_cls) and
             issubclass(config_node_cls, ConfigNode)):
        raise TypeError(f'Expecting ConfigNode class, got {config_node_cls}')

    return config_node_cls()


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


class config_to_program:
    @classmethod
    def _check_signature(cls, fn):
        expected_args = getfullargspec(fn).args
        if len(expected_args) == 0:
            msg = (f'Function `{fn.__name__}` cannot be decorated '
                   f'by `config_to_program` because it does '
                   f'not accept any argument.')
            raise RuntimeError(msg)
        elif len(expected_args) > 1:
            msg = (f'Function `{fn.__name__}` cannot be decorated by '
                   f' `config_to_program` because it expects '
                   f'{len(expected_args)} > 1; If you want to pass extra '
                   f'arguments to this function, use kwargs with default '
                   f'values.')
            raise RuntimeError(msg)

    @classmethod
    def _check_args(cls, fn, args):
        if len(args):
            msg = (f'After decorating `{fn.__name__}` with '
                   f'`config_to_program`, do not provide any additional '
                   f'arguments while invoking it; any additional parameter '
                   f'should be passed as a keyword argument.')
            raise RuntimeError(msg)

    @classmethod
    def destination_formatter(cls, param_name: str) -> str:
        param_name = param_name.replace('.', '__')
        param_name = f"__{param_name}"
        return param_name

    @classmethod
    def update_config(
        cls,
        config: dict,
        param_name: str,
        param_value: str) -> dict:

        config_copy = copy.deepcopy(config)

        param_name, *param_rest = param_name.split('.', 1)

        if len(param_rest) > 0:
            sub_config = config_copy.setdefault(param_name, {})
            param_value = cls.update_config(
                config=sub_config if isinstance(sub_config, dict) else {},
                param_name='.'.join(param_rest),
                param_value=param_value
            )

        config_copy[param_name] = param_value
        return config_copy

    def __new__(cls, config_node: Type[ConfigNode]) -> Callable:
        if not(isclass(config_node) or issubclass(config_node, ConfigNode)):
            raise ValueError(f'`config_node` is not a subclass of {ConfigNode.__name__}')

        local_config_node = config_node

        def main_decorator_wrapper(fn):
            cls._check_signature(fn)

            @functools.wraps(fn)
            def main_wrapped(*args, **kwargs):
                cls._check_args(fn=fn, args=args)

                ap = argparse.ArgumentParser(
                    prog=f'Parser for configuration {config_node.__name__}',
                    usage='',
                    )

                ap.add_argument('-c',
                                dest='config',
                                default=None,
                                help='YAML config file')
                ap.add_argument('-p',
                                dest='print',
                                default=None,
                                help='Print configuration',
                                choices=['input', 'i',
                                         'parsed', 'p',
                                         'continue', 'c'])

                all_params = ConfigNodeProps.\
                    get_all_parameters(local_config_node)

                for param_spec in all_params:
                    ap.add_argument(
                        f'--{param_spec.name}',
                        dest=cls.destination_formatter(param_spec.name),
                        metavar='',
                        type=type_evaluator(param_spec.type),
                        default=argparse.SUPPRESS,
                        help=(f"Type: {param_spec.type.__name__}; "
                              f"Default: {param_spec.default}")
                    )

                parsed_args = ap.parse_args()

                if parsed_args.config:
                    config = yaml.safe_load(
                        read_raw_file(parsed_args.config)
                    )
                else:
                    config = {}

                for param_spec in all_params:
                    param_value = getattr(
                        parsed_args,
                        cls.destination_formatter(param_spec.name),
                        argparse.SUPPRESS
                    )
                    if param_value != argparse.SUPPRESS:
                        config = cls.update_config(
                            config=config,
                            param_name=param_spec.name,
                            param_value=param_value
                        )

                if parsed_args.print in {'input', 'i'}:
                    print('INPUT CONFIG:')
                    print(yaml.safe_dump(config, indent=2).strip())
                    return lambda: None

                config = local_config_node(config)

                if parsed_args.print in {'parsed', 'p', 'continue', 'c'}:
                    print('PARSED CONFIG:')
                    print(config_to_yaml(config, indent=2).strip())
                    if parsed_args.print not in {'continue', 'c'}:
                        return lambda: None

                return fn(config, **kwargs)

            return main_wrapped

        return main_decorator_wrapper

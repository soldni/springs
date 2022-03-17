import os
from argparse import ArgumentParser
from functools import partial, wraps
from inspect import getfile, getfullargspec, isclass
from typing import Any, Callable, Generic, Optional, Sequence, Type, TypeVar

import yaml

from .functional import config_to_yaml
from .instantiate import InitLater
from .node import ConfigNode, ConfigNodeProps, ParameterSpec
from .utils import (MultiValueEnum, PrintUtils, merge_nested_dicts,
                    read_raw_file, resolve_path)


PS = TypeVar("PS", bound="PrintingSteps")
CLI = TypeVar("CLI", bound="cli")


class PrintEnum(MultiValueEnum):
    PARSED = 'p', 'parsed'
    CONTINUE = 'c', 'continue'
    INPUTS = 'i', 'inputs'
    DEFAULTS = 'd', 'defaults'


class PrintingSteps(Generic[PS]):
    def __init__(self: PS,
                 print_steps: Optional[Sequence[PrintEnum]] = None):
        self.print_steps = set(print_steps) or {PrintEnum.PARSED,
                                                PrintEnum.CONTINUE}

    def do_step(self: PS, step_name: PrintEnum) -> bool:
        if step_name in self.print_steps:
            self.print_steps.remove(step_name)
            return True
        return False

    def has_more_steps(self: PS) -> bool:
        return len(self.print_steps) == 0

    def will_print(self: PS) -> bool:
        return (len(self.print_steps) > 0  and
                self.print_steps != {PrintEnum.CONTINUE})


class cli(Generic[CLI]):
    @classmethod
    def _check_signature(cls: Type[CLI], func: Callable):
        expected_args = getfullargspec(func).args
        if len(expected_args) == 0:
            msg = (f'Function `{func.__name__}` cannot be decorated '
                   f'by `config_to_program` because it does '
                   f'not accept any argument.')
            raise RuntimeError(msg)
        elif len(expected_args) > 1:
            msg = (f'Function `{func.__name__}` cannot be decorated by '
                   f' `config_to_program` because it expects '
                   f'{len(expected_args)} > 1; If you want to pass extra '
                   f'arguments to this function, use kwargs with default '
                   f'values.')
            raise RuntimeError(msg)

    @classmethod
    def _check_args(cls: Type[CLI], func: Callable, args: Sequence[Any]):
        if len(args):
            msg = (f'After decorating `{func.__name__}` with '
                   f'`config_to_program`, do not provide any additional '
                   f'arguments while invoking it; any additional parameter '
                   f'should be passed as a keyword argument.')
            raise RuntimeError(msg)

    @classmethod
    def _make_argument_parser(cls: Type[CLI],
                              func: Callable,
                              config_node: ConfigNode) -> ArgumentParser:
        # setup argparse
        prog = f'Parser for configuration {config_node.__name__}'
        current_dir = resolve_path(os.getcwd()) + '/'
        path_to_fn_file = resolve_path(getfile(func))
        rel_fn_file_path = path_to_fn_file.replace(current_dir, '')
        usage = (f'python3 {rel_fn_file_path} '
                 '{-c/--config config_file.yaml} '
                 '{-p/--print [i, p, w]} '
                 '{-d/--debug} '
                 'param1=value1, …, paramN=valueN')
        ap = ArgumentParser(prog=prog, usage=usage)

        # config option
        msg = ('A path to a YAML file containing a configuration for '
               'this program. It can be in the cloud or local.')
        ap.add_argument('-c', '--config', default=None,
                        help=msg, metavar='/path/to/config.yaml')

        # print option
        msg = ('Options to print configuration. If i/inputs '
               'it prints the input options; if p/parsed, it '
               'prints the parsed configuration; if d/defaults, '
               'it lists all defaults options. Add c/continue '
               'to keep running the program after printing. '
               'Default: "--print d --print c".')
        ap.add_argument('-p', '--print', type=PrintEnum, metavar='flag',
                        action='append', choices=PrintEnum,  help=msg,
                        default=[])

        # debug option
        msg = 'Enter debug mode by setting global logging to DEBUG.'
        ap.add_argument('-d', '--debug', action='store_true', help=msg)

        return ap

    @classmethod
    def _wrapped_main_method(cls: Type[CLI],
                             func: Callable,
                             config_node: ConfigNode,
                             print_fn: Optional[Callable] = None,
                             *args,
                             **kwargs) -> Callable:

        # Making sure I can decorate this function
        cls._check_signature(func=func)
        cls._check_args(func=func, args=args)

        # Get argument parser and arguments
        ap = cls._make_argument_parser(func=func, config_node=config_node)
        opts, _args = ap.parse_known_args()

        # set some default options for when no options are provided
        printing_steps = PrintingSteps(opts.print)

        # setup debug
        if opts.debug:
            # relative import here not to mess things up
            from .logging import configure_logging
            configure_logging.debug()

        # Setup an utility to deal with printing
        pu = PrintUtils(print_fn=print_fn)

        # Print default options if requested py the user
        if printing_steps.do_step(PrintEnum.DEFAULTS):

            params = ConfigNodeProps.get_all_parameters(config_node)

            cli_opts_repr = ('CLI OPTIONS:', ) + tuple(
                f'{p.name}: {p.type.__name__} = {p.default}'
                for p in params
            )

            pu.print(*cli_opts_repr, level_up=1)

        # reads and parse teh command line and file configs (if provided)
        cli_config = merge_nested_dicts(*[
            ParameterSpec.from_string(a).to_dict() for a in _args
        ])
        file_config = (yaml.safe_load(read_raw_file(opts.config))
                        if opts.config else {})

        # merge_nested_dicts is not commutative; cli_config gets
        # precedence over file config.
        config = merge_nested_dicts(file_config, cli_config)

        # print both configs if requested
        if printing_steps.do_step(PrintEnum.INPUTS):
            pu.print('INPUT/COMMAND LINE:', cli_config)
            pu.print('INPUT/CONFIG FILE:', file_config)

        if printing_steps.has_more_steps():
            # nothing more to do, let's not risk
            # parsing, which might cause an error!
           return InitLater.no_op()

        # load configuration with node parsers
        parsed_config = config_node(config)

        # print it if requested
        if printing_steps.do_step(PrintEnum.PARSED):
            pu.print('PARSED CONFIG:', parsed_config, yaml_fn=config_to_yaml)

        if printing_steps.do_step(PrintEnum.CONTINUE):
            # we execute the main method
            return func(parsed_config, **kwargs)

        # this will do nothing when called
        return InitLater.no_op()

    def __new__(cls,
                config_node: Type[ConfigNode],
                print_fn: Optional[Callable] = None) -> partial:
        if not(isclass(config_node) or issubclass(config_node, ConfigNode)):
            msg = f'`config_node` is not a subclass of {ConfigNode.__name__}'
            raise ValueError(msg)

        return lambda func: wraps(func)(partial(cls._wrapped_main_method,
                                                config_node=config_node,
                                                print_fn=print_fn,
                                                func=func))

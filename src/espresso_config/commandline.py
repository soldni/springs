import os
from argparse import ArgumentParser, Namespace
from enum import Enum
from functools import partial, wraps
from inspect import getfile, getfullargspec, isclass
from typing import (Any, Callable, Generic, Optional, Sequence, Type, TypeVar,
                    Union)

from .functional import config_to_yaml
from .instantiate import InitLater
from .node import ConfigNode, ConfigNodeProps, ParameterSpec
from .parser import YamlParser
from .utils import (MISSING, PrintUtils, merge_nested_dicts, read_raw_file,
                    resolve_path)

PS = TypeVar("PS", bound="PrintingSteps")
CLI = TypeVar("CLI", bound="cli")


class CliFlags(Enum):
    CONFIG = 'config'
    PARSED = 'parsed'
    STOP = 'stop'
    INPUTS = 'input'
    OPTIONS = 'options'
    DEBUG = 'debug'


def make_flags(opt_name: CliFlags) -> Sequence[str]:
    return f'-{opt_name.value[0]}', f'--{opt_name.value}'


class PrintingSteps(Generic[PS]):
    def __init__(self: PS, ns: Union[Namespace, dict]):

        # turn the namespace to a dictionary
        ns = vars(ns) if isinstance(ns, Namespace) else ns

        # ignoring whatever is of type missing, i.e. was not provided
        # as well as the configuration path
        cli_flags = {k: v for k, v in ns.items()
                     if (v != MISSING and k != CliFlags.CONFIG.value)}

        # default if none are provided
        cli_flags = (cli_flags or {CliFlags.PARSED: True,
                                   CliFlags.STOP: False,
                                   CliFlags.DEBUG: False})

        # convert to Enum entries
        self.steps = {CliFlags(stp) for stp, flg in cli_flags.items() if flg}

    def do_step(self: PS, step_name: CliFlags) -> bool:
        if step_name in self.steps:
            self.steps.remove(step_name)
            return True
        return False

    def has_more_steps(self: PS) -> bool:
        return self.steps != {CliFlags.STOP}

    def will_print(self: PS) -> bool:
        return self.steps and self.has_more_steps()


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

        usage = (
            f'python3 {rel_fn_file_path} '
            f'{{{"/".join(make_flags(CliFlags.CONFIG))} config_file.yaml}} '
            f'{{{"/".join(make_flags(CliFlags.OPTIONS))}}} '
            f'{{{"/".join(make_flags(CliFlags.INPUTS))}}} '
            f'{{{"/".join(make_flags(CliFlags.DEBUG))}}} '
            f'{{{"/".join(make_flags(CliFlags.PARSED))}}} '
            f'{{{"/".join(make_flags(CliFlags.STOP))}}} '
            'param1=value1, …, paramN=valueN'
        )
        ap = ArgumentParser(prog=prog, usage=usage)

        # add options
        msg = 'A path to a YAML file containing a configuration.'
        ap.add_argument(*make_flags(CliFlags.CONFIG),
                        default=None,
                        help=msg,
                        metavar='/path/to/config.yaml')

        msg = 'Print all default options and CLI flags.'
        ap.add_argument(*make_flags(CliFlags.OPTIONS),
                        action='store_true',
                        default=MISSING,
                        help=msg)

        msg = 'Print the input configuration.'
        ap.add_argument(*make_flags(CliFlags.INPUTS),
                        action='store_true',
                        default=MISSING,
                        help=msg)

        msg = 'Print the parsed configuration.'
        ap.add_argument(*make_flags(CliFlags.PARSED),
                        action='store_true',
                        default=MISSING,
                        help=msg)

        msg = 'Enter debug mode by setting global logging to DEBUG.'
        ap.add_argument(*make_flags(CliFlags.DEBUG),
                        action='store_true',
                        default=MISSING,
                        help=msg)

        msg = 'If provided, it stops running before running the script.'
        ap.add_argument(*make_flags(CliFlags.STOP),
                        action='store_true',
                        default=MISSING,
                        help=msg)
        return ap

    @classmethod
    def _wrapped_main_method(cls: Type[CLI],
                             func: Callable,
                             config_node: ConfigNode,
                             print_fn: Optional[Callable] = None,
                             open_fn: Optional[Callable] = None,
                             *args,
                             **kwargs) -> Callable:

        # Making sure I can decorate this function
        cls._check_signature(func=func)
        cls._check_args(func=func, args=args)

        # Get argument parser and arguments
        ap = cls._make_argument_parser(func=func, config_node=config_node)
        opts, _args = ap.parse_known_args()

        # set some default options for when no options are provided
        printing_steps = PrintingSteps(opts)

        # setup debug
        if opts.debug:
            # relative import here not to mess things up
            from .logging import configure_logging
            configure_logging.debug()

        # Setup an utility to deal with printing
        pu = PrintUtils(print_fn=print_fn)

        # Print default options if requested py the user
        if printing_steps.do_step(CliFlags.OPTIONS):

            params = ConfigNodeProps.get_all_parameters(config_node)

            cli_opts_repr = ('CLI OPTIONS:', ) + tuple(
                f'{p.name}: {p.type.__name__} = ' +
                # represent empty string as ''
                (str(p.default) if p.default != '' else "''")
                for p in params
            )

            pu.print(*cli_opts_repr, level_up=1)

        # reads and parse teh command line and file configs (if provided)
        cli_config = merge_nested_dicts(*[
            ParameterSpec.from_string(a).to_dict() for a in _args
        ])
        file_config = (
            YamlParser.load(read_raw_file(opts.config, open_fn=open_fn))
            if opts.config else {}
        )

        # merge_nested_dicts is not commutative; cli_config gets
        # precedence over file config.
        config = merge_nested_dicts(file_config, cli_config)

        # print both configs if requested
        if printing_steps.do_step(CliFlags.INPUTS):
            pu.print('INPUT/COMMAND LINE:', cli_config)
            pu.print('INPUT/CONFIG FILE:', file_config)

        if not printing_steps.has_more_steps():
            # nothing more to do, let's not risk
            # parsing, which might cause an error!
            return InitLater.no_op()

        # load configuration with node parsers
        parsed_config = config_node(config)

        # print it if requested
        if printing_steps.do_step(CliFlags.PARSED):
            pu.print('PARSED CONFIG:', parsed_config, yaml_fn=config_to_yaml)

        if printing_steps.do_step(CliFlags.STOP):
            # this will do nothing when called
            return InitLater.no_op()

        # we execute the main method
        return func(parsed_config, **kwargs)

    def __new__(cls,
                config_node: Type[ConfigNode],
                print_fn: Optional[Callable] = None,
                open_fn: Optional[Callable] = None) -> partial:
        if not(isclass(config_node) or issubclass(config_node, ConfigNode)):
            msg = f'`config_node` is not a subclass of {ConfigNode.__name__}'
            raise ValueError(msg)

        return lambda func: wraps(func)(partial(cls._wrapped_main_method,
                                                config_node=config_node,
                                                print_fn=print_fn,
                                                open_fn=open_fn,
                                                func=func))

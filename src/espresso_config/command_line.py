import os
from argparse import ArgumentParser
from enum import Enum
from functools import partial, wraps
from inspect import getfile, getfullargspec, isclass
from typing import Any, Callable, Optional, Sequence, Type

from .functional import config_to_yaml
from .instantiate import InitLater
from .node import ConfigNode, ConfigNodeProps, ParameterSpec
from .parser import YamlParser
from .utils import (PrintUtils, merge_nested_dicts, read_raw_file,
                    resolve_path, clean_multiline)


class CliFlags(Enum):
    CONFIG = 'config'
    PARSED = 'parsed'
    QUIET = 'quiet'
    INPUTS = 'inputs'
    OPTIONS = 'options'
    DEBUG = 'debug'


def make_flags(opt_name: CliFlags) -> Sequence[str]:
    """Simple helper to create a list of flags for an
    option based on its name"""
    return f'-{opt_name.value[0]}', f'--{opt_name.value}'


class cli:
    @classmethod
    def _check_signature(cls: Type['cli'], func: Callable):
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
    def _check_args(cls: Type['cli'], func: Callable, args: Sequence[Any]):
        if len(args):
            msg = (f'After decorating `{func.__name__}` with '
                   f'`config_to_program`, do not provide any additional '
                   f'arguments while invoking it; any additional parameter '
                   f'should be passed as a keyword argument.')
            raise RuntimeError(msg)

    @classmethod
    def _make_argument_parser(cls: Type['cli'],
                              func: Callable,
                              config_node: ConfigNode) -> ArgumentParser:
        """Sets up argument parser ahead of running the CLI. This includes
        creating a help message, and adding a series of flags."""

        # we find the path to the script we are decorating with the
        # cli so that we can display that to the user.
        current_dir = resolve_path(os.getcwd()) + '/'
        path_to_fn_file = resolve_path(getfile(func))
        rel_fn_file_path = path_to_fn_file.replace(current_dir, '')

        # Program name and usage printed here.
        prog = f'Parser for configuration {config_node.__name__}'
        usage = clean_multiline(f'''
            python3 {rel_fn_file_path} '
            {{{"/".join(make_flags(CliFlags.CONFIG))} config_file.yaml}}
            {{{"/".join(make_flags(CliFlags.OPTIONS))}}}
            {{{"/".join(make_flags(CliFlags.INPUTS))}}}
            {{{"/".join(make_flags(CliFlags.DEBUG))}}}
            {{{"/".join(make_flags(CliFlags.PARSED))}}}
            {{{"/".join(make_flags(CliFlags.QUIET))}}}
            param1=value1, …, paramN=valueN'
        ''')
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
                        help=msg)

        msg = 'Print the input configuration.'
        ap.add_argument(*make_flags(CliFlags.INPUTS),
                        action='store_true',
                        help=msg)

        msg = 'Print the parsed configuration.'
        ap.add_argument(*make_flags(CliFlags.PARSED),
                        action='store_true',
                        help=msg)

        msg = 'Enter debug mode by setting global logging to DEBUG.'
        ap.add_argument(*make_flags(CliFlags.DEBUG),
                        action='store_true',
                        help=msg)

        msg = 'If provided, it does not print the configuration when running.'
        ap.add_argument(*make_flags(CliFlags.QUIET),
                        action='store_true',
                        help=msg)
        return ap

    @classmethod
    def _wrapped_main_method(cls: Type['cli'],
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
        # printing_steps = PrintingSteps(opts)

        # setup debug
        if opts.debug:
            # relative import here not to mess things up
            from .logging import configure_logging
            configure_logging.debug()

        # Setup an utility to deal with printing
        pu = PrintUtils(print_fn=print_fn)

        # We don't run the main program if the user
        # has requested to print the any of the config.
        do_no_run = (opts.options or opts.inputs or opts.parsed)

        # Print default options if requested py the user
        if opts.options:
            params = ConfigNodeProps.get_all_parameters(config_node)

            cli_opts_repr = ('OPTS/CLI FLAG:', ) + tuple(
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
        if opts.inputs:
            pu.print('INPUT/CLI ARGS:', cli_config)
            pu.print('INPUT/CFG FILE:', file_config)

        if do_no_run and not opts.parsed:
            # if the user hasn't requested to print the parsed config
            # and we are not running the main program, we can exit here.
            return InitLater.no_op()

        # load configuration with node parsers
        parsed_config = config_node(config)

        # print it if requested
        if not(opts.quiet) or opts.parsed:
            pu.print('PARSE/ALL CFG:', parsed_config, yaml_fn=config_to_yaml)

        if do_no_run:
            # we are not running because the user has requested to print
            # either the options, inputs, or parsed config.
            return InitLater.no_op()
        else:
            # we execute the main method and pass the parsed config to it
            return func(parsed_config, **kwargs)

    def __new__(cls: Type['cli'],
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

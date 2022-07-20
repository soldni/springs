import os
from argparse import ArgumentParser
from enum import Enum
from functools import partial
from inspect import getfile, getfullargspec, isclass
from pathlib import Path
from typing import Any, Callable, Optional, Protocol, Sequence, Type, overload

from omegaconf import DictConfig

from .core import (_DataClass, from_dataclass, from_file, from_options, merge,
                   traverse, validate, from_none)
from .initialize import InitLater
from .utils import PrintUtils, clean_multiline


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


class MainFnProtocol(Protocol):
    __name__: str

    @overload
    def __call__(self, config: Any) -> Any:
        ...

    @overload
    def __call__(self, config: Any, *args: Any) -> Any:
        ...

    def __call__(self, config: Any, *args: Any, **kwargs: Any) -> Any:
        ...


class PrintFnProtocol(Protocol):
    def __call__(self, txt: str, /, *args: Any, **kwargs: Any) -> None:
        ...


class DecoratedMainFnProtocol(Protocol):
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        ...


def check_if_callable_can_be_decorated(func: MainFnProtocol):
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
               f'arguments to this function, use kwargs with default values.')
        raise RuntimeError(msg)


def check_if_valid_main_args(func: MainFnProtocol, args: Sequence[Any]):
    if len(args):
        msg = (f'After decorating `{func.__name__}` with '
               f'`config_to_program`, do not provide any additional '
               f'arguments while invoking it; any additional parameter '
               f'should be passed as a keyword argument.')
        raise RuntimeError(msg)


def make_cli_argument_parser(func: MainFnProtocol,
                             name: str) -> ArgumentParser:
    """Sets up argument parser ahead of running the CLI. This includes
    creating a help message, and adding a series of flags."""

    # we find the path to the script we are decorating with the
    # cli so that we can display that to the user.
    current_dir = Path(os.getcwd())
    path_to_fn_file = Path(getfile(func))
    rel_fn_file_path = str(path_to_fn_file).replace(str(current_dir), '')

    # Program name and usage printed here.
    prog = f'Parser for configuration {name}'
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
                    default=[],
                    help=msg,
                    nargs='*',
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


def wrap_main_method(
    func: MainFnProtocol,
    name: str,
    config_node: DictConfig,
    print_fn: Optional[Callable] = None,
    *args: Any,
    **kwargs: Any
) -> Any:

    if not isinstance(config_node, DictConfig):
        raise TypeError("Config node must be a DictConfig")

    # Making sure I can decorate this function
    check_if_callable_can_be_decorated(func=func)
    check_if_valid_main_args(func=func, args=args)

    # Get argument parser and arguments
    ap = make_cli_argument_parser(func=func, name=name)
    opts, leftover_args = ap.parse_known_args()

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
        params = traverse(config_node)

        cli_opts_repr = ('OPTS/CLI FLAG:', ) + tuple(
            f'{p.path} = ' + (str(p.value) if p.value != '' else "''")
            for p in params
        )
        pu.print(*cli_opts_repr, level_up=1)

    # load options from one or more config files;
    # if multiple config files are provided,
    # the latter ones can override the former ones.
    file_config = from_none()
    for config_file in opts.config:
        file_config = merge(file_config, from_file(config_file))

    # load options from cli
    cli_config = from_options(leftover_args)

    # merge file and cli config; cli config overrides file config
    input_config = merge(file_config, cli_config)

    # print both configs if requested
    if opts.inputs:
        pu.print('INPUT/CLI ARGS:', cli_config)
        pu.print('INPUT/CFG FILE:', file_config)

    if do_no_run and not opts.parsed:
        # if the user hasn't requested to print the parsed config
        # and we are not running the main program, we can exit here.
        return InitLater.no_op()

    # load configuration with node parsers
    parsed_config = merge(config_node, input_config)

    # check if all parameters are provided/resolved
    parsed_config = validate(parsed_config)

    # print it if requested
    if not(opts.quiet) or opts.parsed:
        pu.print('PARSE/ALL CFG:', parsed_config)

    if do_no_run:
        # we are not running because the user has requested to print
        # either the options, inputs, or parsed config.
        return InitLater.no_op()
    else:
        # we execute the main method and pass the parsed config to it
        return func(parsed_config, **kwargs)


def cli(
    config_node_cls: Optional[Type[Any]] = None,
    print_fn: Optional[PrintFnProtocol] = None
) -> Callable[[MainFnProtocol], DecoratedMainFnProtocol]:

    if config_node_cls is None:
        config_node = from_none()
        name = '<unnamed>'

    elif not(isclass(config_node_cls) and
             issubclass(config_node_cls, _DataClass)):
        msg = '`config_node` must be be decorated as a dataclass'
        raise ValueError(msg)
    else:
        config_node = from_dataclass(config_node_cls)
        name = config_node_cls.__name__

    def wrapper(func: MainFnProtocol) -> DecoratedMainFnProtocol:
        out = partial(wrap_main_method,
                      func=func,
                      name=name,
                      config_node=config_node,
                      print_fn=print_fn)
        return out

    return wrapper

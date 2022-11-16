import re
import sys
from argparse import Action
from dataclasses import dataclass, fields, is_dataclass
from inspect import getfullargspec, isclass
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
)

from omegaconf import MISSING, DictConfig, ListConfig
from omegaconf.errors import ConfigKeyError, ValidationError
from typing_extensions import Concatenate, ParamSpec

from springs.logging import configure_logging

from .core import (
    from_dataclass,
    from_file,
    from_none,
    from_options,
    merge,
    unsafe_merge,
)
from .rich_utils import (
    RichArgumentParser,
    add_pretty_traceback,
    print_config_as_tree,
    print_table,
)

# parameters for the main function
MP = ParamSpec("MP")

# type for the configuration
CT = TypeVar("CT")

# return type for main function
RT = TypeVar("RT")


@dataclass
class Flag:
    name: str
    help: str
    action: str = MISSING
    default: Optional[Any] = MISSING
    nargs: Optional[Union[str, int]] = MISSING
    metavar: Optional[str] = MISSING
    usage_extras: Optional[str] = MISSING
    choices: Optional[Sequence[Any]] = MISSING

    @property
    def short(self) -> str:
        return f"-{self.name[0]}"

    @property
    def usage(self) -> str:
        extras = (
            "" if self.usage_extras is MISSING else f" {self.usage_extras}"
        )
        return f"{{{self}{extras}}}"

    @property
    def long(self) -> str:
        return f"--{self.name}"

    def add_argparse(self, parser: RichArgumentParser) -> Action:
        kwargs: Dict[str, Any] = {"help": self.help}
        if self.action is not MISSING:
            kwargs["action"] = self.action
        if self.default is not MISSING:
            kwargs["default"] = self.default
        if self.nargs is not MISSING:
            kwargs["nargs"] = self.nargs
        if self.metavar is not MISSING:
            kwargs["metavar"] = self.metavar

        return parser.add_argument(self.short, self.long, **kwargs)

    def __str__(self) -> str:
        return f"{self.short}/{self.long}"


@dataclass
class CliFlags:
    config: Flag = Flag(
        name="config",
        help="A path to a YAML file containing a configuration.",
        default=[],
        action="append",
        metavar="/path/to/yaml",
    )
    options: Flag = Flag(
        name="options",
        help="Print all default options and CLI flags.",
        action="store_true",
    )
    inputs: Flag = Flag(
        name="inputs",
        help="Print the input configuration.",
        action="store_true",
    )
    parsed: Flag = Flag(
        name="parsed",
        help="Print the parsed configuration.",
        action="store_true",
    )
    log_level: Flag = Flag(
        name="log-level",
        help=(
            "Logging level to use for this program. Can be one of "
            "CRITICAL, ERROR, WARNING, INFO, or DEBUG. Defaults to WARNING."
        ),
        default="WARNING",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
    )
    debug: Flag = Flag(
        name="debug",
        help="Enable debug mode; equivalent to --log-level DEBUG.",
        action="store_true",
    )
    quiet: Flag = Flag(
        name="quiet",
        help="If provided, it does not print the configuration when running.",
        action="store_true",
    )
    resolvers: Flag = Flag(
        name="resolvers",
        help=(
            "Print all registered resolvers in OmegaConf, "
            "Springs, and current codebase."
        ),
        action="store_true",
    )
    nicknames: Flag = Flag(
        name="nicknames",
        help="Print all registered nicknames in Springs.",
        action="store_true",
    )

    @property
    def flags(self) -> Iterable[Flag]:
        for f in fields(self):
            maybe_flag = getattr(self, f.name)
            if isinstance(maybe_flag, Flag):
                yield maybe_flag

    def add_argparse(self, parser: RichArgumentParser) -> Sequence[Action]:
        return [flag.add_argparse(parser) for flag in self.flags]

    def make_cli(self, func: Callable, name: str) -> RichArgumentParser:
        """Sets up argument parser ahead of running the CLI. This includes
        creating a help message, and adding a series of flags."""
        # Program name and usage added here.
        ap = RichArgumentParser(
            description=f"Parser for configuration {name}",
            entrypoint=sys.argv[0],
            arguments="param1=value1 … paramN=valueN",
        )
        self.add_argparse(ap)
        return ap


def check_if_callable_can_be_decorated(func: Callable):
    expected_args = getfullargspec(func).args
    if len(expected_args) == 0:
        msg = (
            f"Function `{func.__name__}` cannot be decorated "
            f"by `config_to_program` because it does "
            f"not accept any argument."
        )
        raise RuntimeError(msg)
    elif len(expected_args) > 1:
        msg = (
            f"Function `{func.__name__}` cannot be decorated by "
            f" `config_to_program` because it expects "
            f"{len(expected_args)} > 1; If you want to pass extra "
            f"arguments to this function, use kwargs with default values."
        )
        raise RuntimeError(msg)


def check_if_valid_main_args(func: Callable, args: Sequence[Any]):
    if len(args):
        msg = (
            f"After decorating `{func.__name__}` with "
            f"`config_to_program`, do not provide any additional "
            f"arguments while invoking it; any additional parameter "
            f"should be passed as a keyword argument."
        )
        raise RuntimeError(msg)


C = TypeVar("C", DictConfig, ListConfig)


def merge_and_catch(c1: C, c2: Union[DictConfig, ListConfig]) -> C:
    """Improves printing of errors when merging configs in cli."""
    try:
        return merge(c1, c2)
    except Exception as e:
        prefix = "Error when merging cli options and files with struct config:"

        if isinstance(e, ConfigKeyError):
            msg, *_ = e.args[0].split("\n")
        elif isinstance(e, ValidationError):
            msg, key, *_ = e.args[0].split("\n")
            _, key = key.split("full_key: ", 1)
            msg = f"{msg} for key '{key}'"
        else:
            msg = str(e.args)

        raise type(e)(f"{prefix} {msg}!")


def validate_leftover_args(args: Sequence[str]):
    var_pattern = r"[a-zA-Z_]+[a-zA-Z0-9_]*"
    re_valid = re.compile(rf"({var_pattern}\.?)*{var_pattern}=.+")
    for arg in args:
        if not re_valid.match(arg):
            raise ValueError(
                f"'{arg}' is not an option and it does not match the pattern "
                "'path.to.key=value' expected for a cli config override."
            )


def wrap_main_method(
    func: Callable[Concatenate[Any, MP], RT],
    name: str,
    config_node: DictConfig,
    *args: MP.args,
    **kwargs: MP.kwargs,
) -> RT:

    if not isinstance(config_node, DictConfig):
        raise TypeError("Config node must be a DictConfig")

    # Making sure I can decorate this function
    check_if_callable_can_be_decorated(func=func)
    check_if_valid_main_args(func=func, args=args)

    # Get argument parser and arguments
    ap = CliFlags().make_cli(func=func, name=name)
    opts, leftover_args = ap.parse_known_args()

    # Checks if the args are a match for the 'path.to.key=value′ pattern
    # expected for configuration overrides.
    validate_leftover_args(leftover_args)

    # setup logging level for the root logger
    configure_logging(logging_level="DEBUG" if opts.debug else opts.log_level)

    # We don't run the main program if the user
    # has requested to print the any of the config.
    do_no_run = (
        opts.options
        or opts.inputs
        or opts.parsed
        or opts.resolvers
        or opts.nicknames
    )

    if opts.resolvers:
        # relative import here not to mess things up
        from .resolvers import all_resolvers

        print_table(
            title="Registered Resolvers",
            columns=["Resolver Name"],
            values=[(r,) for r in sorted(all_resolvers())],
            caption=(
                "Resolvers use syntax ${resolver_name:'arg1','arg2'}.\n"
                "For more information, visit https://omegaconf.readthedocs.io/"
                "en/latest/custom_resolvers.html"
            ),
        )

    if opts.nicknames:
        from .nicknames import NicknameRegistry

        print_table(
            title="Registered Nicknames",
            columns=["Nickname", "Path"],
            values=NicknameRegistry().all(),
            caption=(
                "Nicknames are invoked via: "
                "${sp.from_node:nickname,'path.to.key1=value1',...}. "
                "\nOverride keys are optional (but quotes are required)."
            ),
        )

    # Print default options if requested py the user
    if opts.options:
        print_config_as_tree(title="Default Options", config=config_node)

    # This configuration is used to accumulate all options across
    # various config files and the CLI.
    accumulator_config = unsafe_merge(config_node)

    # load options from one or more config files; if multiple config files
    # are provided, the latter ones can override the former ones.
    for config_file in opts.config:
        # load the file
        file_config = from_file(config_file)

        # print the configuration if requested by the user
        if opts.inputs:
            print_config_as_tree(
                title=f"Input From File {config_file}",
                config=file_config,
                title_color="blue",
            )

        # merge the file config with the main config
        accumulator_config = unsafe_merge(accumulator_config, file_config)

    # load options from cli
    cli_config = from_options(leftover_args)

    # print the configuration if requested by the user
    if opts.inputs:
        print_config_as_tree(
            title="Input From Command Line",
            config=cli_config,
            title_color="red",
        )

    # merge the cli config with the main config, do it last
    # so that cli takes precedence over config files.
    accumulator_config = unsafe_merge(accumulator_config, cli_config)

    if do_no_run and not opts.parsed:
        # if the user hasn't requested to print the parsed config
        # and we are not running the main program, we can exit here.
        sys.exit(0)

    # finally merge the accumulator config with the main config
    # using the safe merging function, which will resolve interpolations
    # and perform type checking.
    parsed_config = merge_and_catch(config_node, accumulator_config)

    # print it if requested
    if not (opts.quiet) or opts.parsed:
        print_config_as_tree(
            title="Parsed Config",
            config=parsed_config,
            title_color="green",
        )

    if do_no_run:
        # we are not running because the user has requested to print
        # either the options, inputs, or parsed config.
        sys.exit(0)
    else:
        # we execute the main method and pass the parsed config to it
        return func(parsed_config, *args, **kwargs)


def cli(
    config_node_cls: Optional[Type[CT]] = None,
) -> Callable[
    [
        # this is a main method that takes as first input a parsed config
        Callable[Concatenate[CT, MP], RT]
    ],
    # the decorated method doesn't expect the parsed config as first input,
    # since that will be parsed from the command line
    Callable[MP, RT],
]:
    """
    Create a command-line interface for a method that uses a config file.
    The parsed configuration will be passed as the first argument to the
    decorated method.

    Example usage:

    ```python

    import springs as sp

    @sp.dataclass
    class Config:
        greeting: str = "Hello"
        name: str = "World"


    @sp.cli(Config)
    def main(cfg: Config):
        print(f"{cfg.greeting}, {cfg.name}!")
    ```

    A structured configuration is not required, but it is recommended,
    as it will allow for type checking at runtime and type hints during
    development.

    Args:
        config_node_cls (Optional[type]): The class of the configuration
            node. If not provided, no type checking will be performed.

    Returns:
        Callable: A decorator that can be used to decorate a method.
    """

    # setup nice traceback through rich library
    add_pretty_traceback()

    if config_node_cls is None:
        config_node = from_none()
        name = "<unnamed>"

    elif not (isclass(config_node_cls) and is_dataclass(config_node_cls)):
        msg = "`config_node` must be be decorated as a dataclass"
        raise ValueError(msg)
    else:
        config_node = from_dataclass(config_node_cls)
        name = config_node_cls.__name__

    def wrapper(func: Callable[Concatenate[CT, MP], RT]) -> Callable[MP, RT]:
        def wrapping(*args: MP.args, **kwargs: MP.kwargs) -> RT:
            # I could have used a functools.partial here, but defining
            # my own function instead allows me to provide nice typing
            # annotations for mypy.
            return wrap_main_method(
                func,
                name,
                config_node,
                *args,
                **kwargs,
            )

        return wrapping

    return wrapper

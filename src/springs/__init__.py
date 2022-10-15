from dataclasses import dataclass, field

from omegaconf import MISSING, DictConfig, ListConfig

from .commandline import cli
from .core import (
    DEFAULT,
    cast,
    edit_list,
    from_dataclass,
    from_dict,
    from_file,
    from_none,
    from_options,
    from_python,
    from_string,
    merge,
    resolve,
    to_dict,
    to_json,
    to_python,
    to_yaml,
    unsafe_merge,
    validate,
)
from .flexyclasses import flexyclass
from .initialize import Target, init
from .logging import configure_logging
from .resolvers import all_resolvers, register
from .shortcuts import (
    fdict,
    flist,
    get_nickname,
    make_flexy,
    make_target,
    nickname,
    toggle_warnings,
)
from .traversal import traverse
from .types import get_type
from .utils import get_version

__version__ = get_version()

__all__ = [
    "all_resolvers",
    "cast",
    "cli",
    "configure_logging",
    "dataclass",
    "DEFAULT",
    "DictConfig",
    "edit_list",
    "fdict",
    "field",
    "flexyclass",
    "flist",
    "from_dataclass",
    "from_dict",
    "from_file",
    "from_none",
    "from_options",
    "from_python",
    "from_string",
    "get_nickname",
    "get_type",
    "init",
    "ListConfig",
    "make_flexy",
    "make_target",
    "merge",
    "MISSING",
    "nickname",
    "register",
    "resolve",
    "Target",
    "to_dict",
    "to_json",
    "to_python",
    "to_yaml",
    "toggle_warnings",
    "traverse",
    "unsafe_merge",
    "validate",
]

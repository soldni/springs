import copy
import errno
import itertools
import os
import re
import shutil
from dataclasses import dataclass, field
from enum import Enum
from textwrap import dedent
from typing import Any, Callable, Optional, OrderedDict, Sequence, Type

from .parser import YamlParser


def clean_multiline(string: str) -> str:
    string = dedent(string.strip())
    string = re.sub(r'\s*\n\s*', ' ', string)
    return string


def merge_nested_dicts(*dicts: Sequence[dict]) -> dict:
    # all the merging is done in a new dict, not in place
    # important to sort: sometimes different keys get merged into
    # the same key once a dict is resolved to a config, and
    # that only happens if we keep track for the order
    out = OrderedDict()

    for d in dicts:
        for k, v in d.items():
            # k altready exists in out, and both subkeys
            # are dictionaries: we recursively call merge_nested_dicts
            is_subdict_to_merge = (k in out and
                                   isinstance(v, dict) and
                                   isinstance(out[k], dict))
            if is_subdict_to_merge:
                v = merge_nested_dicts(out[k], v)

            # assign either the value v or the nested merge
            out[k] = copy.deepcopy(v)

    return out


class MultiValueEnum(Enum):
    """An enum that can accept multiple values.
    Adapted from https://stackoverflow.com/a/43210118"""

    def __new__(cls, *values):
        obj = object.__new__(cls)

        # first value is canonical value
        obj._value_, *other_values = values

        # the others are mapped to the canonical
        for other_value in other_values:
            cls._value2member_map_[other_value] = obj
        obj._all_values = values
        return obj

    def __repr__(self):
        all_values = ', '.join(repr(v) for v in self._all_values)
        return f'<{self.__class__.__name__}.{self._name_}: {all_values}>'

    @classmethod
    def items(cls):
        return iter(cls)

    @classmethod
    def keys(cls):
        return (elem._name_ for elem in cls.items())

    @classmethod
    def values(cls):
        return itertools.chain.from_iterable(
            elem._all_values for elem in cls.items()
        )


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise
    return path


class hybrid_method:
    """A decorator that allows overloading a method depending
    on whether it is a class method or instance method. From
    https://stackoverflow.com/a/28238047"""

    def __init__(self, f_class, finstance=None, doc=None):
        self.f_class = f_class
        self.f_instance = finstance
        self.__doc__ = doc or f_class.__doc__
        # support use on abstract base classes
        self.__isabstractmethod__ = bool(
            getattr(f_class, '__isabstractmethod__', False)
        )

    def class_method(self, f_class):
        return type(self)(f_class, self.f_instance, None)

    def instance_method(self, f_instance):
        return type(self)(self.f_class, f_instance, self.__doc__)

    def __get__(self, instance, cls):
        if instance is None or self.f_instance is None:
            # either bound to the class, or no instance method available
            return self.f_class.__get__(cls, None)
        return self.f_instance.__get__(instance, cls)


@dataclass
class PrintUtils:
    """A few utilities to make printing easier"""

    indent_step: int = 2
    indent_char: str = ' '
    separator_char: str = '-'
    terminal_width: int = field(default=shutil.get_terminal_size().columns)
    print_fn: Callable = None

    def __post_init__(self):
        self.print_fn = self.print_fn or print
        self.has_printed_first_separator = False
        self.is_default_print = self.print_fn is print

    def print(self,
              *lines,
              level: int = 0,
              level_up: int = None,
              yaml_fn: Callable = None):

        # avoid circular imports
        from .node import ConfigNode

        level_up = level_up or float('inf')

        content = ''
        if self.is_default_print:
            if not self.has_printed_first_separator:
                content += self.separator()
            self.has_printed_first_separator = True

        for line in lines:
            if not line:
                # backtrack the new line you just added from previous
                # argument if the current argument evaluates to none, like
                # an empty string, or an empty dict
                content = f'{content.rstrip()} '

            if isinstance(line, (dict, ConfigNode)):
                content += f'{self.to_yaml(line, level, yaml_fn)}\n'
            else:
                content += f'{self.indent(line, level)}\n'

            if level < level_up:
                level += 1

        if self.is_default_print:
            content += f'{self.separator()}\n'

        self.print_fn(content.rstrip())

    def indent(self, line: str, level: int) -> str:
        indent = self.indent_char * level * self.indent_step
        return indent + line

    def separator(self, level: int = 0) -> str:
        separator = self.separator_char * self.terminal_width
        return self.indent(separator, level=level)

    def to_yaml(self,
                content: dict,
                level: int = 0,
                yaml_fn: Callable = None) -> dict:
        if not content:
            # this is in case the dict/list is empty
            return str(content)

        yaml_fn = yaml_fn or YamlParser.dump

        out = yaml_fn(content,
                      indent=self.indent_step,
                      width=self.terminal_width,
                      default_flow_style=False)
        out = '\n'.join(self.indent(ln, level)
                        for ln in out.strip().split('\n')).rstrip()
        return out


class FLAG(type):
    SYMBOL: str
    __YAML__: dict = {}

    def __str__(cls) -> str:
        return cls.SYMBOL

    def __repr__(cls) -> str:
        return f'{cls.__name__}({str(cls)})'

    def __bool__(cls) -> bool:
        return False

    @classmethod
    def yaml(cls, flag_cls):
        cls.__YAML__[str(flag_cls)] = flag_cls
        return YamlParser.register(
            node_type=cls,
            node_dump=str,
            node_load=lambda s: cls.__YAML__[s]
        )(flag_cls)


@FLAG.yaml
class MISSING(metaclass=FLAG):
    """Used to keep track of missing parameters"""
    SYMBOL = '???'


@FLAG.yaml
class FUTURE(metaclass=FLAG):
    """Used to keep track of parameters that we know be provided later"""
    SYMBOL = '>>>'


@FLAG.yaml
class OPTIONAL(metaclass=FLAG):
    """Used to keep track of parameters that we know be provided later"""
    SYMBOL = '***'


def type_evaluator(field_type: Type[Any]) -> Callable:
    """Constructs a simple eval function for command line args
    that does proper casting depending on field_type"""

    def _type_fn(value: str) -> field_type:
        if not issubclass(field_type, str):
            # we use yaml to do the casting!
            value = YamlParser.load(value)

        return field_type(value)
    return _type_fn


def read_raw_file(file_path: str,
                  open_fn: Optional[Callable] = None) -> str:
    """For reading the content of a file."""
    open_fn = open_fn or open
    with open_fn(file_path, mode='r', encoding='utf-8') as f:
        content = f.read()
    return content


def resolve_path(path: str) -> str:
    return os.path.realpath(
        os.path.abspath(
            os.path.expanduser(path)
            if '~' in path
            else path
        )
    )

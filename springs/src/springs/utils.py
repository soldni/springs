from functools import wraps
import hashlib
import pickle
import re
import shutil
from dataclasses import dataclass, field
from textwrap import dedent
from typing import Any, Callable, Optional, Sequence, Union
from pathlib import Path

import yaml
from omegaconf import DictConfig, OmegaConf


def clean_multiline(string: str) -> str:
    string = dedent(string.strip())
    string = re.sub(r'\s*\n\s*', ' ', string)
    return string


@dataclass
class PrintUtils:
    """A few utilities to make printing easier"""

    indent_step: int = 2
    indent_char: str = ' '
    separator_char: str = '-'
    terminal_width: int = field(default=shutil.get_terminal_size().columns)
    print_fn: Optional[Callable] = field(default_factory=lambda: print)

    def __post_init__(self):
        self.print_fn = self.print_fn or print
        self.has_printed_first_separator = False
        self.is_default_print = self.print_fn is print

    def print(self,
              *lines: Union[str, dict, DictConfig],
              level: int = 0,
              level_up: Optional[int] = None):

        level_up = level_up or float('inf')     # type: ignore

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

            if isinstance(line, DictConfig):
                line = OmegaConf.to_container(line)

            if isinstance(line, dict):
                content += f'{self.to_yaml(line, level)}\n'
            else:
                content += f'{self.indent(line, level)}\n'

            level += 1 if level < level_up else 0   # type: ignore

        if self.is_default_print:
            content += f'{self.separator()}\n'

        self.print_fn(content.rstrip())     # type: ignore

    def indent(self, line: str, level: int) -> str:
        indent = self.indent_char * level * self.indent_step
        return indent + line

    def separator(self, level: int = 0) -> str:
        separator = self.separator_char * self.terminal_width
        return self.indent(separator, level=level)

    def to_yaml(self, content: dict, level: int = 0) -> str:
        if not content:
            # this is in case the dict/list is empty
            return str(content)

        out = yaml.dump(content,
                        indent=self.indent_step,
                        width=self.terminal_width,
                        default_flow_style=False)
        out = '\n'.join(self.indent(ln, level)
                        for ln in out.strip().split('\n')).rstrip()
        return out


def cache_to_disk(kwargs: Optional[Sequence[str]] = None,
                  location: Optional[Union[str, Path]] = None) -> Callable:
    """Decorator to cache a function's output to disk.

    Args:
        kwargs: The name of the values in the function's signature to
            use to determine the filename of the cache file.
            If None, all values are used.
        location: The directory where the cache file will be stored.
            If None, ~/.cache is used.

    Returns:
        A decorator that enables caches the output of a function
            decorated with it.
    """
    if location is None:
        location = (Path('~') / '.cache').expanduser().absolute()
    location = Path(location)

    # make caching directory if it doesn't exist
    if not location.exists():
        location.mkdir(parents=True)

    def decorator(func: Callable,
                  kwargs_to_cache: Optional[Sequence[str]] = kwargs,
                  location: Path = location) -> Callable:

        @wraps(func)
        def wrapper(
            *args,
            __kwargs_to_cache__: Optional[Sequence[str]] = kwargs_to_cache,
            __location__: Path = location,
            __invalidate__: bool = False,
            **kwargs: Any
        ) -> Any:
            if args:
                msg = 'You cannot pass non-positional arguments when caching'
                raise ValueError(msg)

            # always cache in the same order
            if __kwargs_to_cache__ is None:
                __kwargs_to_cache__ = tuple(kwargs.keys())
            __kwargs_to_cache__ = sorted(__kwargs_to_cache__)

            # hash all kwargs
            h = hashlib.sha1()
            for k, v in kwargs.items():

                if k in __kwargs_to_cache__:
                    # include name of key in cache name
                    h.update(pickle.dumps((k, v)))

            # digest and give .pickle extension
            cache_path = __location__ / f'{h.hexdigest()}.pickle'

            if not cache_path.exists() or __invalidate__:
                # cache miss
                resp = func(**kwargs)
                with open(cache_path, 'wb') as f:
                    pickle.dump(resp, f)
            else:
                # cache hit
                with open(cache_path, 'rb') as f:
                    resp = pickle.load(f)

            # return whatever the function returns
            return resp

        return wrapper

    return decorator

import re
import shutil
from textwrap import dedent
from typing import Callable, Optional, Union

import yaml
from omegaconf import DictConfig, OmegaConf


def clean_multiline(string: str) -> str:
    string = dedent(string.strip())
    string = re.sub(r'\s*\n\s*', ' ', string)
    return string


class PrintUtils:
    """A few utilities to make printing easier"""

    def __init__(self,
                 indent_step: int = 2,
                 indent_char: str = ' ',
                 separator_char: str = '-',
                 terminal_width: Optional[int] = None,
                 print_fn: Optional[Callable[..., None]] = None) -> None:
        self.indent_step = indent_step
        self.indent_char = indent_char
        self.separator_char = separator_char
        self.terminal_width = (terminal_width or
                               shutil.get_terminal_size().columns)
        self.print_fn = print_fn or print
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
                content += f'{self.indent(str(line), level)}\n'

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

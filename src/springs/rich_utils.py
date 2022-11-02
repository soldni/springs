import os
from argparse import SUPPRESS, ArgumentParser
from typing import IO, Any, Dict, List, Optional, Sequence, Union

from omegaconf import DictConfig, ListConfig
from rich.console import Console, Group
from rich.panel import Panel
from rich.style import Style
from rich.table import Column, Table
from rich.text import Text
from rich.traceback import install
from rich.tree import Tree

from .core import traverse
from .utils import SpringsConfig


def add_pretty_traceback(**install_kwargs: Any) -> None:
    if SpringsConfig.RICH_TRACEBACK_INSTALLED:
        return

    # override any default settings if provided
    install_kwargs = {
        **dict(show_locals=SpringsConfig.RICH_LOCALS),
        **install_kwargs,
    }

    # setup nice traceback through rich library
    install(**install_kwargs)

    # mark as installed; prevent double installation.
    # this is a global setting.
    SpringsConfig.RICH_TRACEBACK_INSTALLED = True


def print_table(
    title: str,
    columns: Sequence[str],
    values: Sequence[Sequence[Any]],
    colors: Optional[Sequence[str]] = None,
    caption: Optional[str] = None,
):
    colors = list(
        colors or ["magenta", "cyan", "red", "green", "yellow", "blue"]
    )
    if len(columns) > len(colors):
        # repeat colors if we have more columns than colors
        colors = colors * (len(columns) // len(colors) + 1)

    def _get_longest_row(text: str) -> int:
        return max(len(row) for row in text.splitlines())

    min_width = min(
        max(_get_longest_row(title), _get_longest_row(caption or "")) + 2,
        os.get_terminal_size().columns - 2,
    )

    table = Table(
        *(
            Column(column, justify="center", style=color, vertical="middle")
            for column, color in zip(columns, colors)
        ),
        title=f"\n{title}",
        min_width=min_width,
        caption=caption,
        title_style="bold",
        caption_style="grey74",
    )
    for row in values:
        table.add_row(*row)

    Console().print(table)


def print_config_as_tree(
    title: str,
    config: Union[DictConfig, ListConfig],
    title_color: str = "default",
):
    def get_parent_path(path: str) -> str:
        return path.rsplit(".", 1)[0] if "." in path else ""

    root = Tree(f"[{title_color}][bold]{title}[bold][/{title_color}]")
    trees: Dict[str, Tree] = {"": root}
    nodes_order: Dict[str, Dict[str, int]] = {}

    all_nodes = sorted(
        traverse(config, include_nodes=True, include_leaves=False),
        key=lambda spec: spec.path.count("."),
    )
    for spec in all_nodes:
        parent_path = get_parent_path(spec.path)
        tree = trees.get(parent_path, None)
        if spec.key is None or tree is None:
            raise ValueError("Cannot print disjoined tree")

        label = "[bold {color}]{repr}[/bold {color}]".format(
            color="magenta" if isinstance(spec.value, DictConfig) else "cyan",
            repr=spec.key if isinstance(spec.key, str) else f"[{spec.key}]",
        )
        subtree = tree.add(label=label)
        trees[spec.path] = subtree
        nodes_order.setdefault(parent_path, {})[label] = spec.position

    for spec in traverse(config, include_nodes=False, include_leaves=True):
        parent_path = get_parent_path(spec.path)
        tree = trees.get(parent_path, None)
        if tree is None:
            raise ValueError("Cannot print disjoined tree")

        label = (
            f"[bold]{spec.key}[/bold] ({spec.type.__name__}) = {spec.value}"
        )
        tree.add(label=label)
        nodes_order.setdefault(parent_path, {})[label] = spec.position

    for label, tree in trees.items():
        # sort nodes in each tree to match the order the appear in the config
        tree.children.sort(
            key=lambda child: nodes_order[label][str(child.label)]
        )

    panel = Panel(root, padding=0, border_style=Style(conceal=True))
    Console().print(panel)


class RichArgumentParser(ArgumentParser):
    def __init__(
        self,
        *args,
        entrypoint: Optional[str] = None,
        arguments: Optional[str] = None,
        console_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.entrypoint = entrypoint
        self.arguments = arguments
        self.formatted: Dict[str, Any] = {}
        self.console_kwargs = console_kwargs or {}

    def format_usage(self):
        if self.entrypoint is not None and self.arguments is not None:
            flags: List[str] = []

            for ag in self._action_groups:
                for act in ag._group_actions:

                    if isinstance(act.metavar, str):
                        metavar = (act.metavar,)
                    elif act.metavar is None:
                        metavar = (act.dest.upper(),)
                    else:
                        metavar = act.metavar

                    if isinstance(act.nargs, int):
                        metavar = metavar * act.nargs
                    elif act.nargs == "?":
                        metavar = ("[" + metavar[0] + "]?",)
                    elif len(metavar) == 1:
                        metavar = metavar + ("...",)

                    options = "/".join(act.option_strings)
                    flag = "{" + options + "} " + ", ".join(metavar)
                    flags.append(flag.strip())

            usage = (
                "[green]python[/green] "
                + f"[magenta][bold]{self.entrypoint}[/bold][/magenta] "
                + "[yellow]"
                + " ".join(flags)
                + "[/yellow]"
                + f" {self.arguments}"
            )
        else:
            usage = self.usage

        if usage is not None:
            return Panel(
                usage,
                title="[bold][cyan] Usage [cyan][/bold]",
                title_align="center",
            )

    def format_help(self):
        groups = []

        if self.description:
            description = Panel(
                Text(f"{self.description}", justify="center"),
                style=Style(bold=True),
                border_style=Style(conceal=True),
            )
            groups.append(description)

        if (usage := self.format_usage()) is not None:
            groups.append(usage)

        for ag in self._action_groups:
            if len(ag._group_actions) == 0:
                continue

            table = Table(
                show_edge=False,
                show_header=False,
                border_style=Style(bold=False, conceal=True),
            )
            table.add_column(
                "Flag", style=Style(color="magenta"), justify="left"
            )
            table.add_column(
                "Default", style=Style(color="yellow"), justify="center"
            )
            table.add_column(
                "Action", style=Style(color="red"), justify="center"
            )
            table.add_column(
                "Description", style=Style(color="green"), justify="left"
            )
            table.add_row(
                *(f"[bold]{c.header}[/bold]" for c in table.columns),
            )

            for action in ag._group_actions:
                if action.default == SUPPRESS or action.default is None:
                    default = "-"
                else:
                    default = repr(action.default)

                if action.nargs is None:
                    nargs = type(action).__name__.strip("_")[0]
                elif action.nargs == 0:
                    nargs = "-"
                else:
                    nargs = str(action.nargs)

                table.add_row(
                    "/".join(action.option_strings),
                    default,
                    nargs,
                    (action.help or "").capitalize(),
                )

            panel = Panel(
                table,
                title=(
                    Text(
                        ag.title.capitalize(),
                        style=Style(bold=True, color="cyan"),
                    )
                    if ag.title
                    else None
                ),
                title_align="center",
            )
            groups.append(panel)

        return Panel(
            Group(*groups),
            border_style=Style(conceal=True),
        )

    def _print_message(
        self, message: Any, file: Optional[IO[str]] = None
    ) -> None:
        console = Console(**{**self.console_kwargs, "file": file})
        console.print(message)

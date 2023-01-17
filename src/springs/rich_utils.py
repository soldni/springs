import os
import re
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


GREY = "grey74"


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
    print_help: bool = False,
):
    def get_parent_path(path: str) -> str:
        return path.rsplit(".", 1)[0] if "." in path else ""

    root = Tree(f"[{title_color}][bold]{title}[/bold][/{title_color}]")
    trees: Dict[str, Tree] = {"": root}
    nodes_order: Dict[str, Dict[str, int]] = {}

    # STEP 1: We start by adding all nodes to the tree; a node is a
    #         DictConfig or ListConfig that has children.
    all_nodes = sorted(
        traverse(config, include_nodes=True, include_leaves=False),
        key=lambda spec: spec.path.count("."),
    )
    for spec in all_nodes:
        parent_path = get_parent_path(spec.path)
        tree = trees.get(parent_path, None)
        if spec.key is None or tree is None:
            raise ValueError("Cannot print disjoined tree")

        # color is different for DictConfig and ListConfig
        l_color = "magenta" if isinstance(spec.value, DictConfig) else "cyan"
        l_text = spec.key if isinstance(spec.key, str) else f"[{spec.key}]"
        label = f"[bold {l_color}]{l_text}[/bold {l_color}]"

        # Add help if available; make it same color as the key, but italic
        # instead of bold. Note that we print the help iff print_help is True.
        # We also remove any newlines and extra spaces from the help using
        # a regex expression.
        if spec.help and print_help:
            l_help = re.sub(r"\s+", " ", spec.help.strip())
            label = f"{label}\n[{l_color} italic]({l_help})[/italic {l_color}]"

        # Actually adding the node here!
        subtree = tree.add(label=label)

        # We need to keep track of each node in the tree separately; this
        # is so that we can attach the leaves to the correct node later.
        trees[spec.path] = subtree

        # This helps us remember the order nodes appear in the config
        # created by the user. We use this to sort the nodes in the tree
        # before printing.
        nodes_order.setdefault(parent_path, {})[label] = spec.position

    # STEP 2: We now add all leaves to the tree; a leaf is anything that
    #         is not a DictConfig or ListConfig.
    all_leaves = sorted(
        traverse(config, include_nodes=False, include_leaves=True),
        key=lambda spec: str(spec.key),
    )
    for spec in all_leaves:
        parent_path = get_parent_path(spec.path)
        tree = trees.get(parent_path, None)
        if tree is None:
            raise ValueError("Cannot find node for this leaf")

        # Using '???' to indicate unknown type
        type_name = spec.type.__name__ if spec.type else "???"
        label = f"[bold]{spec.key}[/bold] ({type_name}) = {spec.value}"

        # Add help if available; print it a gray color and italic.
        if spec.help and print_help:
            l_help = re.sub(r"\s+", " ", spec.help.strip())
            label = f"{label}\n[{GREY} italic]({l_help})[/{GREY} italic]"

        # Actually adding the leaf here!
        tree.add(label=label)

        # This helps us remember the order leaves appear in the config
        # created by the user. We use this to sort the nodes in the tree
        # before printing.
        nodes_order.setdefault(parent_path, {})[label] = spec.position

    # STEP 3: sort nodes in each tree to match the order the appear
    #         in the config created by the user.
    for l, t in trees.items():  # noqa: E741
        t.children.sort(key=lambda child: nodes_order[l][str(child.label)])

    # STEP 4: if there are no nodes or leaves in this configuration, add a
    #         message to the tree that indicates that the config is empty.
    if len(all_leaves) == len(all_nodes) == 0:
        root = Tree(f"{root.label}\n  [{GREY} italic](empty)[/{GREY} italic]")

    # time to print!
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
                    (action.help or ""),
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

import os
from argparse import ArgumentParser, HelpFormatter
from typing import IO, Any, Dict, Optional, Sequence, Type, Union

from omegaconf import DictConfig, ListConfig
from rich.console import Console
from rich.table import Column, Table
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


def print_config_as_tree(title: str, config: Union[DictConfig, ListConfig]):
    def get_parent_path(path: str) -> str:
        return path.rsplit(".", 1)[0] if "." in path else ""

    trees: Dict[str, Tree] = {"": (root := Tree(f"[bold]\n{title}[/bold]"))}
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

    Console().print(root)


class RichFormatter(HelpFormatter):
    ...


class RichArgumentParser(ArgumentParser):
    def __init__(
        self,
        *args,
        formatter_class: Type[HelpFormatter] = RichFormatter,
        console_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.console_kwargs = console_kwargs or {}

    def _print_message(
        self, message: Any, file: Optional[IO[str]] = None
    ) -> None:
        console = Console(**{**self.console_kwargs, "file": file})
        console.print(message)

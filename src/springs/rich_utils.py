import os
import re
from argparse import SUPPRESS, ArgumentParser
from dataclasses import dataclass
from typing import IO, Any, Dict, Generator, List, Optional, Sequence, Union

from omegaconf import DictConfig, ListConfig
from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.style import Style
from rich.table import Column, Table
from rich.text import Text
from rich.traceback import install
from rich.tree import Tree

from . import MISSING
from .core import traverse
from .utils import SpringsConfig

__all__ = [
    "RichArgumentParser",
    "ConfigTreeParser",
    "TableParser",
    "add_pretty_traceback",
]


def _s(
    *,
    c: Optional[str] = None,
    b: Optional[bool] = None,
    i: Optional[bool] = None,
    u: Optional[bool] = None,
    d: Optional[bool] = None,
    r: Optional[bool] = None,
    l: Optional[bool] = None,  # noqa: E741
) -> Style:
    return Style(
        color=c, bold=b, italic=i, underline=u, dim=d, conceal=l, reverse=r
    )


@dataclass
class SpringsTheme:
    _rich: bool = Console().color_system not in {"standard", "windows"}
    _real: bool = Console().is_terminal

    # # # # # # # # # # # # # Configuration Trees # # # # # # # # # # # # # # #

    r_title: Style = (
        _s(b=True) if _rich else (_s(u=True, d=False) if _real else _s())
    )
    r_help: Style = (
        _s(c="grey74", b=False, i=True)
        if _rich
        else (_s(u=False, d=True) if _real else _s())
    )
    r_dict: Style = (
        _s(c="magenta", b=False, i=False, d=False, u=False) if _real else _s()
    )
    r_list: Style = (
        _s(c="cyan", b=False, i=False, d=False, u=False) if _real else _s()
    )
    r_root: Style = (
        _s(c="green", b=False, i=False, d=False, u=False) if _real else _s()
    )
    r_leaf: Style = _s(c="default", b=False, i=False, d=False, u=False)

    # # # # # # # # # # # # # # # # Usage Pane # # # # # # # # # # # # # # # #

    u_bold: Style = _s(b=True) if _rich else _s()
    u_title: Style = _s(c="default") + u_bold
    u_pane: Style = _s(c="cyan") + u_bold
    u_exec: Style = _s(c="green", i=False, d=False, u=False) + u_bold
    u_path: Style = _s(c="magenta", i=False, d=False, u=False) + u_bold
    u_flag: Style = _s(c="yellow", b=False, i=False, d=False, u=False)
    u_para: Style = _s(c="default", b=False, i=False, d=False, u=False)
    u_plain: Style = r_leaf

    # # # # # # # # # # # # # # # Tables Design # # # # # # # # # # # # # # # #

    t_clr: List[str] = MISSING
    t_cnt: int = MISSING
    t_head: Style = _s(b=True) if _rich else (_s(r=True) if _real else _s())
    t_body: Style = _s(b=False) if _rich else (_s(r=False) if _real else _s())

    # # # # # # # # # # # # # # # # Box Styles # # # # # # # # # # # # # # # #

    b_show: box.Box = box.ROUNDED
    b_hide: box.Box = box.Box("\n".join(" " * 4 for _ in range(8)))

    def __post_init__(self):
        if self.t_clr is MISSING:
            self.t_clr = ["magenta", "yellow", "red", "cyan", "green", "blue"]

        if self.t_cnt is MISSING:
            self.t_cnt = len(self.t_clr)

        self.t_clr = self.t_clr * (self.t_cnt // len(self.t_clr) + 1)

    @property
    def t_colors(self) -> Generator[Style, None, None]:
        for c in self.t_clr:
            yield _s(c=c)


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


class RichArgumentParser(ArgumentParser):
    theme: SpringsTheme
    entrypoint: Optional[str]
    arguments: Optional[str]
    formatted: Dict[str, Any]
    console_kwargs: Dict[str, Any]

    def __init__(
        self,
        *args,
        entrypoint: Optional[str] = None,
        arguments: Optional[str] = None,
        console_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.theme = SpringsTheme()
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
                Text(text="python", style=self.theme.u_exec)
                + Text(text=" ", style=self.theme.u_plain)
                + Text(text=f"{self.entrypoint}", style=self.theme.u_path)
                + Text(text=" ", style=self.theme.u_plain)
                + Text(text=" ".join(flags), style=self.theme.u_flag)
                + Text(text=" ", style=self.theme.u_plain)
                + Text(text=f"{self.arguments}", style=self.theme.u_para)
            )
        else:
            usage = self.usage

        if usage is not None:
            return Panel(
                usage,
                title=(
                    Text(text=" ", style=self.theme.u_plain)
                    + Text(text="Usage", style=self.theme.u_pane)
                    + Text(text=" ", style=self.theme.u_plain)
                ),
                title_align="center",
            )

    def format_help(self):
        groups = []

        if self.description:
            description = Panel(
                Text(self.description, justify="center"),
                style=self.theme.u_title,
                box=box.SIMPLE,
            )
            groups.append(description)

        if (usage := self.format_usage()) is not None:
            groups.append(usage)

        for ag in self._action_groups:
            if len(ag._group_actions) == 0:
                continue

            flags = []
            defaults = []
            actions = []
            descriptions = []

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

                flags.append("/".join(action.option_strings))
                defaults.append(default)
                actions.append(nargs)
                descriptions.append(action.help or "")

            table = TableParser.make_table(
                columns=["Flag", "Default", "Action", "Description"],
                values=list(zip(flags, defaults, actions, descriptions)),
                theme=self.theme,
                v_justify=["left", "center", "center", "left"],
            )
            title = (
                Text(ag.title.capitalize(), style=self.theme.u_pane)
                if ag.title
                else None
            )
            panel = Panel(
                table, title=title, title_align="center", box=self.theme.b_show
            )
            groups.append(panel)

        return Panel(
            Group(*groups),
            box=self.theme.b_hide,
        )

    def _print_message(
        self, message: Any, file: Optional[IO[str]] = None
    ) -> None:
        Console(**{**self.console_kwargs, "file": file}).print(message)


class ConfigTreeParser:
    def __init__(
        self,
        theme: Optional[SpringsTheme] = None,
        console_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.theme = theme or SpringsTheme()
        self.console_kwargs = console_kwargs or {}

    @classmethod
    def _get_parent_path(cls, path: str) -> str:
        return path.rsplit(".", 1)[0] if "." in path else ""

    @classmethod
    def make_config_tree(
        cls,
        title: str,
        config: Union[DictConfig, ListConfig],
        subtitle: Optional[str] = None,
        print_help: bool = False,
        theme: Optional[SpringsTheme] = None,
    ) -> Tree:
        theme = theme or SpringsTheme()

        root_label = Text(text=title, style=theme.r_root + theme.r_title)
        if subtitle:
            root_label += Text(
                text=f"\n{subtitle}", style=theme.r_help + theme.r_root
            )

        root = Tree(label=root_label)
        trees: Dict[str, Tree] = {"": root}
        nodes_order: Dict[str, Dict[str, int]] = {}

        # STEP 1: We start by adding all nodes to the tree; a node is a
        #         DictConfig or ListConfig that has children.
        all_nodes = sorted(
            traverse(config, include_nodes=True, include_leaves=False),
            key=lambda spec: spec.path.count("."),
        )
        for spec in all_nodes:
            parent_path = cls._get_parent_path(spec.path)
            tree = trees.get(parent_path, None)
            if spec.key is None or tree is None:
                raise ValueError("Cannot print disjoined tree")

            # # color is different for DictConfig and ListConfig
            style = (
                theme.r_dict
                if isinstance(spec.value, DictConfig)
                else theme.r_list
            )
            text = spec.key if isinstance(spec.key, str) else f"[{spec.key}]"
            label = Text(text=text, style=style + theme.r_title)

            # Add help if available; make it same color as the key, but italic
            # instead of bold. Note that we print the help iff print_help is
            # True. We also remove any newlines and extra spaces from the help
            # using a regex expression.
            if spec.help and print_help:
                label += Text(
                    text="\n" + re.sub(r"\s+", " ", spec.help.strip()),
                    style=theme.r_help + style,
                )

            # Actually adding the node here!
            subtree = tree.add(label=label)

            # We need to keep track of each node in the tree separately; this
            # is so that we can attach the leaves to the correct node later.
            trees[spec.path] = subtree

            # This helps us remember the order nodes appear in the config
            # created by the user. We use this to sort the nodes in the tree
            # before printing.
            nodes_order.setdefault(parent_path, {})[str(label)] = spec.position

        # STEP 2: We now add all leaves to the tree; a leaf is anything that
        #         is not a DictConfig or ListConfig.
        all_leaves = sorted(
            traverse(config, include_nodes=False, include_leaves=True),
            key=lambda spec: str(spec.key),
        )
        for spec in all_leaves:
            parent_path = cls._get_parent_path(spec.path)
            tree = trees.get(parent_path, None)
            if tree is None:
                raise ValueError("Cannot find node for this leaf")

            # Using '???' to indicate unknown type
            type_name = spec.type.__name__ if spec.type else "???"
            label = (
                Text(text=str(spec.key), style=theme.r_leaf + theme.r_title)
                + Text(text=": ", style=theme.r_leaf)
                + Text(text=f"({type_name})", style=theme.r_leaf)
                + Text(text=" = ", style=theme.r_leaf)
                + Text(text=str(spec.value), style=theme.r_leaf)
            )

            # Add help if available; print it a gray color and italic.
            if spec.help and print_help:
                label += Text(
                    text="\n" + re.sub(r"\s+", " ", spec.help.strip()),
                    style=theme.r_leaf + theme.r_help,
                )

            # Actually adding the leaf here!
            tree.add(label=label)

            # This helps us remember the order leaves appear in the config
            # created by the user. We use this to sort the nodes in the tree
            # before printing.
            nodes_order.setdefault(parent_path, {})[str(label)] = spec.position

        # STEP 3: sort nodes in each tree to match the order the appear
        #         in the config created by the user.
        for leaf, tree in trees.items():  # noqa: E741
            tree.children.sort(
                key=lambda child: nodes_order[leaf][str(child.label)]
            )

        # STEP 4: if there are no nodes or leaves in this configuration, add a
        #         message to the tree that indicates that the config is empty.
        if len(all_leaves) == len(all_nodes) == 0:
            root_label += Text(text="\n  [empty]", style=theme.r_help)
            root = Tree(label=root_label)

        return root

    def __call__(
        self,
        config: Union[DictConfig, ListConfig],
        title: Optional[str] = None,
        subtitle: Optional[str] = None,
        print_help: bool = False,
    ):
        tree = self.make_config_tree(
            title=title or "🌳",
            config=config,
            subtitle=subtitle,
            print_help=print_help,
            theme=self.theme,
        )

        # time to print!
        panel = Panel(tree, padding=0, box=self.theme.b_hide)
        Console(**self.console_kwargs).print(panel)


class TableParser:
    def __init__(
        self,
        theme: Optional[SpringsTheme] = None,
        console_kwargs: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.theme = theme or SpringsTheme()
        self.console_kwargs = console_kwargs or {}

    @classmethod
    def make_table(
        cls,
        columns: Sequence[Any],
        values: Sequence[Sequence[Any]],
        title: Optional[str] = None,
        v_justify: Optional[Sequence[str]] = None,
        h_justify: Optional[Sequence[str]] = None,
        theme: Optional[SpringsTheme] = None,
        caption: Optional[str] = None,
        borders: bool = False,
    ) -> Table:
        theme = theme or SpringsTheme()
        v_justify = v_justify or ["center"] * len(columns)
        h_justify = h_justify or ["middle"] * len(columns)

        def _get_longest_row(text: str) -> int:
            return max(len(row) for row in (text.splitlines() or [""]))

        min_width_outside_content = min(
            max(_get_longest_row(title or ""), _get_longest_row(caption or ""))
            + 2,
            os.get_terminal_size().columns - 2,
        )

        columns = (
            Column(
                header=f" {cl} ",
                justify=vj,  # type: ignore
                style=co + theme.t_body,
                header_style=co + theme.t_head,
                vertical=hj,  # type: ignore
            )
            for cl, vj, hj, co in zip(
                columns, v_justify, h_justify, theme.t_colors
            )
        )

        table = Table(
            *columns,
            padding=(0, 0),
            title=f"\n{title}" if title else None,
            min_width=min_width_outside_content,
            caption=caption,
            title_style=theme.r_title,
            caption_style=theme.r_help,
            box=(theme.b_show if borders else theme.b_hide),
            expand=True,
            collapse_padding=True,
        )
        for row in values:
            table.add_row(*row)

        return table

    def __call__(
        self,
        columns: Sequence[Any],
        values: Sequence[Sequence[Any]],
        title: Optional[str] = None,
        v_justify: Optional[Sequence[str]] = None,
        h_justify: Optional[Sequence[str]] = None,
        caption: Optional[str] = None,
        borders: bool = False,
    ) -> None:
        table = self.make_table(
            columns=columns,
            values=values,
            title=title,
            v_justify=v_justify,
            h_justify=h_justify,
            theme=self.theme,
            caption=caption,
            borders=borders,
        )
        # time to print!
        panel = Panel(table, padding=0, box=self.theme.b_hide)
        Console(**self.console_kwargs).print(panel)

from dataclasses import dataclass
from functools import cached_property
from typing import Any, Iterator, Optional, Type, Union
from typing import cast as typecast

from omegaconf import MISSING, DictConfig, ListConfig, OmegaConf
from omegaconf.basecontainer import BaseContainer


@dataclass
class ParamSpec:
    key: Union[str, int, None]
    path: str
    value: Any
    parent: Optional[Union[DictConfig, ListConfig]]
    interpol: bool

    def is_node(self) -> bool:
        return isinstance(self.value, (DictConfig, ListConfig))

    @property
    def type(self) -> Type:
        if self.key is None:
            raise ValueError("Cannot get type of root node")
        else:
            # int actually work fine, but OmegaConf.get_type() is
            # not correctly typed.
            return OmegaConf.get_type(self.parent, self.key)  # type: ignore

    @cached_property
    def position(self) -> int:
        if self.key is None:
            return -1
        elif isinstance(self.key, int):
            return self.key
        elif isinstance(self.parent, DictConfig):
            return tuple(self.parent.keys()).index(self.key)
        else:
            raise ValueError("Cannot get position of this key in parent")


@dataclass
class FailedParamSpec(ParamSpec):
    error: Exception


def traverse(
    node: BaseContainer,
    include_nodes: bool = False,
    include_leaves: bool = True,
    include_root: bool = False,
    recurse: bool = True,
) -> Iterator[ParamSpec]:

    if include_root:
        yield ParamSpec(
            key=None, path="", value=node, parent=None, interpol=False
        )

    if isinstance(node, ListConfig):
        for key in range(len(node)):
            if is_interpolation := OmegaConf.is_interpolation(node, key):
                # we don't want to resolve interpolations for now
                # as they might not be resolvable at the moment
                value = typecast(list, OmegaConf.to_container(node))[
                    typecast(int, key)
                ]
            else:
                value = node[typecast(int, key)]

            if isinstance(value, BaseContainer):
                # we recurse into the node if it is a container
                if recurse:
                    for spec in traverse(
                        value,
                        include_leaves=include_leaves,
                        include_nodes=include_nodes,
                    ):
                        yield ParamSpec(
                            key=spec.key,
                            path=f"[{key}].{spec.path}",
                            value=spec.value,
                            parent=spec.parent,
                            interpol=is_interpolation,
                        )

            current_node_spec = ParamSpec(
                key=key,
                # [num] is the notation for list indices
                path=f"[{key}]",
                value=value,
                parent=node,
                interpol=is_interpolation,
            )

            # we yield the node if it is not a container, or if
            # we are specifically asked to include nodes
            if current_node_spec.is_node():
                if include_nodes:
                    yield current_node_spec
            elif include_leaves:
                yield current_node_spec

    elif isinstance(node, DictConfig):
        for key in node.keys():
            if OmegaConf.is_missing(node, key):
                value = MISSING
                is_interpolation = False
            elif is_interpolation := OmegaConf.is_interpolation(
                node, str(key)
            ):
                # We don't want to resolve interpolations for now,
                # as they might not be resolvable at the moment
                value = OmegaConf.to_container(node)[key]  # type: ignore
            else:
                value = OmegaConf.select(node, str(key))

            if isinstance(value, BaseContainer):
                if recurse:
                    for spec in traverse(
                        value,
                        include_nodes=include_nodes,
                        include_leaves=include_leaves,
                    ):
                        yield ParamSpec(
                            key=spec.key,
                            # we use str(key) here to make sure
                            # it's just a string, not an obj repr
                            path=f"{str(key)}.{spec.path}",
                            value=spec.value,
                            parent=spec.parent,
                            interpol=is_interpolation,
                        )

            current_node_spec = ParamSpec(
                key=str(key),
                path=str(key),
                value=value,
                parent=node,
                interpol=is_interpolation,
            )

            # we yield the node if it is not a container, or if
            # we are specifically asked to include nodes
            if current_node_spec.is_node():
                if include_nodes:
                    yield current_node_spec
            elif include_leaves:
                yield current_node_spec

    else:
        raise ValueError(
            f"Cannot traverse `{node}`; DictConfig or ListConfig "
            f"expected, but got `{type(node)}`."
        )

from dataclasses import dataclass
from typing import Any, Iterator, Optional, Union

from omegaconf import MISSING, DictConfig, ListConfig, OmegaConf
from omegaconf.basecontainer import BaseContainer


@dataclass
class ParamSpec:
    key: Union[str, int, None]
    path: str
    value: Any
    parent: Optional[Union[DictConfig, ListConfig]]

    def is_node(self) -> bool:
        return isinstance(self.value, (DictConfig, ListConfig))


def traverse(
    node: BaseContainer,
    include_nodes: bool = False,
    include_root: bool = False
) -> Iterator[ParamSpec]:

    if include_root:
        yield ParamSpec(key=None, path='', value=node, parent=None)

    if isinstance(node, ListConfig):
        for i, element in enumerate(node):
            if isinstance(element, BaseContainer):
                for spec in traverse(element, include_nodes=include_nodes):
                    yield ParamSpec(key=spec.key,
                                    path=f'[{i}].{spec.path}',
                                    value=spec.value,
                                    parent=spec.parent)

            if include_nodes or not isinstance(element, BaseContainer):
                yield ParamSpec(key=i,
                                path=f'[{i}]',
                                value=element,
                                parent=node)

    elif isinstance(node, DictConfig):
        for key in node.keys():
            if OmegaConf.is_missing(node, key):
                value = MISSING
            elif OmegaConf.is_interpolation(node, str(key)):
                # We don't want to resolve interpolations for now,
                # as they might not be resolvable at the moment
                value = OmegaConf.to_container(node)[key]  # type: ignore
            else:
                value = OmegaConf.select(node, str(key))

            if isinstance(value, BaseContainer):
                for spec in traverse(value, include_nodes=include_nodes):
                    yield ParamSpec(key=spec.key,
                                    path=f'{key}.{spec.path}',
                                    value=spec.value,
                                    parent=spec.parent)

            if include_nodes or not isinstance(value, BaseContainer):
                yield ParamSpec(key=str(key),
                                path=str(key),
                                value=value,
                                parent=node)

    else:
        raise ValueError(f'Cannot traverse `{node}`; DictConfig or ListConfig '
                         f'expected, but got `{type(node)}`.')

from dataclasses import field as _field
from dataclasses import fields, is_dataclass
from typing import Optional

from omegaconf.basecontainer import BaseContainer

from .types_utils import get_type

__all__ = ["field", "HelpLookup"]


def field(
    *, help: Optional[str] = None, omegaconf_ignore: bool = False, **kwargs
):
    metadata = {
        **kwargs.pop("metadata", {}),
        "help": help,
        "omegaconf_ignore": omegaconf_ignore,
    }
    return _field(metadata=metadata, **kwargs)


class HelpLookup:
    def __init__(self, node: BaseContainer):
        # the class of the node; it is useful to have, especially so that
        # we can check if the object comes with a help field
        self.node_cls = get_type(node)  # type: ignore

        if is_dataclass(self.node_cls):
            self._help = {
                f.name: f.metadata.get("help", None)
                for f in fields(self.node_cls)
            }
        else:
            self._help = {}

    def __getitem__(self, key: str) -> Optional[str]:
        if key not in self._help:
            return None
        return self._help[key]

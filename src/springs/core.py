import json
from collections import abc
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from functools import reduce
from inspect import isclass
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple, TypeVar, Union
from typing import cast as typing_cast
from typing import overload

from omegaconf import DictConfig, ListConfig, OmegaConf
from omegaconf.errors import MissingMandatoryValue
from omegaconf.omegaconf import DictKeyType
from yaml.scanner import ScannerError

from .flexyclasses import FlexyClass
from .traversal import FailedParamSpec, traverse

DEFAULT: Any = "***"


C = TypeVar("C", bound=Union[DictConfig, ListConfig])


def cast(config: Any, copy: bool = False) -> DictConfig:
    if is_dataclass(config):
        parsed_config = from_dataclass(config)
    elif isinstance(config, dict):
        parsed_config = from_dict(config)
    elif isinstance(config, str):
        parsed_config = from_string(config)
    elif config is None:
        parsed_config = from_none(config)
    elif isinstance(config, DictConfig):
        parsed_config = deepcopy(config) if copy else config
    elif isinstance(config, Path):
        parsed_config = from_file(config)
    else:
        raise TypeError(f"Cannot cast `{type(config)}` to DictConfig")

    return parsed_config


def from_none(*args: Any, **kwargs: Any) -> DictConfig:
    """Returns an empty dict config"""
    return OmegaConf.create()


def from_dataclass(config: Any) -> DictConfig:
    """Cast a dataclass to a structured omega config"""
    if config is None:
        return from_none()

    if isclass(config) and issubclass(config, FlexyClass):
        config = config.defaults()

    elif not is_dataclass(config):
        raise TypeError(f"`{config}` is not a dataclass!")

    parsed_config = OmegaConf.structured(config)

    if not isinstance(parsed_config, DictConfig):
        raise TypeError(f"Cannot create dict config from `{config}`")
    return parsed_config


@overload
def from_python(
    config: Union[Dict[DictKeyType, Any], Dict[str, Any]]
) -> DictConfig:
    ...


@overload
def from_python(config: List[Any]) -> ListConfig:
    ...


def from_python(
    config: Union[Dict[DictKeyType, Any], Dict[str, Any], List[Any]]
) -> Union[DictConfig, ListConfig]:
    """Create a config from a dict"""
    if not isinstance(config, (dict, list)):
        raise TypeError(f"`{config}` is not a dict or list!")

    parsed_config = OmegaConf.create(config)

    if not isinstance(parsed_config, (DictConfig, ListConfig)):
        raise ValueError(
            f"Config `{config}` is not a DictConfig or ListConfig!"
        )

    return parsed_config


def from_dict(
    config: Union[Dict[DictKeyType, Any], Dict[str, Any]]
) -> DictConfig:
    """Create a config from a dict"""
    if not isinstance(config, dict):
        raise TypeError(f"`{config}` is not a dict!")

    return from_python(config)  # type: ignore


def from_string(config: str) -> DictConfig:
    """Load a config from a string"""
    if not isinstance(config, str):
        raise TypeError(f"`{config}` is not a string!")

    parsed_config = OmegaConf.create(config)

    if not isinstance(parsed_config, DictConfig):
        raise ValueError(f"Config `{config}` is not a DictConfig!")
    return parsed_config


def from_file(path: Union[str, Path]) -> DictConfig:
    """Load a config from a file, either YAML or JSON"""
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Cannot file configuration at {path}")

    try:
        # if it fails, it's not a yaml file
        config = OmegaConf.load(path)
    except ScannerError:
        try:
            with open(path, "r", encoding="utf-8") as f:
                config = from_python(json.load(f))
        except json.JSONDecodeError:
            raise ValueError(
                f"Cannot parse configuration at {path}; "
                "not a valid YAML or JSON file"
            )

    if not isinstance(config, DictConfig):
        raise ValueError(f"Config loaded from {path} is not a DictConfig!")

    return config


def from_options(opts: Sequence[str]) -> DictConfig:
    """Create a config from a list of options"""
    if not isinstance(opts, abc.Sequence) or not all(
        isinstance(o, str) for o in opts
    ):
        raise TypeError(f"`{opts}` is not a list of strings!")

    config = OmegaConf.from_dotlist(list(opts))
    if not isinstance(config, DictConfig):
        raise TypeError(f"input is not a sequence of strings, but `{opts}")
    return config


def to_yaml(config: Any) -> str:
    """Convert a omegaconf config to a YAML string"""
    if not isinstance(config, DictConfig):
        config = from_dataclass(config)
    return OmegaConf.to_yaml(config)


def to_json(config: Any) -> str:
    """Convert a omegaconf config to a JSON string"""
    if not isinstance(config, DictConfig):
        config = from_dataclass(config)
    return json.dumps(to_python(config))


def to_python(config: Any) -> Any:
    """Convert a omegaconf config to a Python primitive type"""
    if is_dataclass(config):
        config = from_dataclass(config)
    container = OmegaConf.to_container(config)
    return container


def to_dict(config: Any) -> Dict[DictKeyType, Any]:
    """Convert a omegaconf config to a Python primitive type"""
    container = to_python(config)

    if not isinstance(container, dict):
        raise TypeError(f"`{container}` is not a dict!")

    return container


########################################


def resolve(config: C) -> C:
    """Resolve a config"""
    config = deepcopy(config)
    OmegaConf.resolve(config)
    return config


def safe_validate(config_node: C) -> Tuple[C, List[FailedParamSpec]]:
    """Check if all attributes are resolve and not missing

    If resolution fails, second element of return tuple contains
    missing keys."""

    errors = []

    if not isinstance(config_node, (DictConfig, ListConfig)):
        raise TypeError(f"`{config_node}` is not a DictConfig!")

    for spec in traverse(config_node):
        if spec.key is None:
            raise RuntimeError(
                "You should not be here! Something went "
                "wrong in the core Springs library."
            )

        if OmegaConf.is_missing(spec.parent, spec.key):
            # raise ValueError(f"Missing value for `{spec.path}`")
            errors.append(
                FailedParamSpec(error=MissingMandatoryValue(), **asdict(spec))
            )

        if OmegaConf.is_interpolation(spec.parent, spec.key):
            try:
                getattr(spec.parent, str(spec.key))
            except Exception as e:
                errors.append(FailedParamSpec(error=e, **asdict(spec)))

    return config_node, errors


def validate(
    config_node: C,
    raise_on_missing: bool = True,
    raise_on_failed_interpolation: bool = True,
) -> C:
    config_node, errors = safe_validate(config_node)

    for spec in errors:
        if spec.interpol and not raise_on_failed_interpolation:
            continue
        if (
            isinstance(spec.error, MissingMandatoryValue)
            and not raise_on_missing
        ):
            continue

        # this will not run if missing is an empty list
        raise ValueError(
            f"Interpolation for '{spec.path}' not resolved; "
            f"{type(spec.error).__name__}: "
            f"{' '.join(str(a) for a in spec.error.args)}"
        ) from spec.error
    return config_node


def unsafe_merge(
    first_config: C,
    *other_configs: Union[DictConfig, ListConfig],
) -> C:
    """Merge two or more configurations together without any validation.

    Args:
        first_config (Union[DictConfig, ListConfig]): The first configuration
            to merge.
        *other_configs (Union[DictConfig, ListConfig]): The other
            configurations to merge with the first one; they are merged in
            the order they are provided.

    Returns:
        Union[DictConfig, ListConfig]: The merged configuration.
    """
    for c in (first_config, *other_configs):
        if not isinstance(c, (DictConfig, ListConfig)):
            raise TypeError(f"`{c}` is not a DictConfig or ListConfig!")

    output_config = reduce(
        lambda a, b: OmegaConf.merge(a, OmegaConf.create(b)),
        (
            OmegaConf.to_container(c, resolve=False)
            for c in (first_config, *other_configs)
        ),
        # we need to start with an empty dict or list rather than
        # the first config to prevent type checking from kicking in
        # during merge.
        OmegaConf.create({} if isinstance(first_config, DictConfig) else []),
    )

    return typing_cast(C, output_config)


def merge(
    first_config: C,
    *other_configs: Union[DictConfig, ListConfig],
    resolve_nodes: bool = True,
    validate_config: bool = True,
) -> C:
    """Merge two or more configurations together. If `skip_resolve`
    and `skip_validate` are both `True`, this function is equivalent to
    `unsafe_merge`.

    Args:
        first_config (Union[DictConfig, ListConfig]): The first configuration
            to merge.
        *other_configs (Union[DictConfig, ListConfig]): The other
            configurations to merge with the first one; they are merged in
            the order they are provided.
        resolve_nodes (bool, optional): If `False`, keys that are references
            to other keys will not be resolved. Defaults to `True`.
        validate_config (bool, optional): If `False`, the merged configuration
            will not be validated. Defaults to `True`.

    Returns:
        Union[DictConfig, ListConfig]: The merged configuration.
    """

    unsafe_config = unsafe_merge(first_config, *other_configs)

    if resolve_nodes:
        unsafe_config = resolve(unsafe_config)

    output_config = OmegaConf.merge(first_config, unsafe_config)

    if validate_config:
        output_config = validate(
            output_config,
            raise_on_failed_interpolation=resolve_nodes,
        )

    return typing_cast(C, output_config)


L = TypeVar("L", bound=ListConfig)


def edit_list(config: L, editor: DictConfig) -> L:
    """Edit a copy of a ListConfig using a DictConfig.

    Args:
        config (ListConfig): The ListConfig to edit.
        editor (DictConfig): The DictConfig containing the edits to make.
            The keys of the DictConfig should be the indices of the list.

    Returns:
        ListConfig: The edited ListConfig.
    """
    if not isinstance(config, ListConfig):
        raise TypeError(f"`{config}` is not a ListConfig!")

    if not isinstance(editor, DictConfig):
        raise TypeError(f"`{editor}` is not a DictConfig!")

    config = deepcopy(config)

    for key, value in editor.items():
        try:
            key = int(key)  # pyright: reportGeneralTypeIssues=false
        except TypeError:
            raise TypeError(f"`{key}` is not an int!")

        if key >= len(config):
            raise IndexError(f"Index {key} is out of range!")

        if isinstance(config[key], (DictConfig, ListConfig)):
            config[key] = merge(config[key], value)
        else:
            config[key] = value

    return config

import os
from datetime import datetime, timezone
from typing import Any, Type, Union, Dict

from .functional import config_to_dict
from .node import (
    ConfigNode,
    ConfigNodeProps,
    ConfigRegistryReference,
    ConfigPlaceholderVar
)
from .registry import ConfigRegistry
from .utils import merge_nested_dicts, FUTURE
from .instantiate import TargetType


@ConfigRegistry.add
def __is_type__(*args, **_) -> str:
    """Check if the provided value matches the target type.
    Usage example:

    ```yaml
    foo: 3
    bar: ${foo@__is_type__@int}     # this will eval True
    baz@__is_type__@str: ${foo}     # this will eval False
    ```
    """
    if len(args) < 2:
        msg = ('__is_type__ expects two imputs, '
               'e.g. ${path.to_node@__is_type__@target_type}'
               'or key@__is_type__@target_type: ... .')
        raise ValueError(msg)

    node_source, target_type, *_ = args
    target_type = TargetType.get_callable(target_type)

    if node_source == '${epochs}':
        raise ValueError()

    return isinstance(node_source, target_type)


@ConfigRegistry.add
def __fullpath__(*args, **kwargs) -> str:
    """Resolve all implicit and relative path components
    to give an absolute path to a file or directory"""

    if len(args) > 0:
        path = args[0]
    elif 'config' in kwargs:
        path = kwargs['config']
    elif 'path' in kwargs:
        path = kwargs['path']
    else:
        msg = f'Could not find suitable `path` in {args} or {kwargs}'
        raise RuntimeError(msg)

    if '~' in path:
        path = os.path.expanduser(path)
    path = os.path.realpath(os.path.abspath(path))
    return path


@ConfigRegistry.add
def __environ__(*args, **kwargs) -> str:
    """Look up an environmental variable; returns an empty
    string if the variable is not set."""

    if len(args) > 0:
        environ = args[0]
    elif 'config' in kwargs:
        environ = kwargs['config']
    elif 'environ' in kwargs:
        environ = kwargs['environ']
    else:
        msg = f'Could not find suitable `environ` in {args} or {kwargs}'
        raise RuntimeError(msg)

    return os.environ.get(environ, '')


@ConfigRegistry.add
def __timestamp__(*_, **__) -> str:
    """Returns a timestamp in the format
    year-month-day_hour-minute-second."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")


class _MockResuseRegistryReference(ConfigRegistryReference):
    def __init__(self: '_MockResuseRegistryReference',
                 node_cls: Type[ConfigNode],
                 config: Union[Dict[str, Any], ConfigNode, None] = None,
                 __parent__: ConfigNode = None,
                 __flex_node__: bool = False,
                 __name__: str = None,
                 kwargs: Dict[str, Any] = None):
        self.node_cls = node_cls
        self.node_init_config = config or {}
        self.node_init_parent = __parent__
        self.node_init_flex_node = __flex_node__
        self.node_init_name = __name__
        self.node_init_kwargs = kwargs or {}

    def resolve(self: '_MockResuseRegistryReference',
                config_node: ConfigNode) -> ConfigNode:

        config = merge_nested_dicts(config_to_dict(config_node),
                                    self.node_init_config)

        # important check: this parameter might be have been
        # overridded in the via cli options, so we don't want
        # to restore it by accident. For example, if your yaml config is:
        #   foo@__reuse__@${bar}:
        #       y : 1
        #   bar:
        #       x: 2
        # but a user provides foo.x=3 via command line, that should
        # take preference. in that case; current_value would not be
        # FUTURE, but already have a value (That's because of how we
        # merge configs via CLI). So we return that value instead.

        current_value = self.node_init_parent[self.node_init_name]
        if current_value != FUTURE:
            return current_value

        return self.node_cls(config=config,
                             __parent__=self.node_init_parent,
                             __flex_node__=self.node_init_flex_node,
                             __name__=self.node_init_name,
                             **self.node_init_kwargs)


@ConfigRegistry.add
def __reuse__(
    config: Union[Dict[str, Any], ConfigNode, None] = None,
    var_ref: str = None,
    __parent__: ConfigNode = None,
    __flex_node__: bool = False,
    __name__: str = None,
    node_cls: Type[ConfigNode] = None,
    **kwargs: Dict[str, Any]
) -> str:
    usage = f'usage: key@{__name__}@${{var_reference}}.'

    if var_ref is None:
        if config is None:
            raise RuntimeError(f'Missing var reference! {usage}')
        if isinstance(config, str):
            # need to switch positional args
            config, var_ref = None, config

    if not ConfigPlaceholderVar.contains(var_ref):
        raise ValueError(f'{var_ref} is not a var reference! {usage}')

    if node_cls is None:
        msg = ('Missing node class! You are probably using  '
               f'this reference incorrectly. {usage}')
        raise RuntimeError(msg)

    reg_reference = _MockResuseRegistryReference(
        node_cls=node_cls,
        config=config,
        __parent__=__parent__,
        __flex_node__=__flex_node__,
        __name__=__name__,
        kwargs=kwargs,
    )

    node_variable = ConfigPlaceholderVar(
        parent_node=__parent__,
        param_name=__name__,
        param_value=var_ref,
        outer_reg_ref=reg_reference,
        param_config=None
    )
    parent_props = ConfigNodeProps.get_props(__parent__)
    parent_props.add_var(node_variable)

    return FUTURE

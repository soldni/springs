import os
from datetime import datetime, timezone

from .registry import ConfigRegistry
from .instantiate import get_callable


@ConfigRegistry.add
def __is_type__(*args, **kwargs) -> str:
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
    target_type = get_callable(target_type)

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
def __timestamp__(*args, **kwargs) -> str:
    """Returns a timestamp in the format
    year-month-day_hour-minute-second."""
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")

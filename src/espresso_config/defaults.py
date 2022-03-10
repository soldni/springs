import os
from datetime import datetime, timezone

from .registry import ConfigRegistry


@ConfigRegistry.add
def __fullpath__(*args, **kwargs) -> str:
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
    if len(args) > 0:
        environ = args[0]
    elif 'config' in kwargs:
        environ = kwargs['config']
    elif 'environ' in kwargs:
        environ = kwargs['environ']
    else:
        msg = f'Could not find suitable `environ` in {args} or {kwargs}'
        raise RuntimeError(msg)

    return os.environ.get(environ, None)


@ConfigRegistry.add
def __timestamp__(*args, **kwargs) -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

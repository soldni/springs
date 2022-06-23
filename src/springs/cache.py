import hashlib
import pickle
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, Union

from .initialize import Target


def cache_to_disk(kwargs: Optional[Sequence[str]] = None,
                  location: Optional[Union[str, Path]] = None) -> Callable:
    """Decorator to cache a function's output to disk.

    Args:
        kwargs: The name of the values in the function's signature to
            use to determine the filename of the cache file.
            If None, all values are used.
        location: The directory where the cache file will be stored.
            If None, ~/.cache is used.

    Returns:
        A decorator that enables caches the output of a function
            decorated with it.
    """

    if location is None:
        location = (Path('~') / '.cache').expanduser().absolute()
    path_location = Path(location)

    # make caching directory if it doesn't exist
    if not path_location.exists():
        path_location.mkdir(parents=True)

    def decorator(func: Callable,
                  kwargs_to_cache: Optional[Sequence[str]] = kwargs,
                  location: Path = path_location) -> Callable:
        func_name = Target.to_string(func)

        @wraps(func)
        def wrapper(
            *args: Any,
            __kwargs_to_cache__: Optional[Sequence[str]] = kwargs_to_cache,
            __location__: Path = location,
            __invalidate__: bool = False,
            __func_name__: str = func_name,
            **kwargs: Any
        ) -> Any:
            if args:
                msg = 'You cannot pass non-positional arguments when caching'
                raise ValueError(msg)

            # always cache in the same order
            if __kwargs_to_cache__ is None:
                __kwargs_to_cache__ = tuple(kwargs.keys())
            __kwargs_to_cache__ = sorted(__kwargs_to_cache__)

            # collect hash here
            h = hashlib.sha1()

            # hash function name
            h.update(__func_name__.encode('utf-8'))

            # hash all kwargs
            for k, v in kwargs.items():
                if k in __kwargs_to_cache__:
                    # include name of key in cache name
                    h.update(pickle.dumps((k, v)))

            # digest and give .pickle extension
            cache_path = __location__ / f'{h.hexdigest()}.pickle'

            if not cache_path.exists() or __invalidate__:
                # cache miss
                resp = func(**kwargs)
                with open(cache_path, 'wb') as f:
                    pickle.dump(resp, f)
            else:
                # cache hit
                with open(cache_path, 'rb') as f:
                    resp = pickle.load(f)

            # return whatever the function returns
            return resp

        return wrapper

    return decorator

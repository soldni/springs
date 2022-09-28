import hashlib
import inspect
import pickle
from functools import reduce, wraps
from pathlib import Path
from typing import Callable, Optional, Tuple, TypeVar, Union

from platformdirs import user_cache_dir
from typing_extensions import ParamSpec

from .initialize import Target
from .logging import configure_logging

LOGGER = configure_logging(__file__)

P = ParamSpec("P")
R = TypeVar("R")


def memoize(
    cachedir: Optional[Union[Path, str]] = None,
    appname: Optional[Union[str, Tuple[str, ...]]] = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Memoize a function call to disk.

    Args:
        cachedir (Optional[Union[Path, str]], optional): Directory to store
            cached results. If not provided, we use the platform-specific
            user cache directory we get from platformdirs.
        appname (Optional[Union[str, Tuple[str, ...]]], optional): Name of the
            application to use for the cache directory. If not provided and
            cachedir is not provided, an error is raised. It can either be a
            string or a tuple of strings. If a tuple, a subdirectory is created
            for each string in the tuple.

    Returns:
        Callable[[Callable[P, R]], Callable[P, R]]: A decorator that can be
            applied to a function to memoize it.
    """

    if cachedir is None:
        if appname is None:
            raise ValueError("app_name must be specified if cache_dir is not")

        if isinstance(appname, str):
            appname = (appname,)

        cachedir = reduce(lambda x, y: x / y, appname, Path(user_cache_dir()))

    full_cache_dir = Path(cachedir)
    full_cache_dir.mkdir(parents=True, exist_ok=True)

    def _memoize(func: Callable[P, R]) -> Callable[P, R]:

        # get the fully specified function name
        function_name = Target.to_string(func)

        # get a signature for the function; we will bound it to arguments
        # later to derive a hash.
        function_signature = inspect.signature(func)

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:

            # we accumulate all arguments in a hash here; we also use the
            # fully specified function name to derive a filename at which
            # to cache.
            input_hash = hashlib.sha1()
            input_hash.update(function_name.encode("utf-8"))

            # bound the signature to the arguments; we also build a nice
            # string representation of the arguments for logging purposes.
            bounded_arguments = function_signature.bind(*args, **kwargs)
            arguments_representation = ""

            # we iterate over the arguments and add them to the hash unless
            # the are either a class instance or a function.
            for i, (k, v) in enumerate(bounded_arguments.arguments.items()):

                if i == 0 and (k == "self" or k == "cls"):
                    # we skip cls or self if they are the first argument
                    # provided.
                    continue

                input_hash.update(pickle.dumps((k, v)))
                arguments_representation += f"{k}={v}, "

            # we remove the last comma and space from the string representation
            # we added to the last parameter.
            arguments_representation = arguments_representation.rstrip(", ")
            h = input_hash.hexdigest()

            # this is where we will store/load the cached result to/from.
            cache_file = full_cache_dir / f"{h}.pkl"

            if cache_file.exists():
                # cache hit!
                LOGGER.debug(
                    f"Loading {function_name}({arguments_representation}) "
                    f"from {full_cache_dir} with hash {h}."
                )
                with open(cache_file, "rb") as f:
                    return pickle.load(f)
            else:
                # cache miss!
                result = func(*args, **kwargs)
                LOGGER.debug(
                    f"Loading {function_name}({arguments_representation}) "
                    f"to {full_cache_dir} with hash {h}."
                )
                with open(cache_file, "wb") as f:
                    pickle.dump(result, f)

            return result

        return wrapper

    return _memoize

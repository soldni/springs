import warnings
from typing import Optional, Type, Union

from .utils import clean_multiline

__all__ = [
    "toggle_warnings",
    "warn_on_missing_type_in_init",
    "warn_on_flexyclass_fn",
]


global _EMIT_WARNINGS
_EMIT_WARNINGS = True


def _warn_fn(
    msg: str, category: Optional[Type[Warning]] = None, stacklevel: int = 2
) -> None:
    category = category or RuntimeWarning
    global _EMIT_WARNINGS

    if _EMIT_WARNINGS:
        warnings.warn(clean_multiline(msg), category, stacklevel=stacklevel)


def toggle_warnings(action: Optional[bool] = None) -> None:
    global _EMIT_WARNINGS
    if action is None:
        action = not _EMIT_WARNINGS
    _EMIT_WARNINGS = action


def warn_on_missing_type_in_init(
    type_: Union[Type, None], fn_name: str
) -> None:
    if type_ is None:
        _warn_fn(
            f"""It is strongly recommended to provide a _type_ argument
                  to `{fn_name}`. This ensures that the correct type is
                  annotated as the return value. Further, it performs type
                  checking on the initialized object."""
        )


def warn_on_flexyclass_fn() -> None:
    _warn_fn(
        """Decorating with `flexyclass` is discouraged because it does not
             play nicely with mypy, resulting in incorrect type annotations.
             Instead, consider decorating with `@dataclass` first, and then
             decorating `@make_flexy` on the resulting class."""
    )

import importlib.metadata
import inspect
import os
import re
import sys
import warnings
from ast import literal_eval
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, Optional, Type


def clean_multiline(string: str) -> str:
    string = dedent(string.strip())
    string = re.sub(r"\s*\n\s*", " ", string)
    return string


def get_annotations(obj: Any) -> Dict[str, type]:
    # use inspect.get_annotations if python >= 3.10
    if sys.version_info >= (3, 10):
        return inspect.get_annotations(obj)
    else:
        return getattr(obj, "__annotations__", {})


def get_version() -> str:
    """Get the version of the package."""

    # This is a workaround for the fact that if the package is installed
    # in editable mode, the version is not reliability available.
    # Therefore, we check for the existence of a file called EDITABLE,
    # which is not included in the package at distribution time.
    path = Path(__file__).parent / "EDITABLE"
    if path.exists():
        return "dev"

    try:
        # package has been installed, so it has a version number
        # from pyproject.toml
        version = importlib.metadata.version(__package__ or __name__)
    except importlib.metadata.PackageNotFoundError:
        # package hasn't been installed, so set version to "dev"
        version = "dev"

    return version


class SpringsWarnings:
    WARNINGS = literal_eval(os.environ.get("SPRINGS_WARNINGS", "True"))

    @classmethod
    def toggle(cls, value: Optional[bool] = None):
        if value is None:
            value = not cls.WARNINGS
        cls.WARNINGS = value

    @classmethod
    def _warn(
        cls: Type["SpringsWarnings"],
        message: str,
        category: Type[Warning],
        stacklevel: int = 2,
    ):
        if cls.WARNINGS:
            warnings.warn(message, category, stacklevel=stacklevel)

    @classmethod
    def missing_type(cls: Type["SpringsWarnings"], fn_name: str, type_: Any):
        if type_ is None:
            cls._warn(
                clean_multiline(
                    f"""It is strongly recommended to provide a _type_ argument
                        to `{fn_name}`. This ensures that the correct type is
                        annotated as the return value. Further, it performs
                        type checking on the initialized object."""
                ),
                category=UserWarning,
            )

    @classmethod
    def deprecated(
        cls: Type["SpringsWarnings"],
        deprecated: str,
        removed_when: Optional[str] = None,
        replacement: Optional[str] = None,
    ):
        msg = f"`{deprecated}` is deprecated"
        if removed_when:
            msg += f" and will be removed in Springs {removed_when}."
        else:
            msg += " and may be removed in a future version."

        if replacement:
            msg += f" Use `{replacement}` instead."

        cls._warn(message=msg, category=DeprecationWarning)

    @classmethod
    def argument(cls: Type["SpringsWarnings"], arg_name: str, obj_name: str):
        cls._warn(
            f"'{arg_name}' was provided to `{obj_name}`, but it is ignored",
            category=SyntaxWarning,
        )


class SpringsConfig:
    """A class to hold the configuration for Springs"""

    RICH_LOCALS: bool = literal_eval(
        os.environ.get("SPRINGS_RICH_LOCALS", "False")
    )
    RICH_TRACEBACK_INSTALLED: bool = False
    DEBUG: bool = literal_eval(os.environ.get("SPRINGS_DEBUG", "False"))

    @classmethod
    def toggle_rich_locals(cls, value: Optional[bool] = None) -> bool:
        cls.RICH_LOCALS = (
            (not cls.RICH_LOCALS) if (value is None) else bool(value)
        )
        return cls.RICH_LOCALS

    @classmethod
    def toggle_debug(cls, value: Optional[bool] = None) -> bool:
        cls.DEBUG = (not cls.DEBUG) if (value is None) else bool(value)
        return cls.DEBUG

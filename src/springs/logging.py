import logging
from multiprocessing import current_process
from pathlib import Path
from typing import Optional, Type, Union

from .utils import SpringsWarnings


class configure_logging:
    _DEBUG_MODE: bool = False

    @classmethod
    def debug(
        cls: Type["configure_logging"], *args, **kwargs
    ) -> logging.Logger:

        if "logging_level" in kwargs:
            SpringsWarnings.argument("logging_level", "debug")

        kwargs["logging_level"] = logging.DEBUG

        cls._DEBUG_MODE = True

        return cls.__new__(cls, *args, **kwargs)

    def __new__(  # type: ignore
        cls: Type["configure_logging"],
        logger_name: Optional[str] = None,
        file_logging_path: Optional[Path] = None,
        make_dir_if_missing: bool = True,
        fmt: str = "[%(asctime)s][%(name)s][%(levelname)s] %(message)s",
        datefmt: str = "%Y-%m-%d %H:%M:%S",
        logging_level: Union[int, str] = logging.INFO,
        force_root_reattach: bool = True,
        root_formatter_kwargs: Optional[dict] = None,
        stream_handler_kwargs: Optional[dict] = None,
        file_handler_kwargs: Optional[dict] = None,
        basic_config_kwargs: Optional[dict] = None,
        additional_handlers: Optional[list] = None,
    ) -> logging.Logger:
        """A big function that speeds up configuration of logging"""

        if isinstance(logging_level, str):
            logging_level = getattr(logging, logging_level)

        # we abide by the global debugging flag
        logging_level = logging.DEBUG if cls._DEBUG_MODE else logging_level

        # change how the formatter looks
        kw = root_formatter_kwargs or {}
        root_formatter = logging.Formatter(fmt=fmt, datefmt=datefmt, **kw)

        handlers = list(additional_handlers or [])

        kw = stream_handler_kwargs or {}
        root_stream_handler = logging.StreamHandler(**kw)
        root_stream_handler.setFormatter(root_formatter)
        handlers.append(root_stream_handler)

        if file_logging_path is not None:
            file_logging_path = Path(file_logging_path)

            if make_dir_if_missing:
                file_logging_path.parent.mkdir(parents=True, exist_ok=True)

            path_name = (
                f"{file_logging_path.stem}"
                f"_{current_process().name}"
                f"{file_logging_path.suffix}"
            )

            kw = file_handler_kwargs or {}
            root_file_handler = logging.FileHandler(
                filename=file_logging_path.parent / path_name, **kw
            )
            root_file_handler.setFormatter(root_formatter)
            handlers.append(root_file_handler)

        # add the handlers to the root logger, force reattaching other loggers
        kw = basic_config_kwargs or {}
        logging.basicConfig(
            level=logging_level,
            force=force_root_reattach,
            handlers=handlers,
            **kw,
        )
        return logging.getLogger(logger_name)

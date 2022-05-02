import logging
import os
from multiprocessing import current_process
from typing import Type, Union
import warnings

from .utils import mkdir_p


class configure_logging:
    _DEBUG_MODE = None

    @classmethod
    def debug(cls: Type['configure_logging'],
              *args,
              logging_level: int = None,
              **kwargs) -> logging.Logger:

        if logging_level is not None:
            msg = '`logging_level` was provided to `debug`, but it is ignored'
            warnings.warn(msg)

        cls._DEBUG_MODE = True
        return cls(*args, logging_level=logging.DEBUG, **kwargs)

    def __new__(
        cls: Type['configure_logging'],
        logger_name: str = None,
        file_logging_path: str = None,
        make_dir_if_missing: bool = True,
        fmt: str = "[%(asctime)s][%(name)s][%(levelname)s] %(message)s",
        datefmt: str = "%Y-%m-%d %H:%M:%S",
        logging_level: Union[int, str] = logging.INFO,
        force_root_reattach: bool = True,
        root_formatter_kwargs: dict = None,
        stream_handler_kwargs: dict = None,
        file_handler_kwargs: dict = None,
        basic_config_kwargs: dict = None,
        additional_handlers: list = None,
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
            path_dir, path_name = os.path.split(file_logging_path)

            path_dir = mkdir_p(path_dir) if make_dir_if_missing else path_dir

            path_name, path_ext = os.path.splitext(path_name)
            path_name = f'{path_name}_{current_process().name}{path_ext}'

            kw = file_handler_kwargs or {}
            root_file_handler = logging.FileHandler(
                filename=os.path.join(path_dir, path_name), **kw)
            root_file_handler.setFormatter(root_formatter)
            handlers.append(root_file_handler)

        # add the handlers to the root logger, force reattaching other loggers
        kw = basic_config_kwargs or {}
        logging.basicConfig(level=logging_level,
                            force=force_root_reattach,
                            handlers=handlers, **kw)
        return logging.getLogger(logger_name)

import logging
from logging import StreamHandler, Handler
from multiprocessing import current_process
from pathlib import Path
from typing import List, Optional, Union

from .utils import SpringsConfig

from rich.logging import RichHandler


def configure_logging(
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
    additional_handlers: Optional[List[Handler]] = None,
    skip_formatter_for_handlers: Optional[bool] = False,
    add_rich_traceback: bool = True,
    rich_traceback_kwargs: Optional[dict] = None,
    use_rich_handler: bool = True,
) -> logging.Logger:
    """A big function that speeds up configuration of logging"""

    if add_rich_traceback:
        from .rich_utils import install
        install(**(rich_traceback_kwargs or {}))

    if isinstance(logging_level, str):
        logging_level = getattr(logging, logging_level)

    # we abide by the global debugging flag
    logging_level = logging.DEBUG if SpringsConfig.DEBUG else logging_level

    # change how the formatter looks
    root_formatter = logging.Formatter(
        fmt=fmt, datefmt=datefmt, **(root_formatter_kwargs or {})
    )

    # get any additional handlers, set the formatter to match the one abo
    additional_handlers = additional_handlers or []
    for hdl in additional_handlers:
        if not skip_formatter_for_handlers:
            hdl.setFormatter(root_formatter)

    # setup the stream handler; either using the built-in one or the
    # one from the rich library depending on options.
    if use_rich_handler:
        # rich comes with its own format, so we don't need to set it here
        root_stream_handler = RichHandler(**(stream_handler_kwargs or {}))
    else:
        root_stream_handler = StreamHandler(**(stream_handler_kwargs or {}))
        root_stream_handler.setFormatter(root_formatter)

    handlers: List[Handler] = [root_stream_handler] + additional_handlers

    if file_logging_path is not None:
        # if a file logging path is provided, we setup a file handler
        # to log to that file.
        file_logging_path = Path(file_logging_path)

        if make_dir_if_missing:
            file_logging_path.parent.mkdir(parents=True, exist_ok=True)

        path_name = (
            f"{file_logging_path.stem}"
            f"_{current_process().name}"
            f"{file_logging_path.suffix}"
        )
        root_file_handler = logging.FileHandler(
            filename=file_logging_path.parent / path_name,
            **(file_handler_kwargs or {})
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

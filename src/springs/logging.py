from logging import (
    FileHandler,
    Formatter,
    Handler,
    Logger,
    StreamHandler,
    basicConfig,
    getLevelName,
    getLogger,
)
from multiprocessing import current_process
from pathlib import Path
from typing import List, Optional, Union

from rich.logging import RichHandler

from .utils import SpringsConfig


def configure_logging(
    logger_name: Optional[str] = None,
    file_logging_path: Optional[Path] = None,
    make_dir_if_missing: bool = True,
    fmt: str = "[%(asctime)s][%(name)s][%(levelname)s] %(message)s",
    datefmt: str = "%Y-%m-%d %H:%M:%S",
    logging_level: Union[int, str, None] = None,
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
) -> Logger:
    """Configure logging and returns a logger of name `logger_name` or the root
    logger if a name is not provided.

    Args:
        logger_name (Optional[str], optional): The name of the logger to
            configure. If not provided, it returns the root logger.  Defaults
            to None.
        file_logging_path (Optional[Path], optional): The path to the file
            where logs should be written. If not provided, no logs are not
            written to a file.  Defaults to None.
        make_dir_if_missing (bool, optional): If True, the directory where
            the file logging path is located is created if it does not exist.
            Defaults to True.
        fmt (str, optional): The format of the log message. Defaults to
            "[DATE-TIME][NAME][LEVEL] MESSAGE".
        datefmt (str, optional): The format of the date in the log message.
            Defaults to YEAR-MONTH-DAY HOUR-MINUTE-SECOND.
        logging_level (Union[int, str], optional): The level of logs to
            display. By default, it is set to the value of the root logger.
        force_root_reattach (bool, optional): If True, all loggers are
            reattached to the new handlers. Defaults to True.
        root_formatter_kwargs (Optional[dict], optional): The keyword
            arguments to pass to the formatter for the root logger. Defaults
            to no extra keyword arguments.
        stream_handler_kwargs (Optional[dict], optional): The keyword
            arguments to pass to the stream handler. Defaults to no extra
            keyword arguments.
        file_handler_kwargs (Optional[dict], optional): The keyword
            arguments to pass to the file handler. Defaults to no extra
            keyword arguments.
        basic_config_kwargs (Optional[dict], optional): The keyword
            arguments to pass to the basicConfig function. Defaults to no
            extra keyword arguments.
        additional_handlers (Optional[List[Handler]], optional): A list of
            additional handlers to add to the logger. Defaults to no extra
            handlers beside the stream handler.
        skip_formatter_for_handlers (Optional[bool], optional): If True,
            the formatter is not added to the additional handlers. Defaults to
            False.
        add_rich_traceback (bool, optional): If True, rich is used to print
            tracebacks in case of exceptions. Defaults to True.
        rich_traceback_kwargs (Optional[dict], optional): The keyword
            arguments to pass to the function that adds rich traceback.
            Defaults to no extra keyword arguments.
        use_rich_handler (bool, optional): If True, the rich handler is as
            stream handler. Defaults to True.
    """

    if add_rich_traceback:
        from .rich_utils import install

        install(**(rich_traceback_kwargs or {}))

    if SpringsConfig.DEBUG:
        logging_level = getLevelName("DEBUG")
    elif logging_level is not None:
        logging_level = getLevelName(logging_level)

    # change how the formatter looks
    root_formatter = Formatter(
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
        root_file_handler = FileHandler(
            filename=file_logging_path.parent / path_name,
            **(file_handler_kwargs or {}),
        )
        root_file_handler.setFormatter(root_formatter)
        handlers.append(root_file_handler)

    # add the handlers to the root logger, force reattaching other loggers
    kw = basic_config_kwargs or {}
    basicConfig(
        level=logging_level,
        force=force_root_reattach,
        handlers=handlers,
        **kw,
    )
    return getLogger(logger_name)


import errno
import os
from ast import literal_eval
from typing import Any, Callable, Type

import smart_open


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise
    return path


class hybridmethod:
    """A decorator that allows overloading a method depending
    on whether it is a class method or instance method. From
    https://stackoverflow.com/a/28238047"""

    def __init__(self, f_class, finstance=None, doc=None):
        self.f_class = f_class
        self.f_instance = finstance
        self.__doc__ = doc or f_class.__doc__
        # support use on abstract base classes
        self.__isabstractmethod__ = bool(
            getattr(f_class, '__isabstractmethod__', False)
        )

    def classmethod(self, f_class):
        return type(self)(f_class, self.f_instance, None)

    def instancemethod(self, f_instance):
        return type(self)(self.f_class, f_instance, self.__doc__)

    def __get__(self, instance, cls):
        if instance is None or self.f_instance is None:
              # either bound to the class, or no instance method available
            return self.f_class.__get__(cls, None)
        return self.f_instance.__get__(instance, cls)


class MISSING:
    """Used to keep track of missing parameters"""

    def __repr__(self) -> str:
        return 'MISSING'


def type_evaluator(field_type: Type[Any]) -> Callable:
    """Constructs a simple eval function for command line args
    that does proper casting depending on field_type"""

    def _type_fn(value: str) -> field_type:
        if not issubclass(field_type, str):
            # unless the type is string, we use literal
            # eval to cast to a built in python type;
            # literal_eval supports things such as list, dict,
            # etc. too!
            value = literal_eval(value)

        return field_type(value)
    return _type_fn


def read_raw_file(file_path: str) -> str:
    """For reading the content of a file from multiple
    providers."""
    with smart_open.open(file_path, mode='r', encoding='utf-8') as f:
        content = f.read()
    return content

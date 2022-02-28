
from ast import literal_eval
import smart_open
from typing import Any, Callable, Type


class hybridmethod:
    """A decorator that allows overloading a method depending
    on whether it is a class method or instance method. From
    https://stackoverflow.com/a/28238047"""

    def __init__(self, fclass, finstance=None, doc=None):
        self.fclass = fclass
        self.finstance = finstance
        self.__doc__ = doc or fclass.__doc__
        # support use on abstract base classes
        self.__isabstractmethod__ = bool(
            getattr(fclass, '__isabstractmethod__', False)
        )

    def classmethod(self, fclass):
        return type(self)(fclass, self.finstance, None)

    def instancemethod(self, finstance):
        return type(self)(self.fclass, finstance, self.__doc__)

    def __get__(self, instance, cls):
        if instance is None or self.finstance is None:
              # either bound to the class, or no instance method available
            return self.fclass.__get__(cls, None)
        return self.finstance.__get__(instance, cls)


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
            # literal_eval supports things such as list, dict, etc. too!
            value = literal_eval(value)

        return field_type(value)
    return _type_fn


def read_raw_file(file_path: str) -> str:
    with smart_open.open(file_path, mode='r', encoding='utf-8') as f:
        content = f.read()
    return content

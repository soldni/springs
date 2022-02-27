import functools
import logging
from platform import node
import re
import copy
import inspect
from typing import (
    Any,
    Iterable,
    List,
    Sequence,
    Set,
    Tuple,
    Type,
    Union,
    Dict,
    Optional,
    TypeVar,
    Generic
)
import yaml

logging.basicConfig()
LOGGER = logging.getLogger(__name__)

CN = TypeVar('CN', bound='ConfigNode')
CV = TypeVar('CV', bound='ConfigPlaceholderVar')
CP = TypeVar('CP', bound='ConfigParam')
CR = TypeVar('CR', bound='ConfigNodeProperties')


class ConfigParam(Generic[CP]):
    """Type wrapper to indicate parameters in a config node."""
    type: Type

    def __new__(cls: Type[CP], target_type: Type) -> Type[CP]:
        class ConfigTypedParam(cls):
            type = target_type
        return ConfigTypedParam


class ConfigNodeProperties(Generic[CR]):
    PROPERTIES_NAME = '__node__'

    def __init__(self: CR, node: CN, name: str, parent: CN = None):
        self.node = node
        self.config_vars = []
        self.param_keys = set()
        self.set_parent(parent)
        self.set_name(name)
        self.__set_properties()

    @property
    def node_cls(self):
        return self.node.__class__

    @property
    def cls_name(self):
        return self.node_cls.__name__

    @classmethod
    def get_properties(cls: Type[CR], node: CN) -> CR:
        return getattr(node, cls.PROPERTIES_NAME)

    def __set_properties(self: CR):
        setattr(self.node, self.PROPERTIES_NAME, self)

    def set_parent(self: CR, parent_node: Union[CN, None]):
        # keep track of which is the root node for this config
        self.parent = self.node if parent_node is None else parent_node

    def set_name(self: CR, node_name: Union[str, None]):
            # set the full path to this node as its name
        self.short_name = self.node_cls.__name__ if node_name is None else node_name
        self.long_name = (node_name if self.is_root() else
                          f'{self.get_properties(self.parent).long_name}.{node_name}')

    def get_annotations(self: CR) -> Dict[str, ConfigParam]:
        # these are all annotations for parameters for this node; we use
        # them to cast param values to the right type as we parse a config
        annotations = {name: annotation for name, annotation in
                       getattr(self.node_cls, '__annotations__', {}).items()
                       if issubclass(annotation, ConfigParam)}
        return annotations

    def get_defaults(self: CR) -> Dict[str, Any]:
        # These are all the default values that have been provided
        # for the parameters for this node.
        defaults = {name: self.node_cls.__dict__[name]
                    for name in self.get_annotations()
                    if name in self.node_cls.__dict__}
        return defaults

    def get_subnodes(self: CR) -> Dict[str, CN]:
        # these are almost all the subnodes for the node; for now, we
        # capture the ones that are of the form
        #   class node(ConfigNode):
        #     class subnode (ConfigNode):
        #       ...
        # we process the ones that are fully unspecified, such as FlexNodes,
        # as part of the annotations:
        #   class node(ConfigNode):
        #     subnode: ConfigParam(FlexNode) = None
        #     ...
        subnodes = {name: cls_ for name, cls_ in self.node_cls.__dict__.items()
                    if inspect.isclass(cls_) and issubclass(cls_, ConfigNode)}
        return subnodes

    def assign_param(self, name: str, value: Any):
        # printing some debug info
        root = ' (root)' if self.is_root() else ''
        LOGGER.debug(f'[{self.long_name}{root}] {name}={value}')

        # do the actual assignment
        self.param_keys.add(name)
        setattr(self.node, name, value)

    def get_params_names(self: CR) -> Iterable[str]:
        yield from self.param_keys

    def add_var(self: CR, var: CV):
        self.config_vars.append(var)

    def is_root(self: CR) -> bool:
        return self.parent == self.node

    def get_root(self: CR) -> CN:
        """Traverse the configuration this node is part of to find the root node"""
        if self.is_root():
            return self
        else:
            return self.get_properties(self.parent).get_root()

    def get_children(self: CN) -> Iterable[CN]:
        """Get a iterable of all the subnodes to this config node"""
        for key, value in sorted(self.node):
            if isinstance(value, ConfigNode):
                yield (key, value)

    def apply_vars(self: CR) -> Set[str]:
        """Resolve all variables by applying substitutions to its
        parameters or its subnodes'. Raises a RuntimeError in case
        of a cyclical dependency."""
        try:
            while len(self.config_vars) > 0:
                var: ConfigPlaceholderVar = self.config_vars[0]
                var.resolve()
                self.config_vars.pop(0)

            for _, node in self.get_children():
                self.get_properties(node).apply_vars()
        except RecursionError:
            msg = ('Variables in your configuration cannot be resolved '
                   'due to cyclical assignments. Check your config!')
            raise RuntimeError(msg)

    def to_dict(self: CR) -> Dict[str, Any]:
        return {k: (self.get_properties(v).to_dict() if isinstance(v, ConfigNode)
                    else (repr(v) if isinstance(v, ConfigPlaceholderVar) else v))
                for k, v in self.node}

    def to_yaml(self: CR, *args: Sequence[Any], **kwargs: Dict[str, Any]) -> str:
        return yaml.safe_dump(self.to_dict(), *args, **kwargs)



class ConfigNode(Generic[CN]):
    """A generic configuration node."""

    def __init__(
        self: CN,
        config: Optional[Dict[str, Any]] = None,
        __parent__ : CN = None,
        __flex_node__: bool = False,
        __name__: str = None
        ) -> None:

        node_props = ConfigNodeProperties(node=self, name=__name__, parent=__parent__)

        # get annnotations, defaults, and subnodes. Will be used to look up the
        # right types for values, get their default value, and instantiate any
        # subnode to this config node.
        annotations = node_props.get_annotations()
        defaults = node_props.get_defaults()
        subnodes = node_props.get_subnodes()

        # if the config provided is empty, we try to make do with just default values
        config = config or {}

        # override with options that are provided in `config` argument
        for param_name, param_value in config.items():

            if '@' in param_name:
                # we have a registry reference! we need to extract the
                # reference and get the config from the registry.

                # first, we import from the registry; we do it here to avoid
                # circular references.
                from espresso_config.registry import ConfigRegistry

                # we split parameter name out, and the the right constructor
                # for this reference out of the registry.
                param_name, registry_reference_name = param_name.split('@', 1)
                registry_config_cls = ConfigRegistry.get(registry_reference_name)
            else:
                registry_config_cls = None

            # check if it is a valid parameter, if not, raise a KeyError
            if ((param_name not in annotations) and
                (param_name not in subnodes) and
                not(__flex_node__)):
                # CASE 0: we can't add this key to this config; raise an error.
                msg = f'Parameter "{param_name}" not supported in "{node_props.cls_name}"'
                raise KeyError(msg)

            if registry_config_cls is not None:
                # CASE 1: we just pulled a config object out of the registry! let's
                #         use it to initialize the value for this parameter. we provide
                #         the value of the config as an input.
                param_value = registry_config_cls(
                    param_value, __parent__=self, __name__=param_name
                )

            elif ConfigPlaceholderVar.has_placeholder_var(param_value):
                # CASE 2: you found a value with a variable in it; we save it with
                #         the rest of the vars, and it will be resolved it later.
                param_value = ConfigPlaceholderVar(
                    parent_node=self,
                    param_name=param_name,
                    param_value=param_value,
                    param_config=annotations.get(param_name, None)
                )
                node_props.add_var(param_value)
            elif param_name in annotations:
                # CASE 3: you found a value for with we have a type annotation!
                #         you cast to that type and add it to the node.

                # we do different things depending on what the type of the
                # parameter is, so we first extract the type.
                param_type = annotations[param_name].type

                if inspect.isclass(param_type) and issubclass(param_type, ConfigNode):
                    # CASE 3.1: sometimes the type of a paramemter is ConfigNode
                    #           or a subclass of it, making necessary to pass some extra
                    #           parameters to the constructor instead of just
                    #           `param_value`. we accomplish that with a partial decorator.
                    param_type = functools.partial(
                        param_type, __parent__=self, __name__=param_name
                    )
                param_value = param_type(param_value)

            elif param_name in subnodes:
                # CASE 4: This parameter corresponds to a subnode! we create
                #         the subnode and set that as parameter value
                param_value = subnodes[param_name](
                    config=param_value, __parent__=self, __name__=param_name
                )
            elif __flex_node__:
                # CASE 5: I don't recognize this key, but I'm in flex config mode
                #         so I'll just add it to this node object (config_value
                #         is already asssigned, that's why we just pass here).
                pass
            else:
                # CASE ∞: Something went wrong and you reached a technically
                #         unreachable branch! Someone will have to investigate.
                msg = 'Unreachable! Please file an issue.'
                raise RuntimeError(msg)

            # add parameter to set of parameters in this node and assign it
            node_props.assign_param(name=param_name, value=param_value)

        # try using default values for parameters with no override
        for param_name in annotations:
            if param_name in config:
                # this parameter is already assigned
                continue
            if param_name not in defaults:
                msg = f'parameter "{param_name}" missing for "{node_props.cls_name}"'
                raise ValueError(msg)

            param_value = copy.deepcopy(defaults[param_name])
            if ConfigPlaceholderVar.has_placeholder_var(param_value):
                param_value = ConfigPlaceholderVar(
                    parent_node=self,
                    param_name=param_name,
                    param_value=param_value,
                    annotation=annotations[param_name]
                )
                node_props.add_var(param_value)

            # add parameter to set of parameters in this node and
            # assign its DEFAULT VALUE
            node_props.assign_param(name=param_name, value=param_value)

        # try instantitate nodes with no overrides
        for param_name, subnode_cls in subnodes.items():
            if param_name in config:
                # this parameter is already assigned
                continue
            param_value = subnode_cls(__parent__=self, __name__=param_name)

            # add the subnode to the config!
            node_props.assign_param(name=param_name, value=param_value)

        # finally, if this is a root class, we want to take care of replacing
        # variables with actual values; not going to do any late binding a la
        # hydra, with some minimal logic to catch cyclical assignments
        if node_props.is_root():
            node_props.apply_vars()

    def __iter__(self: CN) -> Iterable[Tuple[str, Any]]:
        """Get a iterable of names and parameters in this node, including subnodes"""
        yield from ((k, self[k]) for k in
                    ConfigNodeProperties.get_properties(self).get_params_names())

    def __len__(self: CN) -> int:
        return sum(1 for _ in self)


class ConfigPlaceholderVar(Generic[CV]):
    """A Placeholder for config values that contains a variable.
    Placeholder variables are specified using the following format:

        PLACEHOLDER := ${PATH_TO_VALUE}
        PATH_TO_VALUE := PATH_TO_VALUE.VAR_NAME
        VAR_NAME := [a-zA-Z_]\w+

    PATH_TO_VALUE is used to traverse down the config node
    to find suitable replacement values for the placeholder.
    """

    VAR_TEMPLATE = r'^\$\{(([a-zA-Z_]\w*)\.?)+\}$'

    def __init__(
        self: CV,
        parent_node: ConfigNode,
        param_name: str,
        param_value: str,
        param_config: Optional[ConfigParam] = None
    ):
        self.param_name = param_name
        self.parent_node = parent_node
        self.unresolved_param_value = param_value
        self.param_config = param_config
        self.placeholder_vars = {}

        self.var_match = re.match(self.VAR_TEMPLATE, param_value).group()
        self.var_path = tuple(self.var_match[2:-1].split('.'))

    def __repr__(self: CV) -> str:
        return self.__str__()

    def __str__(self: CV) -> str:
        return str(self.unresolved_param_value)

    def resolve(self: CV):
        """Replace variables in this value with their actual value"""

        # we need to start looking from the root
        root_node = self.parent_node._get_root()

        # this reduce function traverses the config from the
        # root node to get to the variable that we want
        # to use for substitution
        placeholder_substitution = functools.reduce(
            lambda node, key: node[key], self.var_path, root_node
        )

        # if the substitution is a full subnode, wee call
        # apply_vars to make sure that all substitutions in
        # the subnode are gracefully handled
        if isinstance(placeholder_substitution, ConfigNode):
            ConfigNodeProperties.get_properties(placeholder_substitution).apply_vars()

        # note that we make a copy of the object to avoid
        # unwanted side effects
        replaced_value = copy.deepcopy(placeholder_substitution)

        if isinstance(replaced_value, ConfigNode):
            # we need to handle the case of a config node a bit
            # differently, including make sure that the lineage
            # and the parent of the new node are correctly set.
            node_props = ConfigNodeProperties.get_properties(replaced_value)
            node_props.set_parent(self.parent_node)
            node_props.set_name(self.param_name)

        setattr(self.parent_node, self.param_name, replaced_value)

    @classmethod
    def has_placeholder_var(cls: Type[CV], value: Any) -> bool:
        """Returns True if value has variable (${...})
           somewhere, False otherwise"""
        if isinstance(value, str) and re.findall(cls.VAR_TEMPLATE, value):
            return True
        return False


class ConfigFlexNode(ConfigNode):
    """Just like a ConfigNode, except it allows for additional
    parameters other than the ones provided with annotations"""
    def __init__(
        self: CN,
        *args: List[Any],
         __flex_node__: bool = True,
        **kwargs: Dict[str, Any]
    ) -> None:
        super().__init__(*args, __flex_node__=True, **kwargs)

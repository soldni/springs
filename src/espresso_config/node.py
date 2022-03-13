import copy
import functools
import logging
import re
from dataclasses import dataclass, field
from inspect import getmembers, isclass, isroutine
from typing import (Any, Dict, Generic, Iterable, List, NamedTuple, Optional,
                    Sequence, Set, Tuple, Type, TypeVar, Union, get_type_hints)

import yaml

from .utils import MISSING, hybridmethod


# get logger for this file, mostly used for debugging
LOGGER = logging.getLogger(__name__)


# Type declaration for classes
T = TypeVar("T")
CN = TypeVar('CN', bound='ConfigNode')
CV = TypeVar('CV', bound='ConfigPlaceholderVar')
CP = TypeVar('CP', bound='ConfigParam')
CR = TypeVar('CR', bound='ConfigNodeProps')
CE = TypeVar('CE', bound='ConfigRegistryReference')
PS = TypeVar('PS', bound='ParameterSpec')

# Constants
CONFIG_NODE_PROPERTIES_NAME = '__node__'
CONFIG_NODE_REGISTRY_SEPARATOR = '@'
CONFIG_PARAM_CLI_FORMAT = r'([a-zA-Z_]\w*)(\.([a-zA-Z_]\w*))*=.*'
CONFIG_PLACEHOLDER_VAR_TEMPLATE = (
    r'\$\{(([a-zA-Z_]\w*)\.?)*(%s[a-zA-Z_]+)*\}' %
    CONFIG_NODE_REGISTRY_SEPARATOR
)


class ParameterSpec(NamedTuple):
    """Holds a parameter spec. Can be instantiated from either string or
    by passing the attributes directly."""

    name: str
    default: T
    type: Type[T]

    @classmethod
    def from_string(cls: Type[PS], string: str) -> PS:
        if not re.findall(CONFIG_PARAM_CLI_FORMAT, string):
            msg = f"Cannot parse string '{string}' into a parameter"
            raise ValueError(msg)
        name, default = string.split('=', 1)
        default = yaml.safe_load(default)
        return cls(name=name, default=default, type=type(default))

    def to_dict(self: PS) -> dict:
        outdict = None
        for part in self.name.split('.')[::-1]:
            outdict = {part: outdict} if outdict else {part: self.default}
        return outdict


class ConfigParam(Generic[CP]):
    """Type wrapper to indicate parameters in a config node."""
    type: T

    def __new__(cls: Type[CP], target_type: T) -> T:
        class ConfigTypedParam(cls):
            type = target_type
        return ConfigTypedParam


class ConfigRegistryReference(Generic[CE]):
    """Extract registry references and resolve them"""
    def __init__(
        self: CE,
        param_name: str = None,
        registry_ref: str = None,
        registry_args: Sequence[Any] = None
    ):
        self.param_name = param_name
        self.registry_ref = registry_ref
        self.registry_args = registry_args or []

    def name_as_placeholder_variable(self: CE):
        """Split the name (if provided) to be used
        as the path for placeholder variable"""
        if self.param_name:
            return self.param_name.split('.')
        return None

    @classmethod
    def from_str(cls: Type[CE], string: str) -> CE:
        args = string.split(CONFIG_NODE_REGISTRY_SEPARATOR)
        if len(args) == 1:
            # no reference
            return cls(param_name=args[0])
        else:
            param_name, registry_ref, *args = args
            return cls(param_name=param_name,
                       registry_ref=registry_ref,
                       registry_args=args)

    def resolve(self: CE,
                *args,
                nodes_cls: Sequence[CN] = None,
                **kwargs) -> Any:
        """Resolves and instantiates a reference to a registry object using
        `param_value`. `nodes_cls` can be a list of ConfigNode objects to
        merge with no override to the registry reference (if the registry
        reference is itself a ConfigNode). `kwargs`, as well as `self.args`
        are passed to the registry reference constructor."""

        if self.registry_ref is None:
            # no-op if there is no registry ref!
            return args[0] if len(args) == 1 else args

        nodes_cls = nodes_cls or []

        from .registry import ConfigRegistry
        registry_reference = ConfigRegistry.get(self.registry_ref)

        for node_cls in nodes_cls:

            if isclass(node_cls) and not issubclass(node_cls, ConfigNode):
                msg = ('The registry reference resolver has receive an object'
                       f'of type {node_cls}, which is not a ConfigNode')
                raise ValueError(msg)

            if (isclass(registry_reference) and
                not issubclass(registry_reference, ConfigNode)):
                msg = ('The registry reference resolver has received one or '
                       'more ConfigNode, but they cannot be merged with a '
                       f'registry reference of type {type(registry_reference)}')
                raise ValueError(msg)

            registry_reference = registry_reference >> node_cls

        return registry_reference(*args, *self.registry_args, **kwargs)

    @classmethod
    def contains(cls, string: str) -> bool:
        return CONFIG_NODE_REGISTRY_SEPARATOR in string


class ConfigNodeProps(Generic[CR]):
    def __init__(self: CR, node: CN, name: str, parent: CN = None):
        self.node = node
        self.config_vars = []
        self.param_keys = set()
        self.set_parent(parent)
        self.set_name(name)
        self.__set_props()

    @property
    def node_cls(self):
        return type(self.node)

    @property
    def cls_name(self):
        return self.node_cls.__name__

    @classmethod
    def get_props(cls: Type[CR], node: CN) -> CR:
        return getattr(node, CONFIG_NODE_PROPERTIES_NAME)

    def __set_props(self: CR):
        """Binds this property file to a node."""
        setattr(self.node, CONFIG_NODE_PROPERTIES_NAME, self)

    def set_parent(self: CR, parent_node: Union[CN, None]):
        # keep track of which is the root node for this config
        self.parent = self.node if parent_node is None else parent_node

    def set_name(self: CR, node_name: Union[str, None]):
            # set the full path to this node as its name
        self.short_name = self.cls_name if node_name is None else node_name
        self.long_name = (
            self.short_name if self.is_root() else
            f'{self.get_props(self.parent).long_name}.{self.short_name}'
        )

    @hybridmethod
    def get_annotations(cls: Type[CR],
                        node_cls: Type[CN]) -> Dict[str, ConfigParam]:
        # these are all annotations for parameters for this node; we use
        # them to cast param values to the right type as we parse a config
        annotations = {name: annotation for name, annotation in
                       get_type_hints(node_cls).items()
                       if issubclass(annotation, ConfigParam)}
        return annotations

    @get_annotations.instancemethod
    def get_annotations(self: CR) -> Dict[str, ConfigParam]:
        return type(self).get_annotations(self.node_cls)

    @hybridmethod
    def get_defaults(cls: Type[CR], node_cls: Type[CN]) -> Dict[str, Any]:
        # These are all the default values that have been provided
        # for the parameters for this node.

        # We use getmembers instead of __dict__ because it
        # resolves inheritance (__dict__ does not!)
        all_members = dict(getmembers(node_cls))

        defaults = {name: all_members[name]
                    for name in cls.get_annotations(node_cls)
                    if name in all_members}
        return defaults

    @get_defaults.instancemethod
    def get_defaults(self: CR) -> Dict[str, Any]:
        return type(self).get_defaults(self.node_cls)

    @hybridmethod
    def get_subnodes(cls: Type[CR], node_cls: Type[CN]) -> Dict[str, CN]:
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

        # We use getmembers instead of __dict__ because it
        # resolves inheritance (__dict__ does not!)
        all_members = dict(getmembers(node_cls))
        subnodes = {name: cls_ for name, cls_ in all_members.items()
                    if isclass(cls_) and issubclass(cls_, ConfigNode)}
        return subnodes

    @get_subnodes.instancemethod
    def get_subnodes(self: CR) -> Dict[str, CN]:
        return type(self).get_subnodes(self.node_cls)

    @hybridmethod
    def get_all_cls_members(cls: Type[CR],
                            node_cls: Type[CN]) -> Dict[str, Any]:
        all_non_routines = getmembers(node_cls, lambda a: not(isroutine(a)))
        return {name: value for name, value in all_non_routines
                if not((name.startswith('__') and name.endswith('__')) or
                        name == '_is_protocol')}

    @get_all_cls_members.instancemethod
    def get_all_cls_members(self: CR) -> Dict[str, Any]:
        return type(self).get_all_cls_members(self.node_cls)

    @hybridmethod
    def get_all_parameters(cls: Type[CR],
                           node_cls: Type[CN]) -> Sequence[ParameterSpec]:
        """Get all parameters for this node as well as for its subnodes."""

        all_parameters = []

        annotations = cls.get_annotations(node_cls)
        defaults = cls.get_defaults(node_cls)

        for param_name, param_annotation in annotations.items():
            all_parameters.append(
                ParameterSpec(name=param_name,
                              type=param_annotation.type,
                              default=defaults.get(param_name, MISSING))
            )

        for subnode_name, subnode_cls in cls.get_subnodes(node_cls).items():
            for param_spec in cls.get_all_parameters(subnode_cls):
                all_parameters.append(
                    ParameterSpec(name=f'{subnode_name}.{param_spec.name}',
                                  type=param_spec.type,
                                  default=param_spec.default)
                )
        return all_parameters

    @get_all_parameters.instancemethod
    def get_all_parameters(self: CR) -> Sequence[ParameterSpec]:
        return type(self).get_all_parameters(self.node_cls)

    def assign_param(self, name: str, value: Any, annotation: Any = None):
        # printing some debug info
        LOGGER.debug(f'[ASSIGN VAR][{self.long_name}]'
                     f'[{self.cls_name}] {name}={value}')

        # do the actual assignment
        self.param_keys.add(name)
        setattr(self.node, name, value)

        # optionally set up annotation if provided
        # (for more advanced uses)
        if annotation is not None:
            if not hasattr(self.node, '__annotations__'):
                setattr(self.node, '__annotations__', {})
            setattr(self.node.__annotations__, name, annotation)

    def get_params_names(self: CR) -> Sequence[str]:
        return tuple(self.param_keys)

    def add_var(self: CR, var: CV):
        self.config_vars.append(var)

    def pop(self: CR, key: str, default=MISSING) -> Any:
        if key in self.param_keys:
            self.param_keys.remove(key)
            value = getattr(self.node, key)
            delattr(self.node, key)
            return value
        elif default != MISSING:
            return default
        else:
            KeyError(f'`{key}` is not a parameter in {self.long_name}')

    def is_root(self: CR) -> bool:
        return self.parent == self.node

    def get_root(self: CR) -> CN:
        """Traverse the configuration this node is part of to
        find the root node"""
        if self.is_root():
            return self.node
        else:
            return self.get_props(self.parent).get_root()

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
                self.get_props(node).apply_vars()
        except RecursionError:
            msg = ('Variables in your configuration cannot be resolved '
                   'due to cyclical assignments. Check your config!')
            raise RuntimeError(msg)

    def to_dict(self: CR) -> Dict[str, Any]:
        return {k: (self.get_props(v).to_dict()
                    if isinstance(v, ConfigNode) else
                    (repr(v) if isinstance(v, ConfigPlaceholderVar) else v))
                for k, v in self.node}

    def to_yaml(self: CR,
                *args: Sequence[Any],
                **kwargs: Dict[str, Any]) -> str:
        return yaml.safe_dump(self.to_dict(), *args, **kwargs)

    @hybridmethod
    def update(cls: Type[CR],
               node: CN,
               other_node: CN,
               flex: bool = False) -> Dict[str, Any]:
        """Create a new node node where values form `node`
        are updated with values from `other_node`."""

        # we are flexible if we are told to be or if any
        # of the nodes classes is.
        flex = (flex or
                isinstance(node, ConfigFlexNode) or
                isinstance(other_node, ConfigFlexNode))

        props = cls.get_props(node)
        other_props = cls.get_props(other_node)

        node_cls = ((props.node_cls << other_props.node_cls)
                    if flex else props.node_cls)

        config_values = props.to_dict()
        config_values.update(other_props.to_dict())

        return node_cls(config_values, __flex_node__=flex)

    @update.instancemethod
    def update(self: CR,
               other_node: CN,
               flex: bool = False) -> Dict[str, Any]:
        return type(self).update(node=self.node,
                                 other_node=other_node,
                                 flex=flex)


class MetaConfigNode(type):
    """A very simple metaclass for the config node that
    implements operators `>>` and `<<` between subclasses
    of ConfigNode.

    `A >> B` merges A into B, meaning that, if a parameter
    exists in both A and B, the version from A is kept.
    `A << B` merges B in to A; it is equivalent to `B >> A`
    """
    def __rshift__(cls: Type[CN], other_cls: Type[CN]) -> Type[CN]:
        merged = type(f'{cls.__name__}_{other_cls.__name__}',
                     (cls, other_cls),
                     {})
        return merged


    def __lshift__(cls: Type[CN], other_cls: Type[CN]) -> Type[CN]:
        return other_cls >> cls

    def __repr__(cls: Type[CN]):
        attributes = ConfigNodeProps.get_all_cls_members(cls)
        attributes_repr = ', '.join(f'{name}={repr(value)}'
                                    for name, value in attributes.items())
        return f'{cls.__name__}({attributes_repr})'


class ConfigNode(Generic[CN], metaclass=MetaConfigNode):
    """A generic configuration node."""

    def __init__(
        self: CN,
        config: Optional[Union[Dict[str, Any], CN]] = None,
        __parent__ : CN = None,
        __flex_node__: bool = False,
        __name__: str = None
        ) -> None:
        # Parsing comes in 5 phases, each one is in a separate code block!

        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ PHASE 0 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # This is mostly preliminaries

        # Create a property object for this node; the object will bind
        # itself to it
        node_props = ConfigNodeProps(node=self,
                                     name=__name__,
                                     parent=__parent__)

        # get annnotations, defaults, and subnodes. Will be used to look up the
        # right types for values, get their default value, and instantiate any
        # subnode to this config node.
        annotations = node_props.get_annotations()
        defaults = node_props.get_defaults()
        subnodes = node_props.get_subnodes()

        # if the config provided is empty, we try to make do with just default
        # values; we also check if it is of the right type (otherwise if it is
        # not the user will get inscrutable errors down the line).
        config = config or {}
        if isinstance(config, ConfigNode):
            # if it is a config node, we get its dict representation
            # first, and then initialize
            config = ConfigNodeProps.get_props(config).to_dict()

        if not isinstance(config, dict):
            msg = (f'Config to `{node_props.cls_name}` should be dict, '
                   f'but received {type(config)} instead!')
            raise ValueError(msg)
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ PHASE 1 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # Override with options that are provided in `config` dictionary
        for param_name, param_value in config.items():
            # a little lambda function to log how we are doing
            debug_call = lambda case: LOGGER.debug(
                f'[PARSE CONFIG][{node_props.long_name}][{case}] {param_name}'
            )

            if ConfigRegistryReference.contains(param_name):
                # we have a registry reference! we need to extract the
                # reference and get the config from the registry.
                registry_reference = ConfigRegistryReference.\
                    from_str(param_name)
                param_name = registry_reference.param_name
            else:
                registry_reference = None

            # check if it is a valid parameter, if not, raise a KeyError
            if ((param_name not in annotations) and
                (param_name not in subnodes) and
                not(__flex_node__) and
                registry_reference is None):
                debug_call('0.not_supported')
                # CASE 0: we can't add this key to this config; raise an error.
                msg = (f'Parameter "{param_name}" not '
                       f'supported in "{node_props.cls_name}"')
                raise KeyError(msg)

            if registry_reference is not None:
                # CASE 1: we just pulled a config object out of the
                #         registry! let's use it to initialize the value
                #         for this parameter. we provide the value of the
                #         config as an input.
                debug_call('1.registry')

                # It might be the case that we need merge a registry
                # reference with nodes (see explanation below). We keep
                # them in this list before passing them
                # registry_reference.resolve
                nodes_cls_to_merge = []
                if param_name in subnodes:
                    # CASE 1.1: beside the key with just loaded, we also
                    #           have a subnode with potentially some
                    #           default parameters! fear not, we
                    #           merge configs using operator `>>`
                    debug_call('1.1.registry+submodule')
                    nodes_cls_to_merge.append(subnodes[param_name])

                if (param_name in annotations and
                    issubclass(annotations[param_name].type, ConfigNode)):
                    # CASE 1.2: we also need to merge with the type we also
                    #           get from the parameter annotation. This is
                    #           usually empty, but we merge with it for
                    #           good measure too.
                    debug_call('1.2.registry+annotation')
                    nodes_cls_to_merge.append(annotations[param_name].type)

                # Finally after a bunch of merging (maybe?), we can instantiate
                # an object using the registry reference!
                param_value = registry_reference.resolve(
                    param_value,
                    nodes_cls=nodes_cls_to_merge,
                    __parent__=self,
                    __name__=param_name
                )
            elif ConfigPlaceholderVar.contains(param_value):
                # CASE 2: you found a value with a variable in it; we save
                #         it with the rest of the vars, and it will be
                #         resolved it later.
                debug_call('2.variable')
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
                debug_call('3.annotation')

                # we do different things depending on what the type of the
                # parameter is, so we first extract the type.
                param_type = annotations[param_name].type

                if (isclass(param_type) and
                    issubclass(param_type, ConfigNode)):
                    # CASE 3.1: sometimes the type of a paramemter is
                    #           ConfigNode or a subclass of it, making
                    #           necessary to pass some extra parameters to
                    #           the constructor instead of just `param_value`.
                    #           We accomplish that with a partial decorator.
                    debug_call('3.1.ann_subnode')

                    # It only makes sense to do this replacement
                    # if the parameter provided is a dict or a ConfigNode,
                    # because those can be parsed by a config node.
                    if isinstance(param_value, (dict, ConfigNode)):
                        param_type = functools.partial(
                            param_type, __parent__=self, __name__=param_name
                        )
                    else:
                        param_type = lambda x: x
                elif isinstance(param_value, param_type):
                    # We cast to param_type, but only if we absolutely
                    # have to. This prevents unwanted initializations is
                    # the param_type is a complex object. To maintain
                    # the code a bit more legible, we make param_type a
                    # no-op function if casting is not needed.
                    #
                    # (I discovered this while trying to understand why a
                    # trainer, which was expecting a logger, was being passed
                    # a logger that has itself as save_dir; it turns out it was
                    # because an object instance was passed as first parameter
                    # to the constructor itself due to this casting. checking
                    # if the object is already of the expected type should
                    # fix this).
                    param_type = lambda x: x

                # cast (or not!) here
                param_value = param_type(param_value)

            elif param_name in subnodes:
                # CASE 4: This parameter corresponds to a subnode! we create
                #         the subnode and set that as parameter value
                debug_call('4.subnode')

                if isinstance(param_value, (dict, ConfigNode)):
                    # note that calling the subnode init method here
                    # only make sense if we are dealing with a supported
                    # type (a dict or another config node). If not, it
                    # does not make much sense to call the constructor,
                    # as it would lead to errors down the line.
                    # NOTE: we could call it if param_value is none too,
                    # but we assume that if a user has specified a None
                    # here, they do not want to instantiate a subnode.
                    # if they still wish to, they could simply pass {} instead.
                    debug_call('4.1.subnode_applied')
                    param_value = subnodes[param_name](config=param_value,
                                                       __parent__=self,
                                                       __name__=param_name)
                else:
                    debug_call('4.2.subnode_skipped')
            elif __flex_node__:
                # CASE 5: I don't recognize this key, but I'm in flex config
                #         mode so I'll just add it to this node object
                #         (config_value is already asssigned, that's why we
                #         just pass here).
                debug_call('5.unrecognized')
            else:
                # CASE ∞: Something went wrong and you reached a technically
                #         unreachable branch! Someone will have to investigate.
                debug_call('∞.dead_end')
                msg = 'Unreachable! Please file an issue.'
                raise RuntimeError(msg)

            # add parameter to set of parameters in this node and assign it
            node_props.assign_param(name=param_name, value=param_value)
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ PHASE 2 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # Try using default values for parameters with no override. To find
        # which parameters are still missing, we get a tuple of parameter names
        # initialized so far from the node properties object; then we use it
        # to remove parameter names from the set of all annotations.
        missing_params = set(annotations).difference(
            set(node_props.get_params_names())
        )

        for param_name in missing_params:
            if param_name not in defaults:
                # This parameter was not overwritten by the configuration
                # provided to this __init__ method; however, the paramer
                # doesn't have a default, so we need to raise an error.
                msg = (f'parameter "{param_name}" is '
                       f'missing for "{node_props.cls_name}"')
                raise ValueError(msg)

            # We got lucky! We found a default value for this annotated
            # parameter!
            #
            # We first make a copy of the parameter value; we don't want
            # a user to accidentally override a class by modifying an
            # attribute of a config instance!
            param_value = copy.deepcopy(defaults[param_name])

            # Like before, we check if this is a placeholder var; if
            # it is, we need to instantitate it and use it as parameter
            # value so it can be resolved later. We also add it to the
            # registry of all the placeholder variables, which is
            # in the node properties.
            if ConfigPlaceholderVar.contains(param_value):
                param_value = ConfigPlaceholderVar(
                    parent_node=self,
                    param_name=param_name,
                    param_value=param_value,
                    param_config=annotations[param_name]
                )
                node_props.add_var(param_value)

            # add parameter to set of parameters in this node and
            # assign its DEFAULT VALUE
            node_props.assign_param(name=param_name, value=param_value)
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ PHASE 3 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # Last set of assignments! Like we did with annotations, we need to
        # check if there are one or more submodules that have not been
        # initialized already through the config provided by the user.
        missing_subnodes = set(subnodes).difference(
            set(node_props.get_params_names())
        )

        for param_name in missing_subnodes:
            # initialize the subnode here
            param_value = subnodes[param_name](__parent__=self,
                                               __name__=param_name)

            # add the subnode to the config
            node_props.assign_param(name=param_name, value=param_value)
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ PHASE 4 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # Finally, if this is a root class, we want to take care of replacing
        # variables with actual values; not going to do any late binding a la
        # hydra, with some minimal logic to catch cyclical assignments
        if node_props.is_root():
            node_props.apply_vars()
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    def __iter__(self: CN) -> Iterable[Tuple[str, Any]]:
        """Get a iterable of names and parameters in this node,
        including subnodes"""
        yield from ((k, self[k]) for k in
                    ConfigNodeProps.get_props(self).get_params_names())

    def __repr__(self: CN):
        full_name = ConfigNodeProps.get_props(self).long_name
        return (f'<{full_name} config at {hex(id(self))} '
                f'with params {ConfigNodeProps.get_props(self).to_dict()}>')

    def __contains__(self: CN,  key: str) -> bool:
        return key in ConfigNodeProps.get_props(self).get_params_names()

    def __getitem__(self, key: str) -> Any:
        node_props = ConfigNodeProps.get_props(self)
        if key in node_props.get_params_names():
            return getattr(self, key)
        else:
            msg = f'`{key}` is not a parameter in {node_props.long_name}'
            raise KeyError(msg)

    def __len__(self: CN) -> int:
        return sum(1 for _ in self)

    def __rshift__(self: CN, other: CN) -> CN:
        return ConfigNodeProps.get_props(other).update(self)

    def __lshift__(self: CN, other: CN) -> CN:
        return other >> self

    # def __deepcopy__(self: CN, *args, **kwargs) -> CN:
    #     try:
    #         config = ConfigNodeProps.get_props(self).to_dict()
    #         return type(self)(config=config,
    #                         __flex_node__=isinstance(self, ConfigFlexNode),
    #                         __name__=ConfigNodeProps.get_props(self).short_name)
    #     except Exception:
    #         import ipdb
    #         ipdb.set_trace()


@dataclass
class VarMatch:
    path: Sequence[str]
    match: str
    registry: ConfigRegistryReference = field(
        default_factory=ConfigRegistryReference
    )


class ConfigPlaceholderVar(Generic[CV]):
    """A Placeholder for config values that contains a variable.
    Placeholder variables are specified using the following format:

        PLACEHOLDER := ${PATH_TO_VALUE}
        PATH_TO_VALUE := PATH_TO_VALUE.VAR_NAME
        VAR_NAME := [a-zA-Z_]\w+

    PATH_TO_VALUE is used to traverse down the config node
    to find suitable replacement values for the placeholder.
    """

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
        self.param_config_type = (param_config.type if param_config
                                  is not None else lambda x: x)
        self.placeholder_vars = []

        # import here to avoid cycles
        from espresso_config.registry import ConfigRegistry

        for match in re.finditer(CONFIG_PLACEHOLDER_VAR_TEMPLATE, param_value):
            var_path_and_registry = match.group()[2:-1]
            if var_path_and_registry == '':
                # CASE 0: the regex matches even in cases the variable
                #         placeholder is "${}", so we raise an error for
                #         that here.
                msg = (f'Variable placeholder `{match.group()}` in '
                       f'"{param_value}" cannot be parsed.')
                raise ValueError(msg)

            registry = ConfigRegistryReference.from_str(var_path_and_registry)
            self.placeholder_vars.append(
                VarMatch(path=registry.name_as_placeholder_variable(),
                         registry=registry,
                         match=match.group())
            )

    def __repr__(self: CV) -> str:
        return self.__str__()

    def __str__(self: CV) -> str:
        return str(self.unresolved_param_value)

    def resolve(self: CV):
        """Replace variables in this value with their actual value"""

        # we need to start looking from the root
        root_node = ConfigNodeProps.get_props(self.parent_node).get_root()

        replaced_value = self.unresolved_param_value

        while len(self.placeholder_vars) > 0:
            var_match: VarMatch = self.placeholder_vars.pop(0)

            if var_match.path:
                # this reduce function traverses the config from the
                # root node to get to the variable that we want
                # to use for substitution
                placeholder_substitution = functools.reduce(
                    lambda node, key: node[key], var_match.path, root_node
                )
            else:
                # this is a registry reference with no placeholder
                # variable; we set the placeholder substitution to None
                placeholder_substitution = None

            # if the substitution is a full subnode, wee call
            # apply_vars to make sure that all substitutions in
            # the subnode are gracefully handled.
            if isinstance(placeholder_substitution, ConfigNode):
                ConfigNodeProps.get_props(placeholder_substitution).apply_vars()

            # trick of the century: sometimes, by doing variable resolution,
            # we end up with another variable! in that case, we simply
            # tell the parent node with the class to do variable resolution too.
            if isinstance(placeholder_substitution, ConfigPlaceholderVar):
                # asking the parent to apply all its vars!
                ConfigNodeProps.get_props(
                    placeholder_substitution.parent_node).apply_vars()

                # note that even if we apply the substitution,
                # the value inside `placeholder_substitution` placeholder
                # var does not change, so we need to manually fish it out
                placeholder_substitution = getattr(
                    placeholder_substitution.parent_node,
                    placeholder_substitution.param_name
                )

            # we make a copy of the object to avoid unwanted side effects
            placeholder_substitution = copy.deepcopy(placeholder_substitution)

            if var_match.registry.registry_ref:
                # the user has asked for registry reference call, so
                # we oblige. note that we do not pass in any args if
                # there was no placeholder variable
                args = ((placeholder_substitution, ) if
                        var_match.registry.param_name else tuple())
                placeholder_substitution = var_match.registry.resolve(*args)

            if var_match.match == self.unresolved_param_value:
                # the placeholder variable is the entire string, e.g.:
                #   foo: ${bar}
                # we simply set replaced value to it and call it a day
                replaced_value = placeholder_substitution
            else:
                # in this case, the placeholder variable is combined
                # with other variables or strings, e.g.
                #   foo: ${bar}_{$baz}
                # so we replace where appropriate. Note that we cast
                # to string first so that there are no errors when subbing
                placeholder_substitution = str(placeholder_substitution)
                replaced_value = replaced_value.\
                    replace(var_match.match, placeholder_substitution)

        if isinstance(replaced_value, ConfigNode):
            # we need to handle the case of a config node a bit
            # differently, including make sure that the lineage
            # and the parent of the new node are correctly set.
            node_props = ConfigNodeProps.get_props(replaced_value)
            node_props.set_parent(self.parent_node)
            node_props.set_name(self.param_name)
        else:
            # if is not a node, but a simple value, we use the specified
            # type to cast if necessary.
            replaced_value = self.param_config_type(replaced_value)

        # finally done with variable resolution, let's set the
        # parent to this value.
        setattr(self.parent_node, self.param_name, replaced_value)

    @classmethod
    def contains(cls: Type[CV], value: Any) -> bool:
        """Returns True if value has variable (${...})
           somewhere, False otherwise"""
        return (isinstance(value, str) and
                re.findall(CONFIG_PLACEHOLDER_VAR_TEMPLATE, value))


class ConfigFlexNode(ConfigNode):
    """Just like a ConfigNode, except it allows for additional
    parameters other than the ones provided with annotations"""
    def __init__(self: CN,
                 *args: List[Any],
                 __flex_node__: bool = True,
                 **kwargs: Dict[str, Any]) -> None:
        super().__init__(*args, __flex_node__=True, **kwargs)


class DictOfConfigNodes:
    """A special type of node that contains a dictionary of ConfigNodes.
    Useful for when you want to provide a bunch of nodes, but you are
    not sure what the name of keys are. Usage:

    ```python
    from espresso_config import (
        NodeConfig, DictOfConfigNodes, ConfigParam
    )

    class ConfigA(NodeConfig):
        p: ConfigParam(int)

    class RootConfig(NodeConfig):
        dict_of_configs: ConfigParam(DictOfConfigNodes(ConfigA)) = {}

    ```

    and in the corresponding yaml file:

    ```yaml
    dict_of_configs:
        first_config:
            p: 1
        second_config:
            p: 2
        ...
    ```
    """

    class _Wrapper:

        def __new__(cls, config=None, *args, **kwargs):
            parsed = {}

            for k, v in (config or {}).items():
                node = super().__new__(cls)
                node.__init__(v, *args, **kwargs)
                parsed[k] = node

            flex_node_wrapper_cls = type(cls.__name__, (ConfigFlexNode, ), {})
            return flex_node_wrapper_cls(parsed, *args, **kwargs)

    def __new__(cls, node_cls: ConfigFlexNode) -> ConfigFlexNode:
        return type(f'DictOf{node_cls.__name__}',
                    (cls._Wrapper, node_cls), {})

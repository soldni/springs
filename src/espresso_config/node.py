from copy import deepcopy
import functools
import json
import logging
import re
from dataclasses import dataclass, field
from inspect import getmembers, isclass, isroutine
from typing import (
    Any,
    Dict,
    Iterable,
    NamedTuple,
    Optional,
    Sequence,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
    get_type_hints
)
import warnings

from .exceptions import PlaceholderVariableError
from .parser import YamlParser
from .utils import MISSING, hybrid_method, OPTIONAL


# get logger for this file, mostly used for debugging
LOGGER = logging.getLogger(__name__)


# Type declaration for classes
T = TypeVar("T")

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
    default: Any
    type: Type[Any]

    @classmethod
    def from_string(cls: Type['ParameterSpec'],
                    string: str) -> 'ParameterSpec':
        if not re.findall(CONFIG_PARAM_CLI_FORMAT, string):
            msg = f"Cannot parse string '{string}' into a parameter"
            raise ValueError(msg)
        name, default = string.split('=', 1)
        default = YamlParser.load(default)
        return cls(name=name, default=default, type=type(default))

    def to_dict(self: 'ParameterSpec') -> Optional[dict]:
        out_dict = None
        for part in self.name.split('.')[::-1]:
            out_dict = {part: out_dict} if out_dict else {part: self.default}
        return out_dict


T = TypeVar('T')


class ConfigParamMeta(type):
    def __getitem__(cls, *parameters: Type[T]) -> Type[T]:
        return cls(*parameters, __deprecate_warning__=False)


class ConfigParam(metaclass=ConfigParamMeta):
    """Holds type for a config parameter"""

    type: Type

    def __init__(self: 'ConfigParam',
                 target_type: Optional[Type] = None,
                 __deprecate_warning__: bool = True) -> None:
        if __deprecate_warning__:
            msg = ("ConfigParam(type) is deprecated, "
                   "use ConfigParam[type] instead when annotating")
            warnings.warn(msg)

        if target_type is None:
            if not hasattr(self, 'type'):
                raise ValueError("ConfigParam requires a type to be specified")
        else:
            # if no `target_type` is passed, we check if the object has
            # a method `type` which generates a type class at runtime.
            # if not, we raise an error.
            self.type = target_type

    def __repr__(self: 'ConfigParam') -> str:
        type_ = getattr(self, 'type', None)
        return f'{type(self).__name__}({repr(type_)})'

    def __str__(self: 'ConfigParam') -> str:
        type_ = getattr(self, 'type', None)
        return f'{type(self).__name__}({str(type_)})'


class OptionalConfigParam(ConfigParam):
    ...


class ConfigRegistryReference:
    """Extract registry references and resolve them"""
    def __init__(
        self: 'ConfigRegistryReference',
        param_name: Optional[str] = None,
        registry_ref: Optional[str] = None,
        registry_args: Optional[Sequence[Any]] = None
    ):
        self.param_name = param_name
        self.registry_ref = registry_ref
        self.registry_args = registry_args or []

    def name_as_placeholder_variable(
        self: 'ConfigRegistryReference'
    ) -> Optional[Sequence[str]]:
        """Split the name (if provided) to be used
        as the path for placeholder variable"""
        if self.param_name:
            return self.param_name.split('.')
        return None

    @classmethod
    def from_str(cls: Type['ConfigRegistryReference'],
                 string: str) -> 'ConfigRegistryReference':
        """Extract name and parameters of the reference from a string"""

        args = string.split(CONFIG_NODE_REGISTRY_SEPARATOR)
        if len(args) == 1:
            # no reference
            return cls(param_name=args[0])
        else:
            param_name, registry_ref, *args = args
            return cls(param_name=param_name,
                       registry_ref=registry_ref,
                       registry_args=args)

    def resolve_later(self: 'ConfigRegistryReference',
                      *args,
                      **kwargs) -> 'ConfigRegistryReference':
        copy = deepcopy(self)
        copy.resolve = functools.partial(copy.resolve, *args, **kwargs)
        return copy

    def resolve(self: 'ConfigRegistryReference',
                *args,
                node_cls: Optional[Sequence['ConfigNode']] = None,
                **kwargs) -> Any:
        """Resolves and instantiates a reference to a registry object using
        `param_value`. `node_cls` can be a list of ConfigNode objects to
        merge with no override to the registry reference (if the registry
        reference is itself a ConfigNode). `kwargs`, as well as `self.args`
        are passed to the registry reference constructor."""

        if self.registry_ref is None:
            # no-op if there is no registry ref!
            return args[0] if len(args) == 1 else args

        from .registry import ConfigRegistry
        registry_ref = ConfigRegistry.get(self.registry_ref)

        if node_cls:
            if isclass(node_cls) and not issubclass(node_cls, ConfigNode):
                msg = ('The registry reference resolver has receive an object'
                       f'of type {node_cls}, which is not a ConfigNode')
                raise ValueError(msg)

            # we operate slightly differently depending if the registry
            # reference is a config node or not.
            # 1. If yes, we provide defaults from node_cls to potential
            #    make up for some missing parameters in the configuration
            #    passed to this node.
            # 2. If not, it's more free-reign; in fact, we provide
            #    node_cls itself to the registry reference in case
            #    it might be useful.

            if isclass(registry_ref) and issubclass(registry_ref, ConfigNode):
                # getting annotations and subnode for this ConfigNode class,
                # and prepare to pass them to the registry reference
                # constructor as kwargs.
                kwargs.update(ConfigNodeProps.get_defaults(node_cls))
            else:
                kwargs['node_cls'] = node_cls

        return registry_ref(*args, *self.registry_args, **kwargs)

    @classmethod
    def contains(cls, string: str) -> bool:
        return CONFIG_NODE_REGISTRY_SEPARATOR in string


class ConfigNodeProps:
    def __init__(self: 'ConfigNodeProps',
                 node: 'ConfigNode',
                 name: str,
                 parent: Optional['ConfigNode'] = None):
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
    def get_props(cls: Type['ConfigNodeProps'],
                  node: 'ConfigNode') -> 'ConfigNodeProps':
        return getattr(node, CONFIG_NODE_PROPERTIES_NAME)

    def __set_props(self: 'ConfigNodeProps'):
        """Binds this property file to a node."""
        setattr(self.node, CONFIG_NODE_PROPERTIES_NAME, self)

    def set_parent(self: 'ConfigNodeProps',
                   parent_node: Union['ConfigNode', None]):
        # keep track of which is the root node for this config
        self.parent = self.node if parent_node is None else parent_node

    def set_name(self: 'ConfigNodeProps', node_name: Union[str, None]):
        # set the full path to this node as its name
        self.short_name = self.cls_name if node_name is None else node_name
        if self.is_root():
            self.long_name = self.short_name
        else:
            parent_props = self.get_props(self.parent)
            self.long_name = f'{parent_props.long_name}.{self.short_name}'

    @hybrid_method
    def get_annotations(
        cls: Type['ConfigNodeProps'],
        node_cls: Type['ConfigNode'],
        traverse: bool = True
    ) -> Dict[str, ConfigParam]:

        # traverse the inheritance tree if we are asked to; don't
        # otherwise (that is, only return type annotations for this class.)
        raw_annotations = (get_type_hints(node_cls) if traverse else
                           getattr(node_cls, '__annotations__', {}))

        # these are all annotations for parameters for this node; we use
        # them to cast param values to the right type as we parse a config
        annotations = {name: annotation
                       for name, annotation in raw_annotations.items()
                       if isinstance(annotation, ConfigParam)}
        return annotations

    @get_annotations.instance_method
    def get_annotations(
        self: 'ConfigNodeProps',
        traverse: bool = True
    ) -> Dict[str, ConfigParam]:
        return type(self).get_annotations(node_cls=self.node_cls,
                                          traverse=traverse)

    @hybrid_method
    def get_defaults(cls: Type['ConfigNodeProps'],
                     node_cls: Type['ConfigNode']) -> Dict[str, Any]:
        # These are all the default values that have been provided
        # for the parameters for this node.

        # Calling with traverse == True returns all inherited
        # and future type hints.
        all_annotations = cls.get_annotations(node_cls, traverse=True)

        # these are local annotations, i.e. annotations defined in this
        # NodeConfig only.
        local_annotations = cls.get_annotations(node_cls, traverse=False)

        # This is a bit confusing but: sometimes a default
        # is REMOVED when a new ConfigNode is created from a
        # old config node. The use case is sample: you might want
        # to make previously default parameters not default anymore.
        # In that case, if the parameter is part of the
        # local annotations, but not part of the values. (note
        # we can't use hasattr() because that also resolves inheritance,
        # so we use in vars() instead).
        removed_defaults = {param_name for param_name in local_annotations
                            if param_name not in vars(node_cls)}

        # We use getmembers instead of __dict__ because it
        # resolves inheritance (__dict__ does not!)
        all_members = dict(getmembers(node_cls))

        # We are finally ready to compose defaults!
        defaults = {name: all_members[name]
                    for name in all_annotations
                    # has a default value somewhere in the MRO chain...
                    if (name in all_members) and
                    # but it wasn't explicitly removed.
                    (name not in removed_defaults)}

        return defaults

    @get_defaults.instance_method
    def get_defaults(self: 'ConfigNodeProps') -> Dict[str, Any]:
        return type(self).get_defaults(self.node_cls)

    @hybrid_method
    def get_subnodes(cls: Type['ConfigNodeProps'],
                     node_cls: Type['ConfigNode']) -> Dict[str, 'ConfigNode']:
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

    @get_subnodes.instance_method
    def get_subnodes(self: 'ConfigNodeProps') -> Dict[str, 'ConfigNode']:
        return type(self).get_subnodes(self.node_cls)

    @hybrid_method
    def get_all_cls_members(cls: Type['ConfigNodeProps'],
                            node_cls: Type['ConfigNode']) -> Dict[str, Any]:
        all_non_routines = getmembers(node_cls, lambda a: not(isroutine(a)))

        def invalid_name_fn(fn_name: str):
            return ((fn_name.startswith('__') and fn_name.endswith('__'))
                    or fn_name == '_is_protocol')

        members = {name: value for name, value in all_non_routines
                   if not invalid_name_fn(name)}
        return members

    @get_all_cls_members.instance_method
    def get_all_cls_members(self: 'ConfigNodeProps') -> Dict[str, Any]:
        return type(self).get_all_cls_members(self.node_cls)

    @hybrid_method
    def get_all_parameters(
        cls: Type['ConfigNodeProps'],
        node_cls: Type['ConfigNode']
    ) -> Sequence[ParameterSpec]:
        """Get all parameters for this node as well as for its subnodes."""

        all_parameters = []

        annotations = cls.get_annotations(node_cls)
        defaults = cls.get_defaults(node_cls)

        for name, ann in annotations.items():
            default = defaults.get(
                name,
                OPTIONAL if isinstance(ann, OptionalConfigParam) else MISSING
            )
            all_parameters.append(
                ParameterSpec(name=name, type=ann.type, default=default)
            )

        for subnode_name, subnode_cls in cls.get_subnodes(node_cls).items():
            for param_spec in cls.get_all_parameters(subnode_cls):
                all_parameters.append(
                    ParameterSpec(name=f'{subnode_name}.{param_spec.name}',
                                   type=param_spec.type,
                                   default=param_spec.default)
                )
        return all_parameters

    @get_all_parameters.instance_method
    def get_all_parameters(
        self: 'ConfigNodeProps'
    ) -> Sequence[ParameterSpec]:
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

    def get_params_names(self: 'ConfigNodeProps') -> Sequence[str]:
        return tuple(self.param_keys)

    def add_var(self: 'ConfigNodeProps', var: 'ConfigPlaceholderVar'):
        self.config_vars.append(var)

    def pop(self: 'ConfigNodeProps', key: str, default=MISSING) -> Any:
        if key in self.param_keys:
            self.param_keys.remove(key)
            value = getattr(self.node, key)
            delattr(self.node, key)
            return value
        elif default != MISSING:
            return default
        else:
            KeyError(f'`{key}` is not a parameter in {self.long_name}')

    def is_root(self: 'ConfigNodeProps') -> bool:
        return self.parent == self.node

    def get_root(self: 'ConfigNodeProps') -> 'ConfigNode':
        """Traverse the configuration this node is part of to
        find the root node"""
        if self.is_root():
            return self.node
        else:
            return self.get_props(self.parent).get_root()

    def get_children(self: 'ConfigNodeProps',
                     recursive: bool = False) -> Iterable['ConfigNode']:
        """Get a iterable of all the subnodes to this config node"""
        for key, value in sorted(self.node):
            if isinstance(value, ConfigNode):
                yield (key, value)
                if recursive:
                    ch_sub = ConfigNodeProps.get_props(value).get_children()
                    for ch_key, ch_value in ch_sub:
                        yield (f'{key}.{ch_key}', ch_value)

    def apply_vars(self: 'ConfigNodeProps') -> Set[str]:
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

    def to_dict(self: 'ConfigNodeProps') -> Dict[str, Any]:
        return {k: (self.get_props(v).to_dict()
                    if isinstance(v, ConfigNode) else
                    (repr(v) if isinstance(v, ConfigPlaceholderVar) else v))
                for k, v in self.node}

    def to_json(self: 'ConfigNodeProps',
                *args: Sequence[Any],
                **kwargs: Dict[str, Any]) -> str:
        return json.dumps(self.to_dict(), *args, **kwargs)

    def to_yaml(self: 'ConfigNodeProps',
                *args: Sequence[Any],
                **kwargs: Dict[str, Any]) -> str:
        return YamlParser.dump(self.to_dict(), *args, **kwargs)

    def validate_subnodes(self: 'ConfigNodeProps',
                          subnodes_to_validate: Sequence[str]):
        """Check that if specified subnodes are instances of ConfigNode;
        used during pickling/unpickling and copying to make sure nothing
        went bad."""
        for subnode_name in subnodes_to_validate:
            if subnode_name not in self.node:
                msg = (f'Something when wrong; key {subnode_name} '
                       'does not exist in copy')
                raise RuntimeError(msg)

            subnode = self.node[subnode_name]
            if not isinstance(subnode, ConfigNode):
                msg = (f'All subnodes must be instances of {ConfigNode}, '
                       f'not {type(subnode)}.')
                from .registry import ConfigRegistry
                if type(subnode).__name__ in ConfigRegistry:
                    reg_entry = ConfigRegistry.get(type(subnode).__name__)
                    msg += f' Hint: you might want to use {type(reg_entry)}.'
                    raise ValueError(msg)

    @hybrid_method
    def merge_nodes(cls: Type['ConfigNodeProps'],
                    node: 'ConfigNode',
                    other_node: 'ConfigNode',
                    flex: bool = False) -> 'ConfigNode':
        """Create a new node node where values form `node`
        are updated with values from `other_node`."""

        # we are flexible if we are told to be or if any
        # of the nodes classes is.
        flex = (flex or
                isinstance(node, ConfigFlexNode) or
                isinstance(other_node, ConfigFlexNode))

        props = cls.get_props(node)
        other_props = cls.get_props(other_node)

        node_cls = ConfigFlexNode if flex else props.node_cls

        config_values = props.to_dict()
        config_values.update(other_props.to_dict())

        return node_cls(config_values, __flex_node__=flex)

    @merge_nodes.instance_method
    def merge_nodes(self: 'ConfigNodeProps',
                    other_node: 'ConfigNode',
                    flex: bool = False) -> 'ConfigNode':
        return type(self).merge_nodes(node=self.node,
                                      other_node=other_node,
                                      flex=flex)


class ConfigNode:
    """A generic configuration node."""

    def __init__(
        self: 'ConfigNode',
        config: Optional[Union[Dict[str, Any], 'ConfigNode']] = None,
        __parent__: Optional['ConfigNode'] = None,
        __flex_node__: bool = False,
        __name__: Optional[str] = None,
        **kwargs: Dict[str, Any],
    ) -> None:
        # Parsing comes in 5 phases, each one is in a separate code block!

        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ PHASE 0 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # This is mostly preliminaries

        # print info for useful debugging
        LOGGER.debug(f'[PHASE 0.0][CLS {type(self).__name__}]\n'
                     f' config: {config}\n'
                     f'__parent__: {__parent__}\n'
                     f'__flex_node__: {__flex_node__}\n'
                     f'__name__: {__name__}\n'
                     f'**kwargs: {kwargs}\n')

        # Create a property object for this node; the object will bind
        # itself to it
        node_props = ConfigNodeProps(node=self,
                                      name=__name__,
                                      parent=__parent__)

        # get annotations, defaults, and subnodes. Will be used to look up the
        # right types for values, get their default value, and instantiate any
        # subnode to this config node.
        annotations = node_props.get_annotations()
        defaults = node_props.get_defaults()
        subnodes = node_props.get_subnodes()

        # print some debugging info again
        LOGGER.debug(f'[PHASE 0.1][CLS {type(self).__name__}]\n'
                     f'annotations: {annotations}\n'
                     f'defaults: {defaults}\n'
                     f'subnodes: {subnodes}\n')

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

        # any extra keyword argument is used to complement the config
        # NOTE: kwargs never overwrite the config! it's the other way around.
        config = {**(kwargs or {}), **config}
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~ PHASE 1 ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        # Override with options that are provided in `config` dictionary
        for param_name, param_value in config.items():
            # a little function to log how we are doing
            def debug_call(case: str):
                LOGGER.debug(f'[PHASE 1][{node_props.long_name}][{case}]'
                             f'{param_name}')

            if ConfigRegistryReference.contains(param_name):
                # we have a registry reference! we need to extract the
                # reference and get the config from the registry.
                registry_reference = ConfigRegistryReference.\
                    from_str(param_name)
                param_name = registry_reference.param_name
            else:
                registry_reference = None

            # check if it is a valid parameter, if not, raise a KeyError
            is_supported_parameter = (param_name not in annotations and
                                      param_name not in subnodes and
                                      not __flex_node__)
            if is_supported_parameter:
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
                if param_name in subnodes:
                    # CASE 1.S1.1: beside the key with just loaded, we also
                    #              have a subnode with potentially some
                    #              default parameters! fear not, we
                    #              merge configs using operator `>>`
                    debug_call('1.S1.1.registry+submodule')
                    node_cls_to_merge = subnodes[param_name]
                elif (param_name in annotations and
                      issubclass(annotations[param_name].type, ConfigNode)):
                    # CASE 1.S1.2: we also need to merge with the type we also
                    #              get from the parameter annotation. This is
                    #              usually empty, but we merge with it for
                    #              good measure too.
                    debug_call('1.S1.2.registry+annotation')
                    node_cls_to_merge = annotations[param_name].type
                else:
                    node_cls_to_merge = None

                # Finally after a bunch of merging (maybe?), we can instantiate
                # an object using the registry reference!

                if ConfigPlaceholderVar.contains(param_value):
                    # CASE 1.S2.1: The target parameter has a placeholder var
                    #              so we can't quite solve this reference yet
                    #              until the placeholder var is solved.
                    debug_call('1.S2.1.registry+var_in_arg')

                    # we call the resolve method of ConfigRegistryReference,
                    # which allows us to pass some parameters to the
                    # resolve method reference without actually running it.
                    registry_reference = registry_reference.resolve_later(
                        node_cls=node_cls_to_merge,
                        __parent__=self,
                        __name__=param_name
                    )

                    # creating a placeholder node and adding it
                    # to the list of variables for this node. it will
                    # be resolved later.
                    param_value = ConfigPlaceholderVar(
                        parent_node=self,
                        outer_reg_ref=registry_reference,
                        param_name=param_name,
                        param_value=param_value,
                        param_config=annotations.get(param_name, None)
                    )
                    node_props.add_var(param_value)
                else:
                    # CASE 1.S2.2: No variable is sight, so we can just go
                    #              ahead and resolve this parameter value by
                    #              calling the registry reference.
                    debug_call('1.S2.2.registry+novar')
                    param_value = registry_reference.resolve(
                        param_value,
                        node_cls=node_cls_to_merge,
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

                if isclass(param_type) \
                        and issubclass(param_type, ConfigNode):
                    # CASE 3.1: sometimes the type of a parameter is
                    #           ConfigNode or a subclass of it, making
                    #           necessary to pass some extra parameters to
                    #           the constructor instead of just `param_value`.
                    #           We accomplish that with a partial decorator.
                    debug_call('3.1.ann_subnode')

                    # It only makes sense to do this replacement
                    # if the parameter provided is a dict or a ConfigNode,
                    # because those can be parsed by a config node.
                    if isinstance(param_value, (dict, ConfigNode)):
                        debug_call('3.1.1.ann_subnode/is_config')
                        param_type = functools.partial(
                            param_type, __parent__=self, __name__=param_name
                        )
                    else:
                        debug_call('3.1.2.ann_subnode/skip_cast')

                        def param_type(x):
                            return x
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
                    debug_call('3.2.ann_skip_casting')

                    def param_type(x):
                        return x
                else:
                    # this is the case where we cast
                    debug_call('3.3.ann_do_cast')

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
                #         (config_value is already assigned, that's why we
                #         just pass here).
                debug_call('5.unrecognized_but_flexible')
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
        LOGGER.debug(f'[PHASE 2][CLS {type(self).__name__}]')

        # Try using default values for parameters with no override. To find
        # which parameters are still missing, we get a tuple of parameter names
        # initialized so far from the node properties object; then we use it
        # to remove parameter names from the set of all annotations.
        missing_params = set(annotations).\
            difference(set(node_props.get_params_names()))

        for param_name in missing_params:
            # we eval a couple of conditions here on whether we can use
            # this parameter or not
            is_missing_default = param_name not in defaults
            is_optional_default = isinstance(annotations[param_name],
                                             OptionalConfigParam)

            if is_missing_default and is_optional_default:
                msg = (f'[PHASE 2][CLS {type(self).__name__}] '
                       f'Skipping {param_name} because it is '
                       f'annotated as {OptionalConfigParam.__name__}')
                LOGGER.debug(msg)
            elif is_missing_default:
                # This parameter was not overwritten by the configuration
                # provided to this __init__ method; however, the parameter
                # doesn't have a default, so we need to raise an error.
                msg = (f'parameter "{param_name}" is '
                       f'missing for "{node_props.cls_name}"')
                raise ValueError(msg)
            else:
                # We got lucky! We found a default value for this annotated
                # parameter!

                # We first make a copy of the parameter value; we don't want
                # a user to accidentally override a class by modifying an
                # attribute of a config instance!
                param_value = deepcopy(defaults[param_name])

                # Like before, we check if this is a placeholder var; if
                # it is, we need to instantiate it and use it as parameter
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
        LOGGER.debug(f'[PHASE 3][CLS {type(self).__name__}]')

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
        LOGGER.debug(f'[PHASE 4][CLS {type(self).__name__}]')

        # Finally, if this is a root class, we want to take care of replacing
        # variables with actual values; not going to do any late binding a la
        # hydra, with some minimal logic to catch cyclical assignments
        if node_props.is_root():
            node_props.apply_vars()
        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

        LOGGER.debug(f'\n[DONE NODE INIT][CLS {type(self).__name__}]\n')

    def __iter__(self: 'ConfigNode') -> Iterable[Tuple[str, Any]]:
        """Get a iterable of names and parameters in this node,
        including subnodes"""
        yield from ((k, self[k]) for k in
                    ConfigNodeProps.get_props(self).get_params_names())

    def __repr__(self: 'ConfigNode'):
        full_name = ConfigNodeProps.get_props(self).long_name
        return (f'<{full_name} config at {hex(id(self))} '
                f'with params {ConfigNodeProps.get_props(self).to_dict()}>')

    def __contains__(self: 'ConfigNode',  key: str) -> bool:
        # allows to check for nested configs!
        key, *rest = key.split('.')
        rest = '.'.join(rest)

        has_node = key in ConfigNodeProps.get_props(self).get_params_names()
        if rest:
            node = getattr(self, key, None)
            return has_node and isinstance(node, ConfigNode) and rest in node
        else:
            return has_node

    def __getitem__(self, key: str) -> Any:
        node_props = ConfigNodeProps.get_props(self)

        # allows to check for nested configs!
        key, *rest = key.split('.')
        rest = '.'.join(rest)

        if key in node_props.get_params_names():
            value = getattr(self, key)

            if rest:
                # attempt to traverse the tree
                if isinstance(value, ConfigNode):
                    value = value[rest]
                else:
                    msg = f'`{key}` is not a subnode, cannot get `{rest}`'
                    raise KeyError(msg)

            return value
        else:
            msg = f'`{key}` is not a parameter in {node_props.long_name}'
            raise KeyError(msg)

    def __len__(self: 'ConfigNode') -> int:
        return sum(1 for _ in self)

    def __rshift__(self: 'ConfigNode', other: 'ConfigNode') -> 'ConfigNode':
        # other >> self
        return ConfigNodeProps.get_props(other).merge_nodes(self)

    def __lshift__(self: 'ConfigNode', other: 'ConfigNode') -> 'ConfigNode':
        # other << self
        return other >> self


@dataclass
class VarMatch:
    path: Optional[Sequence[str]]
    match: str
    registry: ConfigRegistryReference = field(
        default_factory=ConfigRegistryReference
    )


class ConfigPlaceholderVar:
    """A Placeholder for config values that contains a variable.
    Placeholder variables are specified using the following format:

        PLACEHOLDER := ${PATH_TO_VALUE}
        PATH_TO_VALUE := PATH_TO_VALUE.VAR_NAME
        VAR_NAME := [a-zA-Z_]\\w+

    PATH_TO_VALUE is used to traverse down the config node
    to find suitable replacement values for the placeholder.
    """

    def __init__(
        self: 'ConfigPlaceholderVar',
        parent_node: ConfigNode,
        param_name: str,
        param_value: str,
        outer_reg_ref: Optional[ConfigRegistryReference] = None,
        param_config: Optional[ConfigParam] = None
    ):
        self.param_name = param_name
        self.parent_node = parent_node
        self.unresolved_param_value = param_value
        self.outer_registry_reference = outer_reg_ref
        self.param_config_type = (param_config.type
                                  if param_config is not None
                                  else lambda x: x)
        self.placeholder_vars = []

        for match in re.finditer(CONFIG_PLACEHOLDER_VAR_TEMPLATE,
                                 param_value):
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

    def __repr__(self: 'ConfigPlaceholderVar') -> str:
        return self.__str__()

    def __str__(self: 'ConfigPlaceholderVar') -> str:
        return str(self.unresolved_param_value)

    def resolve(self: 'ConfigPlaceholderVar'):
        """Replace variables in this value with their actual value"""

        # we need to start looking from the root
        root_node = ConfigNodeProps.get_props(self.parent_node).get_root()

        replaced_value = self.unresolved_param_value

        while len(self.placeholder_vars) > 0:
            var_match: VarMatch = self.placeholder_vars.pop(0)

            if var_match.path is not None:
                # this reduce function traverses the config from the
                # root node to get to the variable that we want
                # to use for substitution
                try:
                    placeholder_substitution = functools.reduce(
                        lambda node, key: node[key], var_match.path, root_node
                    )
                except Exception as e:
                    msg = f'Could not resolve ${{{".".join(var_match.path)}}}'
                    raise PlaceholderVariableError(msg) from e
            else:
                # this is a registry reference with no placeholder
                # variable; we set the placeholder substitution to None
                placeholder_substitution = None

            # if the substitution is a full subnode, wee call
            # apply_vars to make sure that all substitutions in
            # the subnode are gracefully handled.
            if isinstance(placeholder_substitution, ConfigNode):
                ConfigNodeProps.get_props(placeholder_substitution)\
                    .apply_vars()

            # trick of the century: sometimes, by doing variable resolution,
            # we end up with another variable! in that case, we simply tell
            # the parent node with the class to do variable resolution too.
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
            placeholder_substitution = deepcopy(placeholder_substitution)

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

        if self.outer_registry_reference:
            # we have been provided an outer_registry_reference, i.e.,
            # a registry that comes from the key part:
            #   key_name@__registry_ref__: ${variable}
            # now that we have resolved the variable, we can finally
            # apply this registry reference before setting the attribute.
            replaced_value = self.outer_registry_reference.resolve(
                replaced_value
            )

        # finally done with variable resolution, let's set the
        # parent to this value.
        setattr(self.parent_node, self.param_name, replaced_value)

    @classmethod
    def contains(cls: Type['ConfigPlaceholderVar'], value: Any) -> bool:
        """Returns True if value has variable (${...})
           somewhere, False otherwise"""
        if isinstance(value, str):
            return len(re.findall(CONFIG_PLACEHOLDER_VAR_TEMPLATE, value)) > 0
        return False


class ConfigFlexNode(ConfigNode):
    """Just like a ConfigNode, except it allows for additional
    parameters other than the ones provided with annotations"""
    def __init__(self: 'ConfigNode',
                 *args,
                 __flex_node__: bool = True,
                 **kwargs) -> None:
        super().__init__(*args, __flex_node__=True, **kwargs)

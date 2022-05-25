# Springs

A set of utilities to turn [OmegaConf](https://omegaconf.readthedocs.io/) into a fully fledge configuration utils.
Just like the springs inside an Omega watch, they help you move with your experiments.

Springs overlaps in functionality with [Hydra](https://hydra.cc/), but without all the unnecessary boilerplate.

## Philosophy

OmegaConf supports creating configurations in all sorts of manners, but we believe that there are benefits into defining configuration from structured objects, namely dataclass.
Springs is built around that notion: write one or more dataclass to compose a configuration (with appropriate defaults), then parse the remainder of options or missing values from command line/a yaml file.

Let's look at an example. Imagine we are building a configuration for a machine learning (ML) experiment, and we want to provide information about model and data to use.
We start by writing the following structure configuration

```python
import springs as sp

@sp.dataclass                   # alias to dataclasses.dataclass
class DataConfig:
    path: str = sp.MISSING      # alias to dataclasses.MISSING
    split: str = 'train'

@sp.dataclass
class ModelConfig:
    name: str = sp.MISSING
    num_labels: int = 2

@sp.dataclass
class ExperimentConfig:
    batch_size: int = 16
    seed: int = 42

@sp.dataclass
class Config:                   # this is our overall config
    data: DataConfig = DataConfig()
    model: ModelConfig = ModelConfig()
    exp: ExperimentConfig = ExperimentConfig()
```

Note how, in matching with OmegaConf syntax, we use `MISSING` to indicate any value that has no default and should be provided at runtime.

If we want to use this configuration with a function that actually runs this experiment, we can use `sp.cli` as follows:

```python
@sp.cli(Config)
def main(config: Config)
    print(config)           # this will print the configuration like a dict
    config.exp.seed         # you can use dot notation to access attributes...
    config['exp']['seed']   # ...or treat it like a dictionary!


if __name__ == '__main__':
    main()

```

Notice how, in the configuration `Config` above, some parameters are missing.
We can specify them from command line...

```bash
python main.py data.path=/path/to/data model.name=bert-base-uncased
```

...or from a YAML config file:

```YAML
data:
    path: /path/to/data

model:
    name: bert-base-uncased

# you can override any part of the config via YAML or CLI
# CLI takes precedence over YAML.
exp:
    seed: 1337

```

To run with from YAML, do:

```bash
python main.py -c config.yaml
```

Easy, right?

### Initializing Object from Configurations

Sometimes a configuration contains all the necessary information to
instantiate an object from it.
Springs supports this use case, and it is as easy as providing a `_target_` node in a configuration:

```python
@sp.dataclass
class ModelConfig:
    _target_: str = \
        'transformers.AutoModelForSequenceClassification.from_pretrained'
    pretrained_model_name_or_path: str = 'bert-base-uncased'
    num_classes: int = 2
```

In your experiment code, run:

```python
def run_model(model_config: ModelConfig):
    ...
    model = sp.init.now(config)
```

if, for some reason, cannot specify the path to a class as a string, you can use `sp.Target.to_string` to resolve a function, class, or method to its path:

```python
import transformers

@sp.dataclass
class ModelConfig:
    _target_: str = sp.Target.to_string(transformers.
                                        AutoModelForSequenceClassification.
                                        from_pretrained)
    pretrained_model_name_or_path: str = 'bert-base-uncased'
    num_classes: int = 2
```

### Resolvers

Guide coming soon!

## Tips and Tricks

This section includes a bunch of tips and tricks for working with OmegaConf and YAML.

### Tip 1: Repeating nodes in YAML input

In setting up YAML configuration files for ML experiments, it is common to
have almost-repeated sections.
In these cases, you can take advantage of YAML's built in variable mechanism and dictionary merging to remove duplicated imports:

```yaml
# &tc assigns an alias to this node
train_config: &tc
  path: /path/to/data
  src_field: full_text
  tgt_field: summary
  split_name: train

test_config:
  # << operator indicates merging,
  # *tc is a reference to the alias above
  << : *tc
  split_name: test
```

This will resolve to:

```yaml
train_config:
  path: /path/to/data
  split_name: train
  src_field: full_text
  tgt_field: summary

test_config:
  path: /path/to/data
  split_name: test
  src_field: full_text
  tgt_field: summary
```

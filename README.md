# Espresso Config

A struct config parser that you can set up in the time it
takes to make an espresso. To install, run

```bash
pip install espresso-config
```

Python 3.8 or newer is required.


## Why Espresso Config?

There are a million of parsers that can turn a YAML configuration / CLI flags into a configuration file, *e.g.*, [Hydra](https://hydra.cc), [ML Collections](https://github.com/google/ml_collections), so why another one? Espresso Config was designed to meet the following requirements:

1. Support structured configs (*i.e.*, define configurations with classes)
2. Allow nested classes in configuration
3. Functions


## Motivating Example

Imagine you want to run the following experiment:

```yaml
backbone: t5-large
model:
  metrics:
    rouge:
      _target_: torchmetrics.functional.text.rouge.rouge_score
  tokenizer:
    _target_: transformers.AutoTokenizer.from_pretrained
    pretrained_model_name_or_path: t5-large
  transformer:
    _target_: transformers.AutoModelForSeq2SeqLM.from_pretrained
    max_sequence_length: 64
    pretrained_model_name_or_path: t5-large
```

Sure, you could parse that yaml file and get a `dict`.
But (a) working with dictionaries is tedious (b) there's no
typing, and (c) you don't want to have to declare all blocks
each time; it would be good if you could save some commonly used
configurations, such as the parameters for one of `transformer`
or `tokenizer` keys.

Espresso Config allows you to solve all off those problems
by specifying a struct class as follows:

```python
from espresso_config import (
    ConfigNode,
    ConfigRegistry,
    ConfigParam,
    ConfigFlexNode
)

@ConfigRegistry.add
class seq2seq(ConfigNode):
    _target_: ConfigParam(str) = 'transformers.AutoModelForSeq2SeqLM.from_pretrained'

@ConfigRegistry.add
class tok(ConfigNode):
    _target_: ConfigParam(str) = 'transformers.AutoTokenizer.from_pretrained'

@ConfigRegistry.add
class rouge(ConfigNode):
    _target_: ConfigParam(str) = 'torchmetrics.functional.text.rouge.rouge_score'

class ApplicationConfig(ConfigNode):
    backbone: ConfigParam(str)
    class model(ConfigNode):
        class transformer(ConfigNode):
            _target_: ConfigParam(str)
            pretrained_model_name_or_path: ConfigParam(str) = '${backbone}'
            max_sequence_length: ConfigParam(int) = 64
        class tokenizer(ConfigNode):
            _target_: ConfigParam(str)
            pretrained_model_name_or_path: ConfigParam(str) = '${backbone}'
        metrics: ConfigParam(ConfigFlexNode) = {}
```

Then, your YAML configuration can be as simple as:

```yaml
backbone: t5-large
model:
  transformer@seq2seq: {}
  tokenizer@tok: {}
  metrics:
    rouge@rouge: {}
```

Voila! To load the config, run:

```python
from espresso_config import config_from_file

config = config_from_file(ApplicationConfig, path_to_yaml)
```

## Placeholder Variable

A placeholder variable is a config value that references another
section of the config, e.g. another value or section.
It uses syntax `${path.to.key}`.


## Registry Reference

A registry reference is a reference to a node config that has been
added to the config registry. It uses syntax `@placeholder_name`.
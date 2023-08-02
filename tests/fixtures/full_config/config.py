from typing import Any, Dict, List, Optional, Union

import springs as sp

PL = "pytorch_lightning"


@sp.dataclass
class SpringsConfig:
    foo: int = 1


@sp.flexyclass
class TargetConfig:
    _target_: str = sp.MISSING


@sp.flexyclass
class LoaderConfig:
    _target_: str = "datasets.load_dataset"
    path: Optional[str] = None
    split: str = sp.MISSING
    task: Optional[str] = None


@sp.flexyclass
class HuggingFaceModuleConfig:
    _target_: str = sp.MISSING
    pretrained_model_name_or_path: str = "${backbone}"


@sp.flexyclass
class MapperConfig:
    _target_: str = sp.MISSING


@sp.dataclass
class DataSplitConfig:
    loader: LoaderConfig = sp.field(default_factory=LoaderConfig)
    mappers: List[MapperConfig] = sp.field(default_factory=list)


@sp.dataclass
class DataConfig:
    _target_: str = "sse.data.DataModule"
    batch_size: int = 1
    num_workers: int = 0
    pin_memory: bool = False
    persistent_workers: bool = False
    collator: TargetConfig = sp.field(default_factory=TargetConfig)
    train_splits_config: List[DataSplitConfig] = sp.field(default_factory=list)
    valid_splits_config: List[DataSplitConfig] = sp.field(default_factory=list)
    test_splits_config: List[DataSplitConfig] = sp.field(default_factory=list)


@sp.dataclass
class EnvironmentConfig:
    root_dir: Optional[str] = "~/plruns"
    run_name: Optional[str] = "sse"
    s3_prefix: Optional[str] = None
    seed: int = 5663


@sp.dataclass
class ModelConfig:
    _target_: str = "sse.models.TokenClassificationModule"
    tokenizer: HuggingFaceModuleConfig = sp.field(
        default_factory=lambda: HuggingFaceModuleConfig(
            _target_="transformers.AutoTokenizer.from_pretrained"
        )
    )
    transformer: HuggingFaceModuleConfig = sp.field(
        default_factory=lambda: HuggingFaceModuleConfig(
            _target_=(
                "transformers."
                "AutoModelForSequenceClassification."
                "from_pretrained"
            )
        )
    )
    val_loss_label: str = "val_loss"
    loss: Optional[TargetConfig] = None
    optimizer: Optional[TargetConfig] = None
    scheduler: Optional[TargetConfig] = None
    transfer: Optional[TargetConfig] = None
    metrics: Dict[str, TargetConfig] = sp.field(default_factory=dict)


@sp.flexyclass
class CheckpointConfig:
    _target_: str = f"{PL}.callbacks.ModelCheckpoint"
    mode: str = "min"
    monitor: str = "${model.val_loss_label}"
    verbose: bool = False


@sp.flexyclass
class GraphicLoggerConfig:
    _target_: str = f"{PL}.loggers.TensorBoardLogger"
    log_graph: bool = False


@sp.flexyclass
class TextLoggerConfig:
    _target_: str = f"{PL}.loggers.CSVLogger"
    name: str = ""
    version: str = ""


@sp.dataclass
class LoggersConfig:
    graphic: GraphicLoggerConfig = sp.field(
        default_factory=GraphicLoggerConfig
    )
    text: TextLoggerConfig = sp.field(default_factory=TextLoggerConfig)


@sp.flexyclass
class EarlyStoppingConfig:
    _target_: str = f"{PL}.callbacks.EarlyStopping"
    check_on_train_epoch_end: bool = False
    min_delta: float = 0
    mode: str = "min"
    monitor: str = "${model.val_loss_label}"
    patience: int = 10
    verbose: bool = False


@sp.flexyclass
class TrainerConfig:
    _target_: str = f"{PL}.Trainer"
    accelerator: str = "auto"
    devices: int = 1
    max_epochs: int = -1
    max_steps: int = -1
    precision: int = 32
    log_every_n_steps: int = 50
    limit_train_batches: Optional[float] = 1.0
    val_check_interval: Union[int, float] = 1
    gradient_clip_val: Optional[float] = None
    strategy: Optional[Dict[str, Any]] = None
    num_sanity_val_steps: int = 2


@sp.dataclass
class SseConfig:
    # base strings to control where models and tokenizers come from
    backbone: Optional[str] = sp.field(
        default=None, help="name of the transformers model to use"
    )
    checkpoint: Optional[str] = None

    env: EnvironmentConfig = sp.field(default_factory=EnvironmentConfig)
    data: DataConfig = sp.field(
        default_factory=DataConfig, help="Data configuration"
    )
    model: ModelConfig = sp.field(default_factory=ModelConfig)
    loggers: LoggersConfig = sp.field(default_factory=LoggersConfig)
    trainer: TrainerConfig = sp.field(default_factory=TrainerConfig)
    checkpointing: Optional[CheckpointConfig] = sp.field(
        default=None, help="optional configurations to deal with checkpointing"
    )
    early_stopping: Optional[EarlyStoppingConfig] = None

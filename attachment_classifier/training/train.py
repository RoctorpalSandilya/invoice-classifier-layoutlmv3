"""Fine-tune LayoutLMv3ForSequenceClassification with HF Trainer.

Receives only a DatasetDict (already encoded) and a Config: no knowledge of sources.
"""
from __future__ import annotations

import inspect
import logging
import math
from typing import Any

import numpy as np
import torch
from datasets import DatasetDict
from sklearn.metrics import accuracy_score, precision_recall_fscore_support
from transformers import (LayoutLMv3ForSequenceClassification, Trainer, TrainingArguments)

from ..config import ID2LABEL, LABEL2ID, LABEL_INVOICE, Config, get_device, set_seed

logger = logging.getLogger(__name__)


def compute_metrics(eval_pred: Any) -> dict[str, float]:
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    p, r, f1, _ = precision_recall_fscore_support(labels, preds, average="binary", pos_label=LABEL_INVOICE,
                                                  zero_division=0)
    return {"accuracy": float(accuracy_score(labels, preds)), "precision": float(p), "recall": float(r),
            "f1": float(f1)}


class WeightedTrainer(Trainer):
    """Trainer with optional class-weighted cross-entropy."""

    def __init__(self, *args: Any, class_weights: torch.Tensor | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.class_weights = class_weights

    def compute_loss(self, model: Any, inputs: dict[str, torch.Tensor], return_outputs: bool = False,
                     num_items_in_batch: int | None = None) -> Any:
        labels = inputs.pop("labels")
        outputs = model(**inputs)
        weight = self.class_weights.to(outputs.logits.device) if self.class_weights is not None else None
        loss = torch.nn.functional.cross_entropy(outputs.logits, labels, weight=weight)
        return (loss, outputs) if return_outputs else loss


def _class_weights(labels: list[int], cfg: Config) -> torch.Tensor | None:
    counts = np.bincount(np.asarray(labels), minlength=2).astype(float)
    if counts.min() == 0:
        logger.warning("A class is missing from the train split; no class weights applied")
        return None
    ratio = counts.max() / counts.min()
    if ratio <= cfg.class_weight_imbalance_ratio:
        logger.info("Classes balanced (ratio %.2f); no class weights", ratio)
        return None
    weights = counts.sum() / (len(counts) * counts)
    logger.info("Class imbalance ratio %.2f -> class weights %s", ratio, weights.round(3).tolist())
    return torch.tensor(weights, dtype=torch.float)


def _freeze_backbone(model: torch.nn.Module) -> None:
    n_train = 0
    for name, p in model.named_parameters():
        p.requires_grad = name.startswith("classifier")
        n_train += p.numel() if p.requires_grad else 0
    logger.info("Backbone frozen; %d trainable parameters (classifier head only)", n_train)


def _training_args(cfg: Config, out_dir: str, device: str, n_train: int) -> TrainingArguments:
    steps_per_epoch = max(1, math.ceil(n_train / cfg.batch_size))
    warmup_steps = int(cfg.warmup_ratio * steps_per_epoch * cfg.epochs)
    kwargs: dict[str, Any] = dict(
        output_dir=out_dir, num_train_epochs=cfg.epochs, learning_rate=cfg.effective_lr,
        per_device_train_batch_size=cfg.batch_size, per_device_eval_batch_size=cfg.batch_size,
        weight_decay=cfg.weight_decay, warmup_steps=warmup_steps, save_strategy="epoch",
        load_best_model_at_end=True, metric_for_best_model="f1", greater_is_better=True,
        save_total_limit=1, seed=cfg.seed, fp16=(device == "cuda"), logging_steps=10,
        remove_unused_columns=False, dataloader_num_workers=cfg.dataloader_workers,
        report_to=[], use_cpu=(device == "cpu"))
    params = inspect.signature(TrainingArguments.__init__).parameters
    kwargs["eval_strategy" if "eval_strategy" in params else "evaluation_strategy"] = "epoch"
    for optional in ("use_cpu",):  # keep compatibility across transformers 4.x / 5.x
        if optional not in params:
            kwargs.pop(optional)
    return TrainingArguments(**kwargs)


def train(dataset_dict: DatasetDict, cfg: Config, out_dir: str) -> tuple[Any, dict[str, Any]]:
    """Train and return (best model, metrics dict). ``out_dir`` holds Trainer checkpoints."""
    set_seed(cfg.seed)
    device = get_device()

    model = LayoutLMv3ForSequenceClassification.from_pretrained(
        cfg.model_name, num_labels=2, id2label=ID2LABEL, label2id=LABEL2ID)
    if cfg.freeze_backbone:
        _freeze_backbone(model)

    train_labels: list[int] = dataset_dict["train"].with_format(None)["label"]
    class_weights = _class_weights(train_labels, cfg)

    trainer = WeightedTrainer(
        model=model, args=_training_args(cfg, out_dir, device, len(train_labels)),
        train_dataset=dataset_dict["train"],
        eval_dataset=dataset_dict["test"], compute_metrics=compute_metrics, class_weights=class_weights)

    logger.info("Starting training: epochs=%d lr=%.2e batch=%d freeze_backbone=%s",
                cfg.epochs, cfg.effective_lr, cfg.batch_size, cfg.freeze_backbone)
    train_result = trainer.train()
    eval_result = trainer.evaluate()

    metrics = {"train": {k: float(v) for k, v in train_result.metrics.items()},
               "test": {k.replace("eval_", ""): float(v) for k, v in eval_result.items()},
               "class_weights": class_weights.tolist() if class_weights is not None else None,
               "device": device}
    logger.info("Final test metrics: %s", metrics["test"])
    return trainer.model, metrics

"""Evaluate a trained model on an encoded test split: metrics, confusion matrix, per-file CSV."""
from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import Any

import numpy as np
import torch
from datasets import Dataset
from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support
from torch.utils.data import DataLoader

from ..config import LABEL_INVOICE, Config, get_device

logger = logging.getLogger(__name__)


@torch.no_grad()
def _predict_probs(model: Any, dataset: Dataset, cfg: Config, device: str) -> np.ndarray:
    model.to(device).eval()
    loader = DataLoader(dataset, batch_size=cfg.batch_size, shuffle=False)
    probs: list[np.ndarray] = []
    for batch in loader:
        batch.pop("labels", None)
        batch = {k: v.to(device) for k, v in batch.items()}
        logits = model(**batch).logits
        probs.append(torch.softmax(logits.float(), dim=-1)[:, LABEL_INVOICE].cpu().numpy())
    return np.concatenate(probs) if probs else np.zeros(0)


def evaluate(model: Any, test_dataset: Dataset, cfg: Config, out_dir: Path | str) -> dict[str, Any]:
    """Return metrics + confusion matrix and write ``test_predictions.csv`` to ``out_dir``."""
    device = get_device()
    raw = test_dataset.with_format(None)
    ids: list[str] = raw["id"]
    filenames: list[str] = raw["filename"]
    labels = np.asarray(raw["label"])

    prob_invoice = _predict_probs(model, test_dataset, cfg, device)
    preds = (prob_invoice >= cfg.threshold).astype(int)

    p, r, f1, _ = precision_recall_fscore_support(labels, preds, average="binary", pos_label=LABEL_INVOICE,
                                                  zero_division=0)
    cm = confusion_matrix(labels, preds, labels=[0, 1])
    metrics: dict[str, Any] = {
        "accuracy": float(accuracy_score(labels, preds)), "precision": float(p), "recall": float(r),
        "f1": float(f1), "threshold": cfg.threshold, "n": int(len(labels)),
        "confusion_matrix": {"labels": ["not_invoice", "invoice"], "rows_true_cols_pred": cm.tolist(),
                             "tn": int(cm[0, 0]), "fp": int(cm[0, 1]), "fn": int(cm[1, 0]), "tp": int(cm[1, 1])}}

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    csv_path = out / "test_predictions.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "filename", "label", "pred", "prob_invoice"])
        for i in range(len(labels)):
            w.writerow([ids[i], filenames[i], int(labels[i]), int(preds[i]), f"{prob_invoice[i]:.6f}"])
    logger.info("Evaluation: P=%.4f R=%.4f F1=%.4f acc=%.4f (n=%d); predictions -> %s",
                p, r, f1, metrics["accuracy"], len(labels), csv_path)
    return metrics

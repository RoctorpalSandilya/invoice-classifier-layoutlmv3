"""Build a train/test DatasetDict from any AttachmentSource.

Extraction runs once per item (with optional on-disk cache). Encoding with the
LayoutLMv3 processor is applied lazily via ``set_transform`` so pixel tensors are
not materialised for the whole corpus at once.
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import torch
from datasets import ClassLabel, Dataset, DatasetDict, Features, Image as HFImage, Sequence, Value
from sklearn.model_selection import train_test_split

from ..config import ID2LABEL, Config
from ..extraction import ExtractionError, FeatureCache, content_key, convert_docx_batch, extract_page
from ..extraction.extract import DOCX_TYPE

logger = logging.getLogger(__name__)

MODEL_KEYS = ("input_ids", "attention_mask", "bbox", "pixel_values")
MANIFEST_COLUMNS = ("id", "filename", "content_type", "label", "split", "has_text_layer", "n_words")


@dataclass
class BuildReport:
    n_total: int = 0
    n_skipped: int = 0
    n_train: int = 0
    n_test: int = 0
    label_counts_train: dict[str, int] = field(default_factory=dict)
    label_counts_test: dict[str, int] = field(default_factory=dict)
    skipped: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        d["skipped"] = self.skipped[:200]  # keep metrics.json bounded
        return d


def make_encoder(processor: Any, cfg: Config) -> Callable[[dict[str, list]], dict[str, torch.Tensor]]:
    """Return a batch transform: raw columns -> model tensors (+ labels)."""

    def encode(batch: dict[str, list]) -> dict[str, torch.Tensor]:
        images = [img.convert("RGB") for img in batch["image"]]
        words = [w if w else [""] for w in batch["words"]]
        boxes = [b if b else [[0, 0, 0, 0]] for b in batch["boxes"]]
        enc = processor(images, words, boxes=boxes, truncation=True, max_length=cfg.max_length,
                        padding="max_length", return_tensors="pt")
        out = {k: enc[k] for k in MODEL_KEYS}
        if "label" in batch:
            out["labels"] = torch.tensor(batch["label"], dtype=torch.long)
        return out

    return encode


def _extract_all(items: Iterable, cfg: Config, report: BuildReport) -> list[dict[str, Any]]:
    cache = FeatureCache(cfg.cache_dir) if cfg.cache_dir is not None else None
    records: list[dict[str, Any]] = []
    for item in items:
        report.n_total += 1
        key = content_key(item.data)
        feats = cache.get(key) if cache else None
        if feats is None:
            try:
                feats = extract_page(item.data, item.content_type, cfg)
            except ExtractionError as exc:
                report.n_skipped += 1
                report.skipped.append({"id": item.id, "filename": item.filename, "reason": str(exc)})
                logger.warning("Skipping %s: %s", item.filename, exc)
                continue
            if cache:
                cache.put(key, feats)
        # With a cache, reference the PNG on disk so page images are decoded lazily per batch
        # rather than all held in memory (1 400 pages at 150 DPI is ~9 GB as PIL images).
        image: Any = str(cache.image_path(key).resolve()) if cache else feats.image
        records.append({"id": item.id, "filename": item.filename, "content_type": item.content_type,
                        "label": int(item.label), "has_text_layer": feats.has_text_layer,
                        "n_words": len(feats.words), "words": feats.words, "boxes": feats.boxes,
                        "image": image})
        if cache:
            feats.image.close()
        if report.n_total % 100 == 0:
            logger.info("Extracted %d items (%d skipped)", report.n_total, report.n_skipped)
    return records


def _to_dataset(records: list[dict[str, Any]], encode: Callable) -> Dataset:
    features = Features({"id": Value("string"), "filename": Value("string"), "words": Sequence(Value("string")),
                         "boxes": Sequence(Sequence(Value("int64"))), "image": HFImage(),
                         "label": ClassLabel(names=[ID2LABEL[0], ID2LABEL[1]])})
    cols = {k: [r[k] for r in records] for k in features}
    ds = Dataset.from_dict(cols, features=features)
    ds.set_transform(encode, columns=["words", "boxes", "image", "label"], output_all_columns=False)
    return ds


def _write_manifest(records: list[dict[str, Any]], split_of: dict[str, str], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "manifest.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_COLUMNS)
        w.writeheader()
        for r in records:
            w.writerow({**{k: r[k] for k in MANIFEST_COLUMNS if k != "split"}, "split": split_of[r["id"]]})
    return path


def build_dataset(source: Any, processor: Any, cfg: Config, out_dir: Path | str) -> tuple[DatasetDict, BuildReport]:
    """Extract, split (stratified), encode lazily, write manifest. Returns (DatasetDict, BuildReport)."""
    report = BuildReport()
    items = list(source.iter_items())
    docx = [it.data for it in items if it.content_type == DOCX_TYPE]
    if docx and cfg.soffice_cmd and cfg.docx_pdf_cache_dir is not None:
        try:
            convert_docx_batch(docx, cfg)  # one soffice launch for all DOCX files
        except ExtractionError as exc:
            logger.warning("Batch DOCX conversion failed (%s); falling back to per-file conversion", exc)
    records = _extract_all(items, cfg, report)
    if len(records) < 2:
        raise RuntimeError(f"Not enough usable items ({len(records)}) to build a dataset")

    labels = [r["label"] for r in records]
    idx = list(range(len(records)))
    train_idx, test_idx = train_test_split(idx, test_size=cfg.test_size, random_state=cfg.seed, stratify=labels)
    train_recs = [records[i] for i in train_idx]
    test_recs = [records[i] for i in test_idx]

    split_of = {r["id"]: "train" for r in train_recs} | {r["id"]: "test" for r in test_recs}
    manifest = _write_manifest(records, split_of, Path(out_dir))
    logger.info("Manifest written to %s", manifest)

    encode = make_encoder(processor, cfg)
    dsd = DatasetDict({"train": _to_dataset(train_recs, encode), "test": _to_dataset(test_recs, encode)})

    report.n_train, report.n_test = len(train_recs), len(test_recs)
    for name, recs, target in (("train", train_recs, report.label_counts_train), ("test", test_recs, report.label_counts_test)):
        for lab in (0, 1):
            target[ID2LABEL[lab]] = sum(1 for r in recs if r["label"] == lab)
        logger.info("%s split: %s", name, target)
    logger.info("Dataset built: %d usable, %d skipped", len(records), report.n_skipped)
    return dsd, report

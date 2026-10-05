"""Command line: train / evaluate / predict."""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Optional

import typer
from transformers import LayoutLMv3Processor

from .config import SUPPORTED_EXTENSIONS, Config

app = typer.Typer(add_completion=False, help="Invoice / not-invoice attachment classifier (LayoutLMv3)")
logger = logging.getLogger("attachment_classifier")


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _build(cfg: Config, source_root: Path, processor: LayoutLMv3Processor, out_dir: Path):
    from .dataset import build_dataset
    from .sources import FileSystemSource  # only the CLI touches sources/

    source = FileSystemSource(source_root, max_items_per_class=cfg.max_items)
    return build_dataset(source, processor, cfg, out_dir)


@app.command()
def train(source_root: Path = typer.Option(Path("./Attachments"), help="Folder containing invoice(s)/ and random/"),
          out: Optional[Path] = typer.Option(None, help="Artifacts dir; default ./artifacts/run_<timestamp>"),
          freeze_backbone: bool = typer.Option(False, help="Train only the classifier head"),
          epochs: int = typer.Option(5), lr: Optional[float] = typer.Option(None),
          batch_size: int = typer.Option(4), max_items: Optional[int] = typer.Option(None, help="Cap per class"),
          no_cache: bool = typer.Option(False, help="Disable the on-disk feature cache"),
          verbose: bool = typer.Option(False)) -> None:
    """Extract, split, fine-tune, evaluate, and write artifacts."""
    _setup_logging(verbose)
    from .training import evaluate, train as run_train

    cfg = Config(source_root=source_root, freeze_backbone=freeze_backbone, epochs=epochs, lr=lr,
                 batch_size=batch_size, max_items=max_items, cache_dir=None if no_cache else Config().cache_dir)
    run_id = time.strftime("run_%Y%m%d_%H%M%S")
    out_dir = out or (cfg.artifacts_root / run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Run %s -> %s", run_id, out_dir)
    logger.info("tesseract=%s soffice=%s", cfg.tesseract_cmd, cfg.soffice_cmd)

    processor = LayoutLMv3Processor.from_pretrained(cfg.model_name, apply_ocr=False)
    dsd, report = _build(cfg, source_root, processor, out_dir)
    model, train_metrics = run_train(dsd, cfg, str(out_dir / "checkpoints"))
    test_metrics = evaluate(model, dsd["test"], cfg, out_dir)

    model_dir = out_dir / "model"
    model.save_pretrained(model_dir)
    processor.save_pretrained(model_dir)

    metrics = {"run_id": run_id, "model_dir": str(model_dir), "config": cfg.to_dict(),
               "dataset": report.to_dict(), "train": train_metrics, "test": test_metrics}
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    typer.echo(f"\nTest set  precision={test_metrics['precision']:.4f}  recall={test_metrics['recall']:.4f}"
               f"  f1={test_metrics['f1']:.4f}  (n={test_metrics['n']}, skipped={report.n_skipped})")
    typer.echo(f"Model saved to: {model_dir.resolve()}")


@app.command()
def evaluate(model_dir: Path = typer.Option(..., help="Directory produced by train (…/model)"),
             source_root: Path = typer.Option(Path("./Attachments")),
             out: Optional[Path] = typer.Option(None, help="Where to write predictions; default <model_dir>/../eval"),
             max_items: Optional[int] = typer.Option(None), verbose: bool = typer.Option(False)) -> None:
    """Rebuild the dataset (same seed -> same split) and evaluate the saved model on the test split."""
    _setup_logging(verbose)
    from transformers import LayoutLMv3ForSequenceClassification

    from .training import evaluate as run_eval

    cfg = Config(source_root=source_root, max_items=max_items)
    out_dir = out or (model_dir.parent / "eval")
    processor = LayoutLMv3Processor.from_pretrained(model_dir, apply_ocr=False)
    dsd, report = _build(cfg, source_root, processor, out_dir)
    model = LayoutLMv3ForSequenceClassification.from_pretrained(model_dir)
    metrics = run_eval(model, dsd["test"], cfg, out_dir)
    metrics["dataset"] = report.to_dict()
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    typer.echo(json.dumps({k: metrics[k] for k in ("precision", "recall", "f1", "accuracy", "n")}, indent=2))


@app.command()
def predict(model_dir: Path = typer.Option(...), file: Path = typer.Option(..., exists=True),
            verbose: bool = typer.Option(False)) -> None:
    """Classify a single file."""
    _setup_logging(verbose)
    from .inference import AttachmentClassifier

    ct = SUPPORTED_EXTENSIONS.get(file.suffix.lower())
    if ct is None:
        raise typer.BadParameter(f"Unsupported extension {file.suffix}; supported: {sorted(SUPPORTED_EXTENSIONS)}")
    clf = AttachmentClassifier(model_dir)
    res = clf.predict(file.read_bytes(), ct)
    typer.echo(json.dumps({"file": str(file), **res.__dict__}, indent=2))


if __name__ == "__main__":
    app()

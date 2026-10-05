"""Interactive demo: paste a file path, get invoice / not-invoice with confidence.

Usage (from the Classification_demo folder):
    python demo.py                              # interactive, newest trained model
    python demo.py --model-dir artifacts/run_frozen_3ep/model
    python demo.py path/to/file.pdf other.jpg   # classify given files and exit

At the prompt you can paste a file path (quotes from "Copy as path" are fine) or a folder
to classify every supported file in it. Type q to quit.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # config paths (caches, LibreOffice profile) are relative to the project folder

os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
warnings.filterwarnings("ignore")
logging.basicConfig(level=logging.ERROR)
for noisy in ("attachment_classifier", "transformers", "pdfplumber", "pdfminer", "PIL"):
    logging.getLogger(noisy).setLevel(logging.ERROR)

os.system("")  # enables ANSI colours in the Windows console
GREEN, RED, YELLOW, DIM, BOLD, RESET = "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[1m", "\033[0m"
WIDTH = 64


def latest_model_dir() -> Path | None:
    runs = [p for p in (ROOT / "artifacts").glob("*/model") if (p / "config.json").is_file()]
    return max(runs, key=lambda p: p.stat().st_mtime) if runs else None


def bar(p: float, width: int = 30) -> str:
    filled = round(p * width)
    return "█" * filled + "░" * (width - filled)


def confidence_label(conf: float) -> str:
    if conf >= 0.95:
        return f"{GREEN}very high{RESET}"
    if conf >= 0.80:
        return f"{GREEN}high{RESET}"
    if conf >= 0.65:
        return f"{YELLOW}moderate{RESET}"
    return f"{RED}low (close to the decision boundary){RESET}"


def classify(path: Path, clf, cfg, extract_page, ExtractionError, content_types) -> None:
    ct = content_types.get(path.suffix.lower())
    print("─" * WIDTH)
    print(f"{BOLD}File:{RESET} {path}")
    if ct is None:
        print(f"{RED}Unsupported file type '{path.suffix}'. Supported: {', '.join(sorted(content_types))}{RESET}")
        return

    data = path.read_bytes()
    t0 = time.perf_counter()
    try:
        feats = extract_page(data, ct, cfg)
    except ExtractionError as exc:
        print(f"{RED}Could not read this file: {exc}{RESET}")
        return
    t1 = time.perf_counter()
    res = clf.predict_features(feats)
    t2 = time.perf_counter()

    p = res.prob_invoice
    conf = p if res.is_invoice else 1 - p
    verdict = f"{GREEN}{BOLD}INVOICE{RESET}" if res.is_invoice else f"{RED}{BOLD}NOT AN INVOICE{RESET}"

    print(f"\n  Result          : {verdict}")
    print(f"  Confidence      : {conf:6.2%}  ({confidence_label(conf)})")
    print(f"  P(invoice)      : {p:6.2%}  {bar(p)}")
    print(f"  P(not invoice)  : {1 - p:6.2%}  {bar(1 - p)}")
    print(f"  Threshold       : {cfg.threshold:.2f}  (invoice if P(invoice) >= threshold)")
    print(f"\n{DIM}  Details{RESET}")
    print(f"  File size       : {len(data) / 1024:,.1f} KB   type: {ct.split('/')[-1][:30]}")
    print(f"  Pages in file   : {feats.page_count}  (only page 1 is classified)")
    source = "embedded text layer" if res.has_text_layer else "OCR (Tesseract)"
    if feats.meta.get("converted_from") == "docx":
        source += ", converted from DOCX"
    print(f"  Text source     : {source}")
    print(f"  Words read      : {res.n_words}  (model sees up to {cfg.max_length} tokens)")
    print(f"  Page image      : {feats.image.width} x {feats.image.height} px")
    print(f"  Time            : read {t1 - t0:.2f}s + model {t2 - t1:.2f}s")
    preview = " ".join(feats.words[:40])
    if preview:
        print(f"  Text preview    : {DIM}{preview[:300]}{'…' if len(feats.words) > 40 else ''}{RESET}")
    print()


def expand(raw: str, content_types: dict) -> list[Path]:
    path = Path(raw.replace("﻿", "").strip().strip('"').strip("'")).expanduser()
    if path.is_dir():
        files = sorted(f for f in path.iterdir() if f.is_file() and f.suffix.lower() in content_types)
        if not files:
            print(f"{YELLOW}No supported files in folder {path}{RESET}")
        return files
    if not path.is_file():
        print(f"{RED}File not found: {path}{RESET}")
        return []
    return [path]


def main() -> None:
    ap = argparse.ArgumentParser(description="Invoice classifier demo")
    ap.add_argument("files", nargs="*", help="files or folders to classify (omit for interactive mode)")
    ap.add_argument("--model-dir", type=Path, default=None, help="trained model folder (default: newest)")
    ap.add_argument("--threshold", type=float, default=None, help="override decision threshold (default 0.5)")
    args = ap.parse_args()

    model_dir = args.model_dir or latest_model_dir()
    if model_dir is None or not (model_dir / "config.json").is_file():
        sys.exit(f"No trained model found. Pass --model-dir or train one first.")

    print(f"{BOLD}Invoice classifier demo{RESET}  (LayoutLMv3)")
    print(f"Loading model from {model_dir} …", flush=True)
    from transformers.utils import logging as hf_logging
    hf_logging.set_verbosity_error()
    hf_logging.disable_progress_bar()
    from attachment_classifier.config import SUPPORTED_EXTENSIONS, Config
    from attachment_classifier.extraction import ExtractionError, extract_page
    from attachment_classifier.inference import AttachmentClassifier

    cfg = Config()
    if args.threshold is not None:
        cfg.threshold = args.threshold
    t0 = time.perf_counter()
    clf = AttachmentClassifier(model_dir, cfg)
    print(f"Model ready in {time.perf_counter() - t0:.1f}s on {clf.device}.\n")

    def run(raw: str) -> None:
        for f in expand(raw, SUPPORTED_EXTENSIONS):
            classify(f, clf, cfg, extract_page, ExtractionError, SUPPORTED_EXTENSIONS)

    if args.files:
        for raw in args.files:
            run(raw)
        return

    print(f"Paste the path of a {', '.join(sorted(SUPPORTED_EXTENSIONS))} file, or a folder. Type q to quit.")
    while True:
        try:
            raw = input(f"{BOLD}path> {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if raw.lower() in {"q", "quit", "exit"}:
            break
        if raw:
            run(raw)


if __name__ == "__main__":
    main()

"""Zero-shot evaluation of Laya on the generated emails.

Usage (from the Classification_demo folder):
    python -m email_classifier.zero_shot_eval                      # all emails, both modes
    python -m email_classifier.zero_shot_eval --limit 20           # quick check, 20 per class
    python -m email_classifier.zero_shot_eval --modes body --questions invoice_ab

Writes predictions.csv and metrics.json to artifacts/laya_zero_shot/<timestamp>/ and prints a
summary table. An email counts as "invoice" when P(invoice) >= --threshold (default 0.5); for
the multi-option doc_type question this is the probability of the "invoice" option.
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from sklearn.metrics import (accuracy_score, confusion_matrix, precision_recall_fscore_support,
                             roc_auc_score)

from .data import EmailItem, load_emails
from .laya_backend import DEFAULT_LAYA_DIR, QUESTIONS, LayaZeroShot

logger = logging.getLogger("email_classifier.zero_shot_eval")
MODES = ("body", "header_body")


def metrics_for(labels: np.ndarray, probs: np.ndarray, threshold: float) -> dict:
    preds = (probs >= threshold).astype(int)
    p, r, f1, _ = precision_recall_fscore_support(labels, preds, average="binary", pos_label=1, zero_division=0)
    tn, fp, fn, tp = confusion_matrix(labels, preds, labels=[0, 1]).ravel()
    auc = float(roc_auc_score(labels, probs)) if len(set(labels.tolist())) == 2 else float("nan")
    return {"accuracy": float(accuracy_score(labels, preds)), "precision": float(p), "recall": float(r),
            "f1": float(f1), "auroc": auc, "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
            "n": int(len(labels)), "mean_p_invoice_pos": float(probs[labels == 1].mean()) if (labels == 1).any() else None,
            "mean_p_invoice_neg": float(probs[labels == 0].mean()) if (labels == 0).any() else None}


def subgroup_accuracy(emails: list[EmailItem], probs: np.ndarray, threshold: float) -> dict[str, dict]:
    groups: dict[str, list[bool]] = defaultdict(list)
    for e, p in zip(emails, probs):
        groups[e.subgroup].append(int(p >= threshold) == e.label)
    return {g: {"n": len(v), "accuracy": round(float(np.mean(v)), 4)} for g, v in sorted(groups.items())}


def main() -> None:
    ap = argparse.ArgumentParser(description="Zero-shot Laya evaluation on generated emails")
    ap.add_argument("--email-root", type=Path, default=Path("Email"))
    ap.add_argument("--laya-dir", type=Path, default=DEFAULT_LAYA_DIR)
    ap.add_argument("--modes", nargs="+", choices=MODES, default=list(MODES))
    ap.add_argument("--questions", nargs="+", choices=list(QUESTIONS), default=list(QUESTIONS))
    ap.add_argument("--limit", type=int, default=None, help="emails per class (default: all)")
    ap.add_argument("--threshold", type=float, default=0.5)
    ap.add_argument("--include-attachment-name", action="store_true",
                    help="add X-Attachment-Name to the header state (leaks the label in this generated data)")
    ap.add_argument("--no-clean", action="store_true", help="do not strip signatures/disclaimers from bodies")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    emails = load_emails(args.email_root, args.limit)
    labels = np.array([e.label for e in emails])
    out_dir = args.out or Path("artifacts") / "laya_zero_shot" / time.strftime("run_%Y%m%d_%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    model = LayaZeroShot(args.laya_dir, question_ids=args.questions, clean_body=not args.no_clean,
                         include_attachment_name=args.include_attachment_name)
    probs = {(m, q): np.zeros(len(emails)) for m in args.modes for q in args.questions}
    answers = {(m, q): [""] * len(emails) for m in args.modes for q in args.questions}

    t0 = time.time()
    total = len(emails) * len(args.modes)
    done = 0
    for mode in args.modes:
        for i, email in enumerate(emails):
            res = model.predict(email, mode)
            for q in args.questions:
                probs[(mode, q)][i] = res[q]["p_invoice"]
                answers[(mode, q)][i] = res[q]["answer"]
            done += 1
            if done % 50 == 0 or done == total:
                el = time.time() - t0
                logger.info("%d/%d emails scored (%.2fs/email, ETA %.0f min)", done, total, el / done,
                            el / done * (total - done) / 60)

    results: dict[str, dict] = {}
    for (mode, q), p in probs.items():
        key = f"{mode}/{q}"
        results[key] = metrics_for(labels, p, args.threshold)
        results[key]["by_subgroup"] = subgroup_accuracy(emails, p, args.threshold)

    with (out_dir / "predictions.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        cols = [f"{m}/{q}" for m in args.modes for q in args.questions]
        w.writerow(["name", "label", "subgroup"] + [f"{c}:p_invoice" for c in cols] + [f"{c}:answer" for c in cols])
        for i, e in enumerate(emails):
            w.writerow([e.name, e.label, e.subgroup]
                       + [f"{probs[(m, q)][i]:.4f}" for m in args.modes for q in args.questions]
                       + [answers[(m, q)][i] for m in args.modes for q in args.questions])
    meta = {"model": "convaiinnovations/laya (English, ModernBERT-large)", "laya_dir": str(args.laya_dir),
            "n_emails": len(emails), "n_invoice": int(labels.sum()), "n_not_invoice": int((labels == 0).sum()),
            "threshold": args.threshold, "clean_body": not args.no_clean,
            "include_attachment_name": args.include_attachment_name, "questions": {q: QUESTIONS[q] for q in args.questions},
            "seconds": round(time.time() - t0, 1), "results": results}
    (out_dir / "metrics.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"\nZero-shot Laya, {len(emails)} emails ({int(labels.sum())} invoice / {int((labels == 0).sum())} not), "
          f"threshold {args.threshold}")
    print(f"{'mode/question':<28}{'acc':>7}{'prec':>7}{'rec':>7}{'f1':>7}{'auroc':>7}   tn  fp  fn  tp")
    for key, r in results.items():
        print(f"{key:<28}{r['accuracy']:7.3f}{r['precision']:7.3f}{r['recall']:7.3f}{r['f1']:7.3f}{r['auroc']:7.3f}"
              f"  {r['tn']:4d}{r['fp']:4d}{r['fn']:4d}{r['tp']:4d}")
    print(f"\nPredictions and metrics written to {out_dir.resolve()}")


if __name__ == "__main__":
    main()

"""Load the generated emails: Email/Header/<label>/<name>.txt + Email/Body/<label>/<name>.txt.

Header and body files share a name with the attachment they describe, so ``name`` also
identifies the attachment (e.g. ``receipt_001`` or ``lookalike_payslip_045``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

LABEL_DIRS = {"invoice": 1, "random": 0}


@dataclass
class EmailItem:
    name: str               # shared stem of header/body/attachment files
    label: int              # 1 = invoice email, 0 = not
    headers: dict[str, str]
    body: str

    @property
    def subgroup(self) -> str:
        """Finer category for error analysis: invoice, receipt, doc, or lookalike_<type>."""
        if self.label == 1:
            return "invoice"
        parts = self.name.split("_")
        if parts[0] == "lookalike" and len(parts) > 2:
            return "lookalike_" + "_".join(parts[1:-1])
        return parts[0]


def parse_headers(text: str) -> dict[str, str]:
    """Parse 'Key: value' lines (continuation lines start with whitespace)."""
    headers: dict[str, str] = {}
    last: str | None = None
    for line in text.splitlines():
        if line[:1] in (" ", "\t") and last:
            headers[last] += " " + line.strip()
            continue
        key, sep, value = line.partition(":")
        if sep and key.strip():
            last = key.strip()
            headers[last] = value.strip()
    return headers


def load_emails(email_root: Path | str, limit_per_class: int | None = None) -> list[EmailItem]:
    root = Path(email_root)
    items: list[EmailItem] = []
    for label_dir, label in LABEL_DIRS.items():
        hdir, bdir = root / "Header" / label_dir, root / "Body" / label_dir
        names = sorted(p.stem for p in hdir.glob("*.txt"))
        if limit_per_class is not None:
            names = names[:limit_per_class]
        missing = 0
        for name in names:
            body_path = bdir / f"{name}.txt"
            if not body_path.is_file():
                missing += 1
                continue
            items.append(EmailItem(name=name, label=label,
                                   headers=parse_headers((hdir / f"{name}.txt").read_text(encoding="utf-8")),
                                   body=body_path.read_text(encoding="utf-8")))
        logger.info("%s: %d emails loaded (%d without a body file)", label_dir, len(names) - missing, missing)
    return items

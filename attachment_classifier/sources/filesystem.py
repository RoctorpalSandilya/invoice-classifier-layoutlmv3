"""Filesystem source: walks <root>/invoice(s)/ and <root>/random/ and infers the label
from the immediate sub-folder name."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from ..config import FOLDER_LABELS, SUPPORTED_EXTENSIONS
from .base import AttachmentItem, AttachmentSource

logger = logging.getLogger(__name__)


class FileSystemSource(AttachmentSource):
    def __init__(self, root: Path | str, max_items_per_class: int | None = None) -> None:
        self.root = Path(root)
        self.max_items_per_class = max_items_per_class
        if not self.root.is_dir():
            raise FileNotFoundError(f"Source root does not exist: {self.root}")

    def _class_dirs(self) -> list[tuple[Path, int]]:
        dirs: list[tuple[Path, int]] = []
        for child in sorted(self.root.iterdir()):
            if child.is_dir() and child.name.lower() in FOLDER_LABELS:
                dirs.append((child, FOLDER_LABELS[child.name.lower()]))
        if not dirs:
            raise FileNotFoundError(
                f"No class folders found under {self.root}; expected one of {sorted(FOLDER_LABELS)}")
        return dirs

    def iter_items(self) -> Iterable[AttachmentItem]:
        for class_dir, label in self._class_dirs():
            count = 0
            for path in sorted(class_dir.rglob("*")):
                if not path.is_file():
                    continue
                ext = path.suffix.lower()
                if ext not in SUPPORTED_EXTENSIONS:
                    logger.debug("Skipping unsupported file %s", path)
                    continue
                if self.max_items_per_class is not None and count >= self.max_items_per_class:
                    break
                count += 1
                yield AttachmentItem(
                    id=str(path.relative_to(self.root)).replace("\\", "/"),
                    filename=path.name,
                    content_type=SUPPORTED_EXTENSIONS[ext],
                    data=path.read_bytes(),
                    label=label,
                )
            logger.info("Folder %s -> label %d: %d files", class_dir.name, label, count)

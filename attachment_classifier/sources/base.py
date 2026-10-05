"""Abstract data source. Training/inference never import from this package; they only
receive AttachmentItem objects (or raw bytes), which keeps the source swappable."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable


@dataclass
class AttachmentItem:
    id: str
    filename: str
    content_type: str
    data: bytes
    label: int | None  # 1 = invoice, 0 = not invoice, None = unlabelled


class AttachmentSource(ABC):
    """Yields attachments from some backing store."""

    @abstractmethod
    def iter_items(self) -> Iterable[AttachmentItem]:
        """Iterate over every attachment, loading its bytes lazily per item."""
        raise NotImplementedError

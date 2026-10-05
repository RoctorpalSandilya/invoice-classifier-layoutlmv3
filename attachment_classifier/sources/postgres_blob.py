"""STUB: future production source backed by Postgres metadata + Azure Blob bytes."""
from __future__ import annotations

from typing import Iterable

from .base import AttachmentItem, AttachmentSource


class PostgresBlobSource(AttachmentSource):
    """Reads attachment rows from Postgres and the file bytes from Azure Blob Storage.

    Intended behaviour (not implemented yet):
      * Query a Postgres table (e.g. ``attachments``) for rows with at least
        ``id``, ``filename``, ``content_type``, ``storage_path`` and optionally ``label``.
      * For each row, download the blob at ``storage_path`` from the configured Azure
        Blob container (``azure.storage.blob.BlobServiceClient``) and yield an
        :class:`AttachmentItem` with those bytes.
      * Connection strings / container name are passed to ``__init__`` or read from
        environment variables; nothing else in the pipeline needs to change because
        training and inference only ever see ``AttachmentItem`` / raw bytes.
    """

    def __init__(self, postgres_dsn: str, blob_connection_string: str, container: str,
                 query: str | None = None) -> None:
        self.postgres_dsn = postgres_dsn
        self.blob_connection_string = blob_connection_string
        self.container = container
        self.query = query

    def iter_items(self) -> Iterable[AttachmentItem]:
        # TODO: implement Postgres row iteration + Azure Blob download.
        raise NotImplementedError("PostgresBlobSource is a stub; see class docstring.")

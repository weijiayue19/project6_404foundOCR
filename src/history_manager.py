"""OCR history management based on a binary search tree.

This module only manages OCR history data. It does not call PaddleOCR and does
not perform image preprocessing. A BST is used so records can be kept ordered by
recognition time while still supporting clear insert and time-range search
logic for class presentation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class OCRHistoryRecord:
    """A single OCR history record.

    ``created_time`` is stored as an ISO formatted string such as
    ``2026-07-07T16:30:00``. ISO timestamps sort lexicographically in the same
    order as time, so they are suitable as the primary BST key.
    """

    record_id: str
    image_path: str
    recognized_text: str
    created_time: str
    file_size: int
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert the record to a JSON-serializable dictionary."""

        return {
            "record_id": self.record_id,
            "image_path": self.image_path,
            "recognized_text": self.recognized_text,
            "created_time": self.created_time,
            "file_size": self.file_size,
            "extra": dict(self.extra),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "OCRHistoryRecord":
        """Build a record from JSON data.

        A clear ``ValueError`` is raised when required fields are missing or the
        JSON object is not shaped like an OCR history record.
        """

        if not isinstance(data, dict):
            raise ValueError("History record must be a JSON object.")

        required_fields = {
            "record_id",
            "image_path",
            "recognized_text",
            "created_time",
            "file_size",
        }
        missing = sorted(required_fields - set(data))
        if missing:
            raise ValueError(f"History record is missing required fields: {', '.join(missing)}")

        extra = data.get("extra", {})
        if extra is None:
            extra = {}
        if not isinstance(extra, dict):
            raise ValueError("History record field 'extra' must be a dictionary.")

        try:
            file_size = int(data["file_size"])
        except (TypeError, ValueError) as exc:
            raise ValueError("History record field 'file_size' must be an integer.") from exc

        return OCRHistoryRecord(
            record_id=str(data["record_id"]),
            image_path=str(data["image_path"]),
            recognized_text=str(data["recognized_text"]),
            created_time=str(data["created_time"]),
            file_size=file_size,
            extra=dict(extra),
        )


@dataclass(slots=True)
class BSTNode:
    """A BST node indexed by ``(created_time, record_id)``.

    ``created_time`` is the main key. ``record_id`` is appended to the key so
    records created at the exact same second do not overwrite each other.
    """

    key: tuple[str, str]
    record: OCRHistoryRecord
    left: "BSTNode | None" = None
    right: "BSTNode | None" = None


class HistoryBST:
    """Manage OCR history records with a binary search tree.

    The BST insertion rule is simple: smaller keys go left, larger keys go
    right. Because the key starts with ``created_time``, an inorder traversal
    visits the left subtree, current node, and right subtree in chronological
    order. Time range search uses this same ordering to skip subtrees that
    cannot contain matching records.
    """

    def __init__(self) -> None:
        self.root: BSTNode | None = None
        self._size = 0

    def insert(self, record: OCRHistoryRecord) -> None:
        """Insert one OCR history record ordered by time, then record id."""

        key = self._make_key(record)
        if self.root is None:
            self.root = BSTNode(key=key, record=record)
            self._size = 1
            return

        inserted = self._insert_node(self.root, key, record)
        if inserted:
            self._size += 1

    def inorder_traversal(self) -> list[OCRHistoryRecord]:
        """Return all records sorted from earliest to latest time."""

        records: list[OCRHistoryRecord] = []
        self._inorder(self.root, records)
        return records

    def search_by_time(self, target_time: str) -> list[OCRHistoryRecord]:
        """Return records whose ``created_time`` exactly equals target_time."""

        matches: list[OCRHistoryRecord] = []
        self._search_by_time(self.root, target_time, matches)
        return matches

    def range_search_by_time(self, start_time: str, end_time: str) -> list[OCRHistoryRecord]:
        """Return records created within ``[start_time, end_time]``.

        BST pruning: when the current node time is earlier than ``start_time``,
        the whole left subtree is too early and can be skipped. When it is later
        than ``end_time``, the whole right subtree is too late and can be
        skipped.
        """

        if start_time > end_time:
            raise ValueError("start_time must be less than or equal to end_time.")

        matches: list[OCRHistoryRecord] = []
        self._range_search(self.root, start_time, end_time, matches)
        return matches

    def search_by_keyword(self, keyword: str) -> list[OCRHistoryRecord]:
        """Search recognized text by keyword, ignoring case."""

        keyword_lower = keyword.lower()
        return [
            record
            for record in self.inorder_traversal()
            if keyword_lower in record.recognized_text.lower()
        ]

    def search_by_image_path(self, image_path: str) -> list[OCRHistoryRecord]:
        """Return records for an exact image path."""

        return [
            record
            for record in self.inorder_traversal()
            if record.image_path == image_path
        ]

    def delete_by_record_id(self, record_id: str) -> bool:
        """Delete a record by id and rebuild the BST.

        Direct BST deletion has several structural cases. For this project the
        clearer approach is to export records with inorder traversal, remove the
        target id, and rebuild the tree by BST insertion. The resulting tree
        remains valid and easy to explain.
        """

        records = self.inorder_traversal()
        remaining = [record for record in records if record.record_id != record_id]
        if len(remaining) == len(records):
            return False

        self.clear()
        for record in remaining:
            self.insert(record)
        return True

    def clear(self) -> None:
        """Remove all records."""

        self.root = None
        self._size = 0

    def size(self) -> int:
        """Return the number of records currently stored."""

        return self._size

    def _insert_node(
        self,
        node: BSTNode,
        key: tuple[str, str],
        record: OCRHistoryRecord,
    ) -> bool:
        if key < node.key:
            if node.left is None:
                node.left = BSTNode(key=key, record=record)
                return True
            return self._insert_node(node.left, key, record)

        if key > node.key:
            if node.right is None:
                node.right = BSTNode(key=key, record=record)
                return True
            return self._insert_node(node.right, key, record)

        node.record = record
        return False

    def _inorder(self, node: BSTNode | None, records: list[OCRHistoryRecord]) -> None:
        if node is None:
            return
        self._inorder(node.left, records)
        records.append(node.record)
        self._inorder(node.right, records)

    def _search_by_time(
        self,
        node: BSTNode | None,
        target_time: str,
        matches: list[OCRHistoryRecord],
    ) -> None:
        if node is None:
            return

        node_time = node.record.created_time
        if target_time < node_time:
            self._search_by_time(node.left, target_time, matches)
        elif target_time > node_time:
            self._search_by_time(node.right, target_time, matches)
        else:
            self._search_by_time(node.left, target_time, matches)
            matches.append(node.record)
            self._search_by_time(node.right, target_time, matches)

    def _range_search(
        self,
        node: BSTNode | None,
        start_time: str,
        end_time: str,
        matches: list[OCRHistoryRecord],
    ) -> None:
        if node is None:
            return

        node_time = node.record.created_time
        if start_time <= node_time:
            self._range_search(node.left, start_time, end_time, matches)
        if start_time <= node_time <= end_time:
            matches.append(node.record)
        if node_time <= end_time:
            self._range_search(node.right, start_time, end_time, matches)

    @staticmethod
    def _make_key(record: OCRHistoryRecord) -> tuple[str, str]:
        return (record.created_time, record.record_id)


def create_history_record(
    image_path: str,
    recognized_text: str,
    file_size: int | None = None,
    extra: dict[str, Any] | None = None,
) -> OCRHistoryRecord:
    """Create an OCR history record with automatic id, time, and file size."""

    if file_size is None:
        try:
            file_size = Path(image_path).stat().st_size
        except OSError:
            # The OCR result may be created from a temporary or moved image; in
            # that case no file size can be read, so 0 is stored explicitly.
            file_size = 0

    return OCRHistoryRecord(
        record_id=str(uuid.uuid4()),
        image_path=image_path,
        recognized_text=recognized_text,
        created_time=datetime.now().replace(microsecond=0).isoformat(),
        file_size=file_size,
        extra=dict(extra or {}),
    )


@dataclass(slots=True)
class HistoryEntry:
    """Compatibility record used by the existing GUI wrapper."""

    entry_id: int
    image_path: str
    text: str
    created_at: float
    region: tuple[int, int, int, int] | None = None
    preprocess_summary: str = ""
    elapsed_seconds: float = 0.0


class HistoryManager:
    """Compatibility wrapper around ``HistoryBST`` for existing GUI code."""

    def __init__(self) -> None:
        self._tree = HistoryBST()
        self._next_id = 1

    def add_entry(
        self,
        image_path: str | Path,
        text: str,
        region: tuple[int, int, int, int] | None = None,
        preprocess_summary: str = "",
        elapsed_seconds: float = 0.0,
    ) -> HistoryEntry:
        """Add a GUI history entry while storing it in the BST backend."""

        entry_id = self._next_id
        self._next_id += 1
        created_time = datetime.now().replace(microsecond=0).isoformat()
        record = create_history_record(
            image_path=str(image_path),
            recognized_text=text,
            extra={
                "entry_id": entry_id,
                "created_at": datetime.fromisoformat(created_time).timestamp(),
                "region": region,
                "preprocess_summary": preprocess_summary,
                "elapsed_seconds": elapsed_seconds,
            },
        )
        record.record_id = str(entry_id)
        record.created_time = created_time
        self._tree.insert(record)
        return self._record_to_entry(record)

    def get_entry(self, entry_id: int) -> HistoryEntry | None:
        """Find a GUI history entry by its integer id."""

        record_id = str(entry_id)
        for record in self._tree.inorder_traversal():
            if record.record_id == record_id or record.extra.get("entry_id") == entry_id:
                return self._record_to_entry(record)
        return None

    def list_entries(self) -> list[HistoryEntry]:
        """List GUI history entries in chronological order."""

        return [self._record_to_entry(record) for record in self._tree.inorder_traversal()]

    def clear(self) -> None:
        """Clear all GUI history entries."""

        self._tree.clear()
        self._next_id = 1

    def _record_to_entry(self, record: OCRHistoryRecord) -> HistoryEntry:
        entry_id = self._entry_id_from_record(record)
        created_at = record.extra.get("created_at")
        if not isinstance(created_at, (int, float)):
            created_at = datetime.fromisoformat(record.created_time).timestamp()

        region = record.extra.get("region")
        if region is not None:
            region = tuple(region)

        return HistoryEntry(
            entry_id=entry_id,
            image_path=record.image_path,
            text=record.recognized_text,
            created_at=float(created_at),
            region=region,
            preprocess_summary=str(record.extra.get("preprocess_summary", "")),
            elapsed_seconds=float(record.extra.get("elapsed_seconds", 0.0)),
        )

    @staticmethod
    def _entry_id_from_record(record: OCRHistoryRecord) -> int:
        extra_id = record.extra.get("entry_id")
        if isinstance(extra_id, int):
            return extra_id
        try:
            return int(record.record_id)
        except ValueError:
            return 0

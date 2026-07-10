"""SQLite repository for OCR recognition records."""

from __future__ import annotations

import sqlite3
from typing import Any


class OcrRecordRepository:
    """Persist and query OCR records through SQLite only."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def insert(self, record: dict[str, Any]) -> dict[str, Any]:
        """Insert one OCR record and return the normalized dictionary."""

        normalized = self._normalize_record(record)
        self.connection.execute(
            """
            INSERT INTO ocr_records (
                record_id,
                original_image_path,
                saved_image_path,
                image_name,
                image_width,
                image_height,
                preview_image,
                recognized_text,
                layout_text,
                ocr_blocks,
                recognition_mode,
                upload_type,
                edited_text,
                created_time,
                file_size,
                image_hash,
                region,
                preprocess_summary,
                elapsed_seconds,
                image_transform
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                normalized["record_id"],
                normalized["original_image_path"],
                normalized["saved_image_path"],
                normalized["image_name"],
                normalized["image_width"],
                normalized["image_height"],
                normalized.get("preview_image"),
                normalized["recognized_text"],
                normalized["layout_text"],
                normalized["ocr_blocks"],
                normalized["recognition_mode"],
                normalized["upload_type"],
                normalized["edited_text"],
                normalized["created_time"],
                normalized["file_size"],
                normalized["image_hash"],
                normalized.get("region"),
                normalized["preprocess_summary"],
                normalized["elapsed_seconds"],
                normalized["image_transform"],
            ),
        )
        self.connection.commit()
        return normalized

    def list_all(self) -> list[dict[str, Any]]:
        return self.query_records(ascending=True)

    def search(self, keyword: str) -> list[dict[str, Any]]:
        """Return records whose recognized text contains keyword, case-insensitive."""

        return self.query_records(keyword=keyword, ascending=True)

    def query_records(
        self,
        *,
        keyword: str = "",
        recognition_mode: str | None = None,
        upload_type: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        ascending: bool = True,
    ) -> list[dict[str, Any]]:
        """Return records matching optional text, mode, type, and created-time filters."""

        clauses: list[str] = []
        params: list[Any] = []
        keyword = keyword.strip()
        if keyword:
            clauses.append("lower(recognized_text) LIKE ? ESCAPE '\\'")
            params.append(f"%{self._escape_like(keyword.lower())}%")
        if recognition_mode:
            clauses.append("recognition_mode = ?")
            params.append(recognition_mode)
        if upload_type:
            clauses.append("upload_type = ?")
            params.append(upload_type)
        if start_time:
            clauses.append("created_time >= ?")
            params.append(start_time)
        if end_time:
            clauses.append("created_time <= ?")
            params.append(end_time)

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        direction = "ASC" if ascending else "DESC"
        rows = self.connection.execute(
            f"""
            SELECT *
            FROM ocr_records
            {where_sql}
            ORDER BY created_time {direction}, record_id {direction}
            """,
            tuple(params),
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_by_id(self, record_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT *
            FROM ocr_records
            WHERE record_id = ?
            """,
            (record_id,),
        ).fetchone()
        return self._row_to_dict(row) if row is not None else None

    def delete_all(self) -> None:
        self.connection.execute("DELETE FROM ocr_records")
        self.connection.commit()

    def delete_by_ids(self, record_ids: list[str]) -> int:
        ids = [str(record_id).strip() for record_id in record_ids if str(record_id).strip()]
        if not ids:
            return 0
        placeholders = ",".join("?" for _ in ids)
        cursor = self.connection.execute(
            f"DELETE FROM ocr_records WHERE record_id IN ({placeholders})",
            tuple(ids),
        )
        self.connection.commit()
        return int(cursor.rowcount if cursor.rowcount is not None else 0)

    def update_edited_text(self, record_id: str, edited_text: str) -> None:
        self.connection.execute(
            """
            UPDATE ocr_records
            SET edited_text = ?
            WHERE record_id = ?
            """,
            (edited_text, record_id),
        )
        self.connection.commit()

    @staticmethod
    def _normalize_record(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "record_id": str(record["record_id"]),
            "original_image_path": str(record["original_image_path"]),
            "saved_image_path": str(record.get("saved_image_path") or record["original_image_path"]),
            "image_name": str(record.get("image_name", "")),
            "image_width": int(record.get("image_width", 0)),
            "image_height": int(record.get("image_height", 0)),
            "preview_image": record.get("preview_image"),
            "recognized_text": str(record.get("recognized_text", "")),
            "layout_text": str(record.get("layout_text") or record.get("recognized_text", "")),
            "ocr_blocks": str(record.get("ocr_blocks", "")),
            "recognition_mode": str(record.get("recognition_mode") or "text"),
            "upload_type": str(record.get("upload_type") or "image"),
            "edited_text": str(record.get("edited_text", "")),
            "created_time": str(record["created_time"]),
            "file_size": int(record.get("file_size", 0)),
            "image_hash": str(record.get("image_hash", "")),
            "region": record.get("region"),
            "preprocess_summary": str(record.get("preprocess_summary", "")),
            "elapsed_seconds": float(record.get("elapsed_seconds", 0.0)),
            "image_transform": str(record.get("image_transform", "")),
        }

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        data.setdefault("text_path", "")
        return data

    @staticmethod
    def _escape_like(value: str) -> str:
        return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

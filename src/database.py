"""SQLite database bootstrap for OCR records."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DATA_DIR = Path("data")
DEFAULT_DATABASE_NAME = "ocr_records.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS ocr_records (
    record_id TEXT PRIMARY KEY,
    original_image_path TEXT NOT NULL,
    saved_image_path TEXT NOT NULL,
    image_name TEXT NOT NULL DEFAULT '',
    image_width INTEGER NOT NULL DEFAULT 0,
    image_height INTEGER NOT NULL DEFAULT 0,
    preview_image BLOB,
    recognized_text TEXT NOT NULL,
    layout_text TEXT NOT NULL DEFAULT '',
    ocr_blocks TEXT NOT NULL DEFAULT '',
    recognition_mode TEXT NOT NULL DEFAULT 'text',
    upload_type TEXT NOT NULL DEFAULT 'image',
    edited_text TEXT NOT NULL DEFAULT '',
    created_time TEXT NOT NULL,
    file_size INTEGER NOT NULL DEFAULT 0,
    image_hash TEXT NOT NULL DEFAULT '',
    region TEXT,
    preprocess_summary TEXT NOT NULL DEFAULT '',
    elapsed_seconds REAL NOT NULL DEFAULT 0.0,
    image_transform TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_ocr_records_created_time
ON ocr_records(created_time);

CREATE INDEX IF NOT EXISTS idx_ocr_records_image_hash
ON ocr_records(image_hash);
"""

MIGRATIONS = {
    "image_name": "ALTER TABLE ocr_records ADD COLUMN image_name TEXT NOT NULL DEFAULT ''",
    "image_width": "ALTER TABLE ocr_records ADD COLUMN image_width INTEGER NOT NULL DEFAULT 0",
    "image_height": "ALTER TABLE ocr_records ADD COLUMN image_height INTEGER NOT NULL DEFAULT 0",
    "preview_image": "ALTER TABLE ocr_records ADD COLUMN preview_image BLOB",
    "layout_text": "ALTER TABLE ocr_records ADD COLUMN layout_text TEXT NOT NULL DEFAULT ''",
    "ocr_blocks": "ALTER TABLE ocr_records ADD COLUMN ocr_blocks TEXT NOT NULL DEFAULT ''",
    "recognition_mode": "ALTER TABLE ocr_records ADD COLUMN recognition_mode TEXT NOT NULL DEFAULT 'text'",
    "upload_type": "ALTER TABLE ocr_records ADD COLUMN upload_type TEXT NOT NULL DEFAULT 'image'",
    "edited_text": "ALTER TABLE ocr_records ADD COLUMN edited_text TEXT NOT NULL DEFAULT ''",
    "image_transform": "ALTER TABLE ocr_records ADD COLUMN image_transform TEXT NOT NULL DEFAULT ''",
}


def default_database_path(data_dir: str | Path = DEFAULT_DATA_DIR) -> Path:
    return Path(data_dir) / DEFAULT_DATABASE_NAME


def connect_database(database_path: str | Path | None = None) -> sqlite3.Connection:
    """Open the local SQLite database and ensure the schema exists."""

    path = Path(database_path) if database_path is not None else default_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    init_database(connection)
    return connection


def init_database(connection: sqlite3.Connection) -> None:
    """Create all OCR tables, indexes, and lightweight schema upgrades."""

    connection.executescript(SCHEMA_SQL)
    existing_columns = {
        row[1]
        for row in connection.execute("PRAGMA table_info(ocr_records)").fetchall()
    }
    for column_name, migration_sql in MIGRATIONS.items():
        if column_name not in existing_columns:
            connection.execute(migration_sql)
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_ocr_records_identity
        ON ocr_records(image_hash, recognition_mode, region, created_time)
        """
    )
    connection.commit()

"""Frozen-application path helpers.

When packaged by PyInstaller, ``sys._MEIPASS`` points to the read-only
bundle directory and ``sys.frozen`` is ``True``.  This module centralises the
runtime / writable-data vs. read-only-resource distinction so that every
other module can ask "where does the database go?" instead of repeating
frozen checks.
"""

from __future__ import annotations

import sys
from pathlib import Path

_APP_NAME = "404 Found OCR"


def _is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def get_data_dir() -> Path:
    """Return a writable user-data directory.

    Frozen (macOS example):
        ``~/Library/Application Support/OCRTool/``

    Development:
        ``data/`` (relative to the project root, same as current behaviour)
    """
    if _is_frozen():
        if sys.platform == "darwin":
            base = Path.home() / "Library" / "Application Support" / _APP_NAME
        elif sys.platform == "win32":
            base = Path.home() / "AppData" / "Local" / _APP_NAME
        else:
            base = Path.home() / ".local" / "share" / _APP_NAME.lower()
        base.mkdir(parents=True, exist_ok=True)
        return base
    return Path("data")


def get_resource_path(relative_path: str | Path) -> Path:
    """Return the absolute path to a bundled resource file.

    Frozen:
        ``sys._MEIPASS / relative_path``

    Development:
        ``<project-root> / relative_path`` (resolved from this file's location)
    """
    relative = Path(relative_path)
    if _is_frozen():
        # PyInstaller sets _MEIPASS to the temp directory where it unpacks
        # bundled data files.
        base = Path(getattr(sys, "_MEIPASS", "."))
    else:
        # This file lives in src/, so parents[1] is the project root.
        base = Path(__file__).resolve().parents[1]
    return base / relative


def get_models_dir() -> Path:
    """Return the ``official_models`` directory containing PaddleX model files.

    Frozen:
        ``sys._MEIPASS / models / official_models /``  (bundled in the .app)

    Development:
        ``~/.paddlex / official_models /``  (PaddleX default cache)

    Usage in frozen mode::

        model_dir = get_models_dir()
        pipeline = PaddleOCR(
            text_detection_model_dir=str(model_dir / "PP-OCRv6_small_det"),
            ...
        )
    """
    if _is_frozen():
        base = Path(getattr(sys, "_MEIPASS", "."))
        bundled = base / "models" / "official_models"
        if bundled.is_dir():
            return bundled
        # Fallback to PaddleX cache if not bundled
        return Path.home() / ".paddlex" / "official_models"
    return Path.home() / ".paddlex" / "official_models"

"""OCR 结果 SQLite 持久化管理。

本模块只负责保存已经完成 OCR 的结果，不重新识别图片。OCR 历史记录统一写入
``data/ocr_records.db``，不再复制图片、写 TXT 文件或维护 records.json。
"""

from __future__ import annotations

import hashlib
import io
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from src.database import connect_database, default_database_path
from src.image_utils import detect_upload_type, render_pdf_first_page
from src.repositories.ocr_record_repository import OcrRecordRepository


class OCRStorageManager:
    """保存和读取 OCR 识别结果。"""

    PREVIEW_MAX_SIZE = (1600, 1200)

    def __init__(self, data_dir: str | Path = "data", database_path: str | Path | None = None) -> None:
        self.data_dir = Path(data_dir)
        self.database_path = Path(database_path) if database_path is not None else default_database_path(self.data_dir)
        self.connection = connect_database(self.database_path)
        self.repository = OcrRecordRepository(self.connection)

    def save_record(
        self,
        image_path: str | Path,
        recognized_text: str,
        *,
        layout_text: str | None = None,
        ocr_blocks: list[dict[str, Any]] | None = None,
        recognition_mode: str = "text",
        upload_type: str | None = None,
        edited_text: str | None = None,
        region: tuple[int, int, int, int] | None = None,
        preprocess_summary: str = "",
        elapsed_seconds: float = 0.0,
        rotation_quarters: int = 0,
        mirror_horizontal: bool = False,
        mirror_vertical: bool = False,
    ) -> dict[str, Any]:
        """保存一次 OCR 成功结果，并返回记录字典。"""

        source = Path(image_path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"原始文件不存在，无法保存记录：{source}")
        if not isinstance(recognized_text, str):
            raise TypeError("recognized_text 必须是字符串")

        record_upload_type = upload_type or detect_upload_type(source)
        image_width, image_height, preview_image = self._build_preview(
            source,
            upload_type=record_upload_type,
            rotation_quarters=rotation_quarters,
            mirror_horizontal=mirror_horizontal,
            mirror_vertical=mirror_vertical,
        )
        transform = self._serialize_image_transform(rotation_quarters, mirror_horizontal, mirror_vertical)
        record = {
            "record_id": uuid.uuid4().hex,
            "original_image_path": str(source),
            "saved_image_path": str(source),
            "image_name": source.name,
            "image_width": image_width,
            "image_height": image_height,
            "preview_image": preview_image,
            "text_path": "",
            "recognized_text": recognized_text,
            "layout_text": layout_text or recognized_text,
            "ocr_blocks": json.dumps(ocr_blocks or [], ensure_ascii=False),
            "recognition_mode": recognition_mode or "text",
            "upload_type": record_upload_type,
            "edited_text": edited_text or "",
            "created_time": datetime.now().replace(microsecond=0).isoformat(),
            "file_size": source.stat().st_size,
            "image_hash": self._sha256_file(source),
            "region": self._serialize_region(region),
            "preprocess_summary": preprocess_summary,
            "elapsed_seconds": elapsed_seconds,
            "image_transform": transform,
        }
        saved = self.repository.insert(record)
        saved["text_path"] = ""
        return saved

    def load_records(self) -> list[dict[str, Any]]:
        """从 SQLite 读取全部 OCR 记录。"""

        return self.repository.list_all()

    def count_records(self) -> int:
        """返回 SQLite 中的 OCR 历史记录总数。"""

        return self.repository.count_records()

    def get_record(self, record_id: str) -> dict[str, Any] | None:
        """按记录 ID 读取单条 OCR 记录。"""

        return self.repository.get_by_id(record_id)

    def search_records(self, keyword: str) -> list[dict[str, Any]]:
        """从 SQLite 搜索 OCR 文本；空关键词返回全部记录。"""

        keyword = keyword.strip()
        if not keyword:
            return self.load_records()
        return self.repository.search(keyword)

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
        """按关键词、识别模式、文件类型和时间范围查询 SQLite 历史记录。"""

        return self.repository.query_records(
            keyword=keyword,
            recognition_mode=recognition_mode,
            upload_type=upload_type,
            start_time=start_time,
            end_time=end_time,
            ascending=ascending,
        )

    def delete_records(self, record_ids: list[str]) -> int:
        """按记录 ID 批量删除 SQLite OCR 历史记录。"""

        return self.repository.delete_by_ids(record_ids)

    def clear_records(self) -> None:
        """清空 SQLite 中的 OCR 历史记录。"""

        self.repository.delete_all()

    def update_edited_text(self, record_id: str, edited_text: str) -> None:
        """只更新用户编辑后的文本。"""

        self.repository.update_edited_text(record_id, edited_text)

    def close(self) -> None:
        self.connection.close()

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _build_preview(
        path: Path,
        *,
        upload_type: str = "image",
        rotation_quarters: int = 0,
        mirror_horizontal: bool = False,
        mirror_vertical: bool = False,
    ) -> tuple[int, int, bytes]:
        """生成数据库内置缩略图，历史查询无需依赖原图仍存在。"""

        if upload_type == "document":
            try:
                preview, _page_count = render_pdf_first_page(path, max_size=OCRStorageManager.PREVIEW_MAX_SIZE)
            except ValueError:
                return 0, 0, b""
            width, height = preview.size
            output = io.BytesIO()
            preview.save(output, format="PNG")
            return width, height, output.getvalue()

        with Image.open(path) as image:
            preview = ImageOps.exif_transpose(image)
            if mirror_horizontal:
                preview = ImageOps.mirror(preview)
            if mirror_vertical:
                preview = ImageOps.flip(preview)
            rotation_quarters = rotation_quarters % 4
            if rotation_quarters:
                preview = preview.rotate(-90 * rotation_quarters, expand=True)
            width, height = preview.size
            if preview.mode not in {"RGB", "RGBA"}:
                preview = preview.convert("RGB")
            preview.thumbnail(OCRStorageManager.PREVIEW_MAX_SIZE, Image.Resampling.LANCZOS)
            output = io.BytesIO()
            preview.save(output, format="PNG")
            return width, height, output.getvalue()

    @staticmethod
    def _serialize_image_transform(
        rotation_quarters: int,
        mirror_horizontal: bool,
        mirror_vertical: bool,
    ) -> str:
        return json.dumps(
            {
                "rotation_quarters": rotation_quarters % 4,
                "mirror_horizontal": bool(mirror_horizontal),
                "mirror_vertical": bool(mirror_vertical),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _serialize_region(region: tuple[int, int, int, int] | None) -> str | None:
        if region is None:
            return None
        return ",".join(str(value) for value in region)

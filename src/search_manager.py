"""OCR 历史文本数据库查询。

查询只读取 SQLite 中已经保存的 OCR 文本，不重新调用 PaddleOCR。空关键词返回全部
历史记录，供历史窗口初始展示使用。
"""

from __future__ import annotations

from typing import Any

from src.storage_manager import OCRStorageManager


class OCRSearchManager:
    """基于已保存 OCR 文本的关键词检索。"""

    def __init__(self, storage_manager: OCRStorageManager | None = None) -> None:
        self.storage_manager = storage_manager or OCRStorageManager()

    def search(self, keyword: str = "") -> list[dict[str, Any]]:
        """搜索候选记录；空关键词返回全部已识别图片。"""

        return self.search_records(keyword=keyword)

    def search_records(
        self,
        *,
        keyword: str = "",
        recognition_mode: str | None = None,
        upload_type: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        newest_first: bool = False,
    ) -> list[dict[str, Any]]:
        """按关键词、识别模式、文件类型和时间范围搜索候选记录。"""

        keyword = keyword.strip()
        records = self.storage_manager.query_records(
            keyword=keyword,
            recognition_mode=recognition_mode,
            upload_type=upload_type,
            start_time=start_time,
            end_time=end_time,
            ascending=not newest_first,
        )
        return [self._to_search_result(record, keyword) for record in records]

    def delete_records(self, record_ids: list[str]) -> int:
        """删除指定历史记录并返回删除数量。"""

        return self.storage_manager.delete_records(record_ids)

    def _to_search_result(self, record: dict[str, Any], keyword: str) -> dict[str, Any]:
        keyword_lower = keyword.lower()
        text = str(record.get("recognized_text", ""))
        return {
            "record_id": record.get("record_id", ""),
            "created_time": record.get("created_time", ""),
            "saved_image_path": record.get("saved_image_path", ""),
            "original_image_path": record.get("original_image_path", ""),
            "image_name": record.get("image_name", ""),
            "image_width": record.get("image_width", 0),
            "image_height": record.get("image_height", 0),
            "preview_image": record.get("preview_image"),
            "recognition_mode": record.get("recognition_mode", "text"),
            "upload_type": record.get("upload_type", "image"),
            "region": record.get("region"),
            "image_transform": record.get("image_transform", ""),
            "edited_text": record.get("edited_text", ""),
            "text_path": "",
            "snippet": self.build_snippet(text, keyword),
            "match_count": text.lower().count(keyword_lower) if keyword else 0,
        }

    def build_snippet(self, text: str, keyword: str, window: int = 30) -> str:
        """围绕第一个命中位置生成摘要片段；空关键词返回文本开头。"""

        if window < 0:
            raise ValueError("window 必须大于等于 0")
        if not keyword:
            return text[: window * 2]

        index = text.lower().find(keyword.lower())
        if index < 0:
            return text[: window * 2]

        start = max(index - window, 0)
        end = min(index + len(keyword) + window, len(text))
        prefix = "..." if start > 0 else ""
        suffix = "..." if end < len(text) else ""
        return f"{prefix}{text[start:end]}{suffix}"

    def get_full_result(self, record_id: str) -> dict[str, Any]:
        """按记录 ID 返回图片预览信息和完整 OCR 文本。"""

        record_id = record_id.strip()
        if not record_id:
            raise ValueError("record_id 不能为空")

        record = self.storage_manager.get_record(record_id)
        if record is None:
            raise KeyError(f"未找到 OCR 记录：{record_id}")
        return {
            "record_id": record_id,
            "image_path": record.get("saved_image_path", ""),
            "original_image_path": record.get("original_image_path", ""),
            "image_name": record.get("image_name", ""),
            "image_width": record.get("image_width", 0),
            "image_height": record.get("image_height", 0),
            "preview_image": record.get("preview_image"),
            "text_path": "",
            "created_time": record.get("created_time", ""),
            "recognized_text": record.get("recognized_text", ""),
            "layout_text": record.get("layout_text") or record.get("recognized_text", ""),
            "edited_text": record.get("edited_text", ""),
            "recognition_mode": record.get("recognition_mode", "text"),
            "upload_type": record.get("upload_type", "image"),
            "region": record.get("region"),
            "image_transform": record.get("image_transform", ""),
            "ocr_blocks": record.get("ocr_blocks", ""),
            "metadata": record,
        }

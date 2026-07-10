"""Pure helper functions for the history search GUI."""

from __future__ import annotations

from datetime import date

from src.gui.history_constants import (
    DISPLAY_MODE_LAYOUT,
    MODE_FILTER_DOCUMENT,
    MODE_FILTER_TEXT,
    TEXT_SOURCE_AFTER,
    TEXT_SOURCE_BEFORE,
    UPLOAD_FILTER_DOCUMENT,
    UPLOAD_FILTER_IMAGE,
)


def select_history_detail_text(
    record: dict[str, object],
    display_mode: str,
    text_source: str = TEXT_SOURCE_BEFORE,
) -> str:
    """根据历史详情显示方式和编辑状态选择文本。"""

    recognized_text = str(record.get("recognized_text", ""))
    if text_source == TEXT_SOURCE_AFTER:
        return str(record.get("edited_text") or recognized_text)
    if display_mode == DISPLAY_MODE_LAYOUT:
        return str(record.get("layout_text") or recognized_text)
    return recognized_text


def history_mode_filter_value(label: str) -> str | None:
    """把历史筛选下拉框文案转换为数据库识别模式。"""

    if label == MODE_FILTER_TEXT:
        return "text"
    if label == MODE_FILTER_DOCUMENT:
        return "document"
    return None


def history_upload_filter_value(label: str) -> str | None:
    """把文本类型下拉框文案转换为数据库上传类型。"""

    if label == UPLOAD_FILTER_IMAGE:
        return "image"
    if label == UPLOAD_FILTER_DOCUMENT:
        return "document"
    return None


def build_history_day_bounds(start_day: date, end_day: date) -> tuple[str, str]:
    """把日期范围转换为 SQLite ISO 时间边界。"""

    if start_day > end_day:
        raise ValueError("开始时间不能晚于结束时间")
    return f"{start_day.isoformat()}T00:00:00", f"{end_day.isoformat()}T23:59:59"


def format_history_result_count(count: int) -> str:
    return f"共 {count} 条"


def format_history_date_range(start_time: str | None, end_time: str | None) -> str:
    if not start_time or not end_time:
        return ""
    return f"{start_time[:10]} 至 {end_time[:10]}"

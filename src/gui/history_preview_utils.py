"""Image preview helpers for the history search GUI."""

from __future__ import annotations

import io
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from src.gui.pixel_theme import INK, PAPER
from src.image_utils import render_pdf_first_page


def parse_region(value: object) -> tuple[int, int, int, int] | None:
    if value is None:
        return None
    parts = str(value).split(",")
    if len(parts) != 4:
        return None
    try:
        return tuple(int(part.strip()) for part in parts)  # type: ignore[return-value]
    except ValueError:
        return None


def parse_image_transform(record: dict[str, object]) -> tuple[int, bool, bool]:
    value = record.get("image_transform")
    if isinstance(value, dict):
        data = value
    else:
        try:
            data = json.loads(str(value or "{}"))
        except json.JSONDecodeError:
            data = {}
    if not isinstance(data, dict):
        data = {}
    return (
        int(data.get("rotation_quarters", 0) or 0) % 4,
        bool(data.get("mirror_horizontal", False)),
        bool(data.get("mirror_vertical", False)),
    )


def apply_record_image_transform(image: Image.Image, record: dict[str, object]) -> Image.Image:
    rotation_quarters, mirror_horizontal, mirror_vertical = parse_image_transform(record)
    transformed = image
    if mirror_horizontal:
        transformed = ImageOps.mirror(transformed)
    if mirror_vertical:
        transformed = ImageOps.flip(transformed)
    if rotation_quarters:
        transformed = transformed.rotate(-90 * rotation_quarters, expand=True)
    return transformed.copy()


def fit_image(image: Image.Image, box: tuple[int, int], *, allow_upscale: bool) -> Image.Image:
    """按容器等比缩放；需要时允许放大数据库缩略图以填充区域。"""

    target_width, target_height = box
    source = image.copy()
    if source.mode not in {"RGB", "RGBA"}:
        source = source.convert("RGB")
    scale = min(target_width / source.width, target_height / source.height)
    if not allow_upscale:
        scale = min(scale, 1.0)
    new_size = (
        max(1, int(round(source.width * scale))),
        max(1, int(round(source.height * scale))),
    )
    if new_size == source.size:
        return source
    return source.resize(new_size, Image.Resampling.LANCZOS)


def draw_region_overlay(image: Image.Image, record: dict[str, object]) -> Image.Image:
    region = parse_region(record.get("region"))
    if region is None:
        return image
    source_width = int(record.get("image_width", 0) or 0)
    source_height = int(record.get("image_height", 0) or 0)
    if source_width <= 0 or source_height <= 0:
        return image
    x1, y1, x2, y2 = region
    scale_x = image.width / source_width
    scale_y = image.height / source_height
    left = int(round(min(x1, x2) * scale_x))
    top = int(round(min(y1, y2) * scale_y))
    right = int(round(max(x1, x2) * scale_x))
    bottom = int(round(max(y1, y2) * scale_y))
    if right <= left or bottom <= top:
        return image
    output = image.copy()
    draw = ImageDraw.Draw(output)
    draw.rectangle((left, top, right, bottom), outline=INK, width=3)
    draw.rectangle((left + 3, top + 3, right - 3, bottom - 3), outline=PAPER, width=1)
    return output


def load_preview_image(
    record: dict[str, object],
    preview_image_cache: dict[str, Image.Image | None],
    *,
    prefer_file: bool = True,
) -> Image.Image | None:
    key = str(record.get("record_id") or record.get("image_path") or record.get("saved_image_path") or "")
    if record.get("image_transform"):
        key = f"{key}:{record.get('image_transform')}"
    if prefer_file and key in preview_image_cache:
        cached = preview_image_cache[key]
        return cached.copy() if cached is not None else None

    if prefer_file and record.get("upload_type") != "document":
        for field in ("image_path", "saved_image_path", "original_image_path"):
            image_path = Path(str(record.get(field) or ""))
            if image_path.is_file():
                with Image.open(image_path) as image:
                    preview = ImageOps.exif_transpose(image)
                    preview = apply_record_image_transform(preview, record)
                    if preview.mode not in {"RGB", "RGBA"}:
                        preview = preview.convert("RGB")
                    copied = preview.copy()
                    preview_image_cache[key] = copied
                    return copied.copy()

    raw_preview = record.get("preview_image")
    if isinstance(raw_preview, memoryview):
        raw_preview = raw_preview.tobytes()
    if isinstance(raw_preview, bytes) and raw_preview:
        try:
            with Image.open(io.BytesIO(raw_preview)) as image:
                copied = image.copy()
                if prefer_file:
                    preview_image_cache[key] = copied
                return copied.copy()
        except OSError:
            pass
    if record.get("upload_type") == "document":
        for field in ("image_path", "saved_image_path", "original_image_path"):
            document_path = Path(str(record.get(field) or ""))
            if document_path.is_file():
                try:
                    preview, _page_count = render_pdf_first_page(document_path)
                except ValueError:
                    continue
                if prefer_file:
                    preview_image_cache[key] = preview.copy()
                return preview.copy()
    return None

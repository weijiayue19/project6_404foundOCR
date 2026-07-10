"""图片、PDF 校验与预览相关的共享配置。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from PIL import Image, UnidentifiedImageError

UploadType = Literal["image", "document"]

MAX_IMAGE_FILE_BYTES = 200 * 1024 * 1024
MAX_IMAGE_PIXELS = 500_000_000
SUPPORTED_IMAGE_FORMATS = {"JPEG", "PNG", "BMP"}
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}
SUPPORTED_DOCUMENT_SUFFIXES = {".pdf"}
SUPPORTED_UPLOAD_SUFFIXES = SUPPORTED_IMAGE_SUFFIXES | SUPPORTED_DOCUMENT_SUFFIXES

# 适当提高 Pillow 的超大图保护阈值，兼顾清晰预览与内存风险控制。
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


def validate_image_path(image_path: str | Path) -> tuple[Path, int, int]:
    """校验图片存在性、格式和尺寸，返回规范化路径与宽高。"""

    path = Path(image_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"图片不存在：{path}")

    file_size = path.stat().st_size
    if file_size > MAX_IMAGE_FILE_BYTES:
        raise ValueError(
            f"图片文件过大：{_format_megabytes(file_size)} MB，当前最大支持 200.0 MB"
        )

    try:
        with Image.open(path) as image:
            image.load()
            image_format = (image.format or "").upper()
            if image_format not in SUPPORTED_IMAGE_FORMATS:
                raise ValueError(
                    "不支持的图片格式。请选择 JPG、JPEG、PNG 或 BMP 文件。"
                )
            width, height = image.size
    except Image.DecompressionBombError as exc:
        raise ValueError("图片像素过高，当前最大支持 5 亿像素。") from exc
    except UnidentifiedImageError as exc:
        raise ValueError("无法识别图片格式，请重新选择有效的图片文件。") from exc
    except OSError as exc:
        raise ValueError("图片文件损坏或无法读取，请更换图片后重试。") from exc

    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError("图片像素过高，当前最大支持 5 亿像素。")

    return path, width, height


def detect_upload_type(path: str | Path) -> UploadType:
    """根据扩展名判断导入文件类型。"""

    suffix = Path(path).suffix.lower()
    if suffix in SUPPORTED_DOCUMENT_SUFFIXES:
        return "document"
    return "image"


def validate_upload_path(upload_path: str | Path) -> tuple[Path, UploadType, int, int]:
    """校验图片或 PDF 文档，返回路径、上传类型和预览宽高。"""

    path = Path(upload_path).expanduser().resolve()
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_DOCUMENT_SUFFIXES:
        return validate_document_path(path)
    if suffix in SUPPORTED_IMAGE_SUFFIXES:
        image_path, width, height = validate_image_path(path)
        return image_path, "image", width, height
    raise ValueError("不支持的文件格式。请选择 JPG、JPEG、PNG、BMP 或 PDF 文件。")


def validate_document_path(document_path: str | Path) -> tuple[Path, UploadType, int, int]:
    """校验 PDF 文档，并用首页预览尺寸作为宽高。"""

    path = Path(document_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"文档不存在：{path}")
    if path.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
        raise ValueError("不支持的文档格式。请选择 PDF 文件。")

    file_size = path.stat().st_size
    if file_size > MAX_IMAGE_FILE_BYTES:
        raise ValueError(
            f"文档文件过大：{_format_megabytes(file_size)} MB，当前最大支持 200.0 MB"
        )

    preview, _page_count = render_pdf_first_page(path)
    return path, "document", preview.width, preview.height


def render_pdf_first_page(pdf_path: str | Path, *, max_size: tuple[int, int] = (1600, 1200)) -> tuple[Image.Image, int]:
    """将 PDF 首页渲染为 PIL 图片，并返回页数。"""

    pages, page_count = _render_pdf_pages(pdf_path, max_size=max_size, first_page_only=True)
    if not pages:
        raise ValueError("PDF 文档没有可预览页面。")
    return pages[0], page_count


def render_pdf_pages(
    pdf_path: str | Path,
    *,
    max_size: tuple[int, int] = (1600, 1200),
) -> list[Image.Image]:
    """将 PDF 全部页面渲染为 PIL 图片列表。"""

    pages, _page_count = _render_pdf_pages(pdf_path, max_size=max_size, first_page_only=False)
    return pages


def _render_pdf_pages(
    pdf_path: str | Path,
    *,
    max_size: tuple[int, int],
    first_page_only: bool,
) -> tuple[list[Image.Image], int]:
    path = Path(pdf_path).expanduser().resolve()
    try:
        import pypdfium2 as pdfium

        document = pdfium.PdfDocument(str(path))
        page_count = len(document)
        if page_count <= 0:
            raise ValueError("PDF 文档没有可预览页面。")
        page_indices = range(1 if first_page_only else page_count)
        pages: list[Image.Image] = []
        for page_index in page_indices:
            page = document[page_index]
            try:
                bitmap = page.render(scale=2.0)
                image = bitmap.to_pil()
            finally:
                close_page = getattr(page, "close", None)
                if callable(close_page):
                    close_page()
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGB")
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
            pages.append(image.copy())
        close_document = getattr(document, "close", None)
        if callable(close_document):
            close_document()
    except ValueError:
        raise
    except Exception as exc:  # noqa: BLE001 - 统一转换 PDF 读取错误给 GUI 展示。
        raise ValueError("PDF 文档损坏、加密或无法读取，请更换文件后重试。") from exc

    return pages, page_count


def _format_megabytes(file_size: int) -> str:
    return f"{file_size / (1024 * 1024):.1f}"

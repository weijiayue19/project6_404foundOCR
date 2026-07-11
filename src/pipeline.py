"""本地 OCR 核心流程编排。

当前项目的自定义预处理只保留：手动灰度化、手动自适应二值化、手动中值滤波
和 numpy 区域裁剪。文本方向处理、缩放和模型输入预处理交给 PaddleOCR 内部。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

from src.image_utils import detect_upload_type, validate_image_path
from src.preprocess.binarize import adaptive_binarize
from src.preprocess.denoise import median_filter
from src.preprocess.grayscale import image_from_gray_array, to_grayscale_array
from src.region_selector import crop_region
from src.services.ocr_service import OcrService
from src.storage_manager import OCRStorageManager


DEFAULT_OPTIONS: dict[str, Any] = {
    "use_grayscale": True,
    "use_binarize": True,
    "use_denoise": True,
    "crop_box": None,
    "save_intermediate": True,
    "save_result": True,
}

ALLOWED_OPTION_KEYS = set(DEFAULT_OPTIONS)


def process_single_image(
    image_path: str | Path,
    options: dict[str, Any] | None = None,
    ocr_service: Any | None = None,
    storage_manager: OCRStorageManager | None = None,
) -> dict[str, Any]:
    """执行单张图片 OCR 核心流程并保存结果。

    流程：
    1. 检查图片路径；
    2. 读取原图；
    3. 可选区域裁剪；
    4. 手动灰度化；
    5. 手动自适应二值化；
    6. 手动中值滤波去噪；
    7. 保存中间图和最终处理图；
    8. 调用 PaddleOCR；
    9. 将识别文本和元数据写入 SQLite；
    10. 直接统计 SQLite 历史记录数量。
    """

    config = normalize_options(options)
    source_path, _width, _height = _run_step("检查图片路径", lambda: validate_image_path(image_path))
    run_id = uuid.uuid4().hex[:8]
    stem = _safe_stem(source_path)
    intermediate_paths: dict[str, str | None] = {
        "cropped": None,
        "gray": None,
        "binary": None,
        "denoised": None,
    }

    image = _run_step("读取原图", lambda: _load_image(source_path))
    current_array: np.ndarray | None = None
    output_root = Path("outputs")
    intermediate_dir = output_root / "intermediate"
    results_dir = output_root / "results"

    crop_box = config["crop_box"]
    if crop_box is not None:
        def do_crop() -> Image.Image:
            cropped = crop_region(np.asarray(image), *crop_box)
            return Image.fromarray(cropped.astype(np.uint8))

        image = _run_step("区域裁剪", do_crop)
        current_array = np.asarray(image).astype(np.uint8, copy=True)
        intermediate_paths["cropped"] = _save_if_enabled(
            image,
            intermediate_dir / f"{stem}_{run_id}_cropped.png",
            config["save_intermediate"],
        )

    needs_gray = bool(config["use_grayscale"] or config["use_binarize"] or config["use_denoise"])
    if needs_gray:
        gray = _run_step("手动灰度化", lambda: to_grayscale_array(image))
        current_array = gray
        image = image_from_gray_array(gray)
        if config["use_grayscale"] or config["use_binarize"] or config["use_denoise"]:
            intermediate_paths["gray"] = _save_array_if_enabled(
                gray,
                intermediate_dir / f"{stem}_{run_id}_gray.png",
                config["save_intermediate"],
            )

    if config["use_binarize"]:
        if current_array is None or current_array.ndim != 2:
            current_array = _run_step("二值化前自动灰度化", lambda: to_grayscale_array(image))
        binary = _run_step("手动自适应二值化", lambda: adaptive_binarize(current_array, window_size=25, C=10))
        current_array = binary
        image = image_from_gray_array(binary)
        intermediate_paths["binary"] = _save_array_if_enabled(
            binary,
            intermediate_dir / f"{stem}_{run_id}_binary.png",
            config["save_intermediate"],
        )

    if config["use_denoise"]:
        if current_array is None or current_array.ndim != 2:
            current_array = _run_step("去噪前自动灰度化", lambda: to_grayscale_array(image))
        denoised = _run_step("手动中值滤波去噪", lambda: median_filter(current_array, k_size=3))
        current_array = denoised
        image = image_from_gray_array(denoised)
        intermediate_paths["denoised"] = _save_array_if_enabled(
            denoised,
            intermediate_dir / f"{stem}_{run_id}_denoised.png",
            config["save_intermediate"],
        )

    processed_image_path = _save_if_enabled(
        image,
        results_dir / f"{stem}_{run_id}_processed.png",
        config["save_result"],
    )
    if processed_image_path is None:
        processed_image_path = _save_if_enabled(
            image,
            results_dir / f"{stem}_{run_id}_processed.png",
            True,
        )

    service = ocr_service or OcrService()
    ocr_raw_result = _run_step("PaddleOCR 识别", lambda: service.recognize(processed_image_path))
    recognized_text = _render_ocr_text(ocr_raw_result, "plain")
    layout_text = _render_ocr_text(ocr_raw_result, "layout")

    storage = storage_manager or OCRStorageManager()
    record = _run_step(
        "保存 OCR 结果",
        lambda: storage.save_record(
            source_path,
            recognized_text,
            layout_text=layout_text,
            ocr_blocks=_ocr_blocks_to_dicts(ocr_raw_result),
            recognition_mode="text",
            upload_type=detect_upload_type(source_path),
            region=config["crop_box"],
        ),
    )
    history_size = _run_step("统计历史记录数量", storage.count_records)

    return {
        "success": True,
        "record_id": record["record_id"],
        "recognized_text": recognized_text,
        "saved_image_path": record["saved_image_path"],
        "text_path": "",
        "created_time": record["created_time"],
        "intermediate_paths": intermediate_paths,
        "processed_image_path": processed_image_path,
        "history_size": history_size,
    }


def normalize_options(options: dict[str, Any] | None) -> dict[str, Any]:
    """合并并校验新的 options 结构。"""

    merged = dict(DEFAULT_OPTIONS)
    if options is not None:
        unknown = set(options) - ALLOWED_OPTION_KEYS
        if unknown:
            raise ValueError(f"未知 options 字段：{', '.join(sorted(unknown))}")
        merged.update(options)

    for name in ("use_grayscale", "use_binarize", "use_denoise", "save_intermediate", "save_result"):
        if not isinstance(merged[name], bool):
            raise TypeError(f"options['{name}'] 必须是 bool")

    crop_box = merged["crop_box"]
    if crop_box is not None:
        if not isinstance(crop_box, (tuple, list)) or len(crop_box) != 4:
            raise ValueError("options['crop_box'] 必须是 None 或 4 个坐标")
        merged["crop_box"] = tuple(int(value) for value in crop_box)

    return merged


def _load_image(path: Path) -> Image.Image:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source)
        if image.mode == "RGBA":
            image = image.convert("RGB")
        elif image.mode not in {"RGB", "L"}:
            image = image.convert("RGB")
        return image.copy()


def _ocr_blocks_to_dicts(result: Any) -> list[dict[str, Any]]:
    blocks = getattr(result, "blocks", None)
    if not isinstance(blocks, list):
        return []
    return [
        {
            "text": getattr(block, "text", ""),
            "confidence": float(getattr(block, "confidence", 0.0)),
            "box": getattr(block, "box", []),
        }
        for block in blocks
    ]


def _render_ocr_text(result: Any, mode: str) -> str:
    render_text = getattr(result, "render_text", None)
    if callable(render_text):
        return str(render_text(mode))
    text = getattr(result, "text", result)
    return str(text)


def _save_if_enabled(image: Image.Image, output_path: Path, enabled: bool) -> str | None:
    if not enabled:
        return None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)
    return str(output_path)


def _save_array_if_enabled(array: np.ndarray, output_path: Path, enabled: bool) -> str | None:
    if not enabled:
        return None
    return _save_if_enabled(Image.fromarray(array.astype(np.uint8), mode="L"), output_path, True)


def _run_step(name: str, func: Any) -> Any:
    try:
        return func()
    except Exception as exc:  # noqa: BLE001 - pipeline must report the failed step clearly.
        print(f"[ERROR] {name}失败：{exc}")
        raise RuntimeError(f"{name}失败：{exc}") from exc


def _safe_stem(path: Path) -> str:
    stem = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in path.stem)
    return stem or "image"


def dump_result(result: dict[str, Any]) -> str:
    """把流程返回对象格式化为中文友好的 JSON 字符串。"""

    return json.dumps(result, ensure_ascii=False, indent=2)

"""Shared state objects and labels for the main OCR window."""

from __future__ import annotations

from dataclasses import dataclass

FAST_MODE_LABEL = "快速识别"
DEEP_MODE_LABEL = "深度识别"

PREPROCESS_STEP_LABELS = {
    "grayscale": "灰度化",
    "binarize": "自适应二值化",
    "denoise": "中值滤波去噪",
}
PREPROCESS_STEP_ORDER = ("grayscale", "binarize", "denoise")


@dataclass(slots=True)
class ImageEditState:
    rotation_quarters: int = 0
    mirrored: bool = False
    vertical_mirrored: bool = False

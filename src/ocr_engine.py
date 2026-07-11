"""PaddleOCR 调用与本地预处理编排。

PaddleOCR 是允许使用的最终文字检测/识别引擎；本模块只负责在调用 OCR 前，
使用 `src.preprocess` 中手写的 PIL/numpy 算法完成裁剪、灰度、二值化和去噪。
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Callable, Literal, TypeVar

import numpy as np
from PIL import Image, ImageOps

from src.image_utils import detect_upload_type
from src.models.ocr_result import OcrResult
from src.preprocess.binarize import adaptive_mean_threshold, binarize_otsu, global_threshold
from src.preprocess.denoise import median_filter, remove_isolated_pixels
from src.preprocess.grayscale import image_from_gray_array, to_grayscale_array
from src.region_selector import crop_region
from src.services.document_service import DocumentService
from src.services.ocr_service import OcrService

BinarizeMode = Literal["none", "global", "otsu", "adaptive"]
DenoiseMode = Literal["none", "median", "isolated"]
PreprocessStepName = Literal["grayscale", "binarize", "denoise"]
OcrMode = Literal["text", "document"]
T = TypeVar("T")

DEFAULT_PREPROCESS_STEP_ORDER: tuple[PreprocessStepName, ...] = ("grayscale", "binarize", "denoise")


@dataclass(slots=True)
class PreprocessConfig:
    """预处理配置。"""

    enable_grayscale: bool = False
    binarize_mode: BinarizeMode = "none"
    global_threshold_value: int = 127
    adaptive_window_size: int = 31
    adaptive_c: float = 10.0
    denoise_mode: DenoiseMode = "none"
    denoise_kernel_size: int = 3
    save_intermediate: bool = False
    step_order: tuple[PreprocessStepName, ...] = DEFAULT_PREPROCESS_STEP_ORDER
    rotation_quarters: int = 0
    mirror_horizontal: bool = False
    mirror_vertical: bool = False


@dataclass(slots=True)
class PreprocessStep:
    """记录一步预处理，便于 demo、历史记录和答辩说明。"""

    name: str
    description: str
    elapsed_seconds: float
    image_path: Path | None = None


@dataclass(slots=True)
class OcrRequest:
    """一次 OCR 请求。region 使用原图坐标：(left, top, right, bottom)。"""

    image_path: Path
    mode: OcrMode = "text"
    region: tuple[int, int, int, int] | None = None
    preprocess_config: PreprocessConfig = field(default_factory=PreprocessConfig)


@dataclass(slots=True)
class OcrExecutionResult:
    """OCR 执行结果，包含 PaddleOCR 输出和预处理过程信息。"""

    ocr_result: OcrResult
    processed_image_path: Path
    steps: list[PreprocessStep]
    preprocess_seconds: float


class OcrEngine:
    """统一封装本地预处理和 PaddleOCR 调用。"""

    def __init__(self, text_service: OcrService | None = None, document_service: DocumentService | None = None) -> None:
        self.text_service = text_service or OcrService()
        self.document_service = document_service or DocumentService()
        self._temporary_directory = tempfile.TemporaryDirectory(prefix="project6_ocr_preprocess_")

    def recognize(self, request: OcrRequest) -> OcrExecutionResult:
        """执行完整 OCR 流程。"""

        if detect_upload_type(request.image_path) == "document":
            if request.mode != "document":
                raise ValueError("PDF 文档只能使用深度识别模式。")
            ocr_result = self.document_service.recognize(request.image_path)
            return OcrExecutionResult(
                ocr_result=ocr_result,
                processed_image_path=request.image_path,
                steps=[],
                preprocess_seconds=0.0,
            )

        started_at = perf_counter()
        processed_image, steps = self.preprocess(request)
        preprocess_seconds = perf_counter() - started_at
        processed_path = self._save_processed_image(processed_image, request.image_path)

        service = self.document_service if request.mode == "document" else self.text_service
        ocr_result = service.recognize(processed_path)
        return OcrExecutionResult(
            ocr_result=ocr_result,
            processed_image_path=processed_path,
            steps=steps,
            preprocess_seconds=preprocess_seconds,
        )

    def preprocess(self, request: OcrRequest) -> tuple[Image.Image, list[PreprocessStep]]:
        """仅执行预处理，不调用 PaddleOCR。"""

        config = request.preprocess_config
        steps: list[PreprocessStep] = []
        with Image.open(request.image_path) as original:
            image = ImageOps.exif_transpose(original)
            if image.mode not in {"RGB", "RGBA", "L"}:
                image = image.convert("RGB")
            image = image.copy()

        image = self._apply_input_transform(image, config)

        if request.region is not None:
            image = self._crop_region(image, request.region)
            steps.append(PreprocessStep("region", f"裁剪区域 {request.region}", 0.0))

        for step_name in self._ordered_preprocess_steps(config):
            if step_name == "grayscale":
                image, step = self._run_grayscale_step(image)
            elif step_name == "binarize":
                image, step = self._run_binarize_step(image, config)
            elif step_name == "denoise":
                image, step = self._run_denoise_step(image, config)
            else:
                raise ValueError(f"未知预处理步骤：{step_name}")
            steps.append(step)

        return image, steps

    def close(self) -> None:
        """释放 OCR 服务和临时目录。"""

        self.text_service.close()
        self.document_service.close()
        self._temporary_directory.cleanup()

    @staticmethod
    def _apply_input_transform(image: Image.Image, config: PreprocessConfig) -> Image.Image:
        transformed = image
        if config.mirror_horizontal:
            transformed = ImageOps.mirror(transformed)
        if config.mirror_vertical:
            transformed = ImageOps.flip(transformed)
        rotation_quarters = config.rotation_quarters % 4
        if rotation_quarters:
            transformed = transformed.rotate(-90 * rotation_quarters, expand=True)
        return transformed

    @staticmethod
    def _ordered_preprocess_steps(config: PreprocessConfig) -> tuple[PreprocessStepName, ...]:
        enabled: set[PreprocessStepName] = set()
        if config.enable_grayscale:
            enabled.add("grayscale")
        if config.binarize_mode != "none":
            enabled.add("binarize")
        if config.denoise_mode != "none":
            enabled.add("denoise")

        ordered: list[PreprocessStepName] = []
        for step_name in config.step_order:
            if step_name not in DEFAULT_PREPROCESS_STEP_ORDER:
                raise ValueError(f"未知预处理步骤：{step_name}")
            if step_name in enabled and step_name not in ordered:
                ordered.append(step_name)
        for step_name in DEFAULT_PREPROCESS_STEP_ORDER:
            if step_name in enabled and step_name not in ordered:
                ordered.append(step_name)
        return tuple(ordered)

    def _run_grayscale_step(self, image: Image.Image) -> tuple[Image.Image, PreprocessStep]:
        return self._time_step(
            "grayscale",
            "RGB 加权公式灰度化",
            lambda: image_from_gray_array(to_grayscale_array(image)),
        )

    def _run_binarize_step(self, image: Image.Image, config: PreprocessConfig) -> tuple[Image.Image, PreprocessStep]:
        gray = to_grayscale_array(image)
        if config.binarize_mode == "global":
            description = f"固定阈值二值化 threshold={config.global_threshold_value}"
            transform = lambda: global_threshold(gray, config.global_threshold_value)
        elif config.binarize_mode == "otsu":
            description = "Otsu 类间方差最大化自动阈值二值化"
            transform = lambda: binarize_otsu(gray)
        elif config.binarize_mode == "adaptive":
            description = f"积分图局部均值自适应二值化 window={config.adaptive_window_size}, c={config.adaptive_c}"
            transform = lambda: adaptive_mean_threshold(gray, config.adaptive_window_size, config.adaptive_c)
        else:
            raise ValueError(f"未知二值化模式：{config.binarize_mode}")
        array, step = self._time_step(config.binarize_mode, description, transform)
        return image_from_gray_array(array), step

    def _run_denoise_step(self, image: Image.Image, config: PreprocessConfig) -> tuple[Image.Image, PreprocessStep]:
        gray = to_grayscale_array(image)
        if config.denoise_mode == "median":
            description = f"手写 {config.denoise_kernel_size}x{config.denoise_kernel_size} 中值滤波"
            transform = lambda: median_filter(gray, config.denoise_kernel_size)
        elif config.denoise_mode == "isolated":
            description = "8 邻域孤立噪点去除"
            transform = lambda: remove_isolated_pixels(gray)
        else:
            raise ValueError(f"未知去噪模式：{config.denoise_mode}")
        array, step = self._time_step(config.denoise_mode, description, transform)
        return image_from_gray_array(array), step

    @staticmethod
    def _crop_region(image: Image.Image, region: tuple[int, int, int, int]) -> Image.Image:
        """使用 region_selector.crop_region 的 numpy 切片实现区域裁剪。"""

        cropped = crop_region(np.asarray(image), *region)
        return Image.fromarray(cropped.astype(np.uint8), mode=image.mode)

    def _save_processed_image(self, image: Image.Image, source_path: Path) -> Path:
        suffix = ".png" if image.mode in {"RGBA", "L"} else source_path.suffix.lower() or ".png"
        output = Path(self._temporary_directory.name) / f"processed_{abs(hash((source_path, image.size)))}{suffix}"
        save_image = image.convert("RGB") if suffix in {".jpg", ".jpeg"} and image.mode == "RGBA" else image
        save_image.save(output)
        return output

    @staticmethod
    def _time_step(name: str, description: str, func: Callable[[], T]) -> tuple[T, PreprocessStep]:
        started_at = perf_counter()
        result = func()
        return result, PreprocessStep(name, description, perf_counter() - started_at)


def demo(input_path: str | Path, output_path: str | Path = "demo_engine_preprocess.png") -> Path:
    """独立演示：执行一组默认预处理并保存最终图片，不调用 PaddleOCR。"""

    engine = OcrEngine()
    try:
        request = OcrRequest(
            image_path=Path(input_path),
            preprocess_config=PreprocessConfig(
                enable_grayscale=True,
                binarize_mode="adaptive",
                denoise_mode="median",
            ),
        )
        image, _steps = engine.preprocess(request)
        output = Path(output_path)
        image.save(output)
        return output
    finally:
        engine.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OCR 预处理编排 demo：python -m src.ocr_engine 图片路径")
    parser.add_argument("image")
    parser.add_argument("--output", default="demo_engine_preprocess.png")
    args = parser.parse_args()
    print(demo(args.image, args.output))

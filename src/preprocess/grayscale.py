"""灰度化算法。

不使用 cv2.cvtColor，也不使用 PIL.Image.convert("L") 完成核心灰度化。
默认采用 RGB 加权公式：
Y = 0.299R + 0.587G + 0.114B。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


_RGB_WEIGHTS = np.array([0.299, 0.587, 0.114], dtype=np.float32)


def _weighted_rgb_to_gray(rgb: np.ndarray) -> np.ndarray:
    """使用加权平均公式把 RGB 三通道矩阵转换为 uint8 二维灰度矩阵。"""

    # 人眼对绿色波段最敏感，因此绿色通道对亮度感知贡献最大，权重 0.587 最高；
    # 红色次之，蓝色最弱。这组权重能让灰度图更接近人眼看到的明暗关系。
    gray = rgb.astype(np.float32) @ _RGB_WEIGHTS
    return np.clip(np.rint(gray), 0, 255).astype(np.uint8)


def rgb_to_gray(image_path: str | Path) -> np.ndarray:
    """读取 RGB 图片并返回 uint8 类型的二维灰度矩阵。

    灰度化能去掉颜色信息，只保留字符边缘、笔画粗细和背景亮度差异，
    可降低 OCR 后续二值化、去噪、版面分析的输入复杂度。
    """

    with Image.open(image_path) as image:
        corrected = ImageOps.exif_transpose(image)
        if corrected.mode != "RGB":
            raise ValueError("rgb_to_gray 需要 RGB 图片")
        rgb = np.asarray(corrected)
    return _weighted_rgb_to_gray(rgb)


def save_gray(gray_array: np.ndarray, output_path: str | Path) -> None:
    """把二维 uint8 灰度矩阵保存为灰度图片。"""

    Image.fromarray(gray_array.astype(np.uint8), mode="L").save(output_path)


def to_grayscale_array(image: Image.Image) -> np.ndarray:
    """把 PIL 图片转换为 uint8 灰度矩阵。"""

    corrected = ImageOps.exif_transpose(image)
    if corrected.mode == "L":
        return np.asarray(corrected).astype(np.uint8, copy=True)
    if corrected.mode != "RGB":
        raise ValueError("to_grayscale_array 需要 RGB 图片")
    rgb = np.asarray(corrected)
    return _weighted_rgb_to_gray(rgb)


def image_from_gray_array(gray: np.ndarray) -> Image.Image:
    """把二维灰度矩阵转换为 PIL 灰度图。"""

    if gray.ndim != 2:
        raise ValueError("灰度图必须是二维数组")
    return Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8), mode="L")


def to_grayscale(image: Image.Image) -> Image.Image:
    """返回灰度 PIL 图片。"""

    return image_from_gray_array(to_grayscale_array(image))


def demo(input_path: str | Path, output_path: str | Path = "demo_gray.png") -> Path:
    """独立演示：读取图片、手写灰度化并保存结果。"""

    gray = rgb_to_gray(input_path)
    output = Path(output_path)
    save_gray(gray, output)
    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="灰度化 demo：python -m src.preprocess.grayscale 图片路径")
    parser.add_argument("image")
    parser.add_argument("--output", default="demo_gray.png")
    args = parser.parse_args()
    print(demo(args.image, args.output))

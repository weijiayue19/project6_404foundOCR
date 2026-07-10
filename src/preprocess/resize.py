"""金字塔缩放算法。

不使用 cv2.resize。这里手写最近邻、双线性重采样，并在大倍率缩小时先做
2 倍金字塔降采样，减少锯齿和计算量。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def _as_array(image: Image.Image) -> np.ndarray:
    array = np.asarray(image)
    if array.ndim == 2:
        return array[:, :, None]
    return array


def _restore_image(array: np.ndarray, mode: str) -> Image.Image:
    data = np.clip(np.rint(array), 0, 255).astype(np.uint8)
    if data.shape[2] == 1:
        return Image.fromarray(data[:, :, 0], mode="L")
    if data.shape[2] == 4:
        return Image.fromarray(data[:, :, :4], mode="RGBA")
    return Image.fromarray(data[:, :, :3], mode="RGB")


def bilinear_resize_array(array: np.ndarray, new_width: int, new_height: int) -> np.ndarray:
    """手写双线性插值缩放。"""

    if new_width <= 0 or new_height <= 0:
        raise ValueError("目标尺寸必须大于 0")
    source = array.astype(np.float32, copy=False)
    if source.ndim == 2:
        source = source[:, :, None]

    height, width, channels = source.shape
    if width == new_width and height == new_height:
        return source.copy()

    x_positions = np.linspace(0, width - 1, new_width, dtype=np.float32)
    y_positions = np.linspace(0, height - 1, new_height, dtype=np.float32)
    x0 = np.floor(x_positions).astype(np.int32)
    y0 = np.floor(y_positions).astype(np.int32)
    x1 = np.minimum(x0 + 1, width - 1)
    y1 = np.minimum(y0 + 1, height - 1)
    wx = (x_positions - x0)[None, :, None]
    wy = (y_positions - y0)[:, None, None]

    top = source[y0[:, None], x0[None, :], :] * (1 - wx) + source[y0[:, None], x1[None, :], :] * wx
    bottom = source[y1[:, None], x0[None, :], :] * (1 - wx) + source[y1[:, None], x1[None, :], :] * wx
    return top * (1 - wy) + bottom * wy


def _downsample_half_array(array: np.ndarray) -> np.ndarray:
    """2x2 均值降采样，是图像金字塔的一层。"""

    source = array.astype(np.float32, copy=False)
    if source.ndim == 2:
        source = source[:, :, None]
    height, width, channels = source.shape
    even_height = max((height // 2) * 2, 2)
    even_width = max((width // 2) * 2, 2)
    cropped = source[:even_height, :even_width, :]
    return cropped.reshape(even_height // 2, 2, even_width // 2, 2, channels).mean(axis=(1, 3))


def pyramid_resize(image: Image.Image, scale: float) -> Image.Image:
    """按比例缩放图片。

    当 scale 小于 0.5 时，先反复做 2 倍金字塔降采样，再用双线性插值到
    精确目标尺寸；放大或小幅缩小时直接使用手写双线性插值。
    """

    if scale <= 0:
        raise ValueError("scale 必须大于 0")
    width, height = image.size
    new_width = max(int(round(width * scale)), 1)
    new_height = max(int(round(height * scale)), 1)
    array = _as_array(image)
    current_scale = 1.0
    while scale / current_scale < 0.5 and min(array.shape[:2]) >= 2:
        array = _downsample_half_array(array)
        current_scale *= 0.5
    resized = bilinear_resize_array(array, new_width, new_height)
    return _restore_image(resized, image.mode)


def resize_to_width(image: Image.Image, target_width: int) -> Image.Image:
    """保持宽高比缩放到指定宽度。"""

    if target_width <= 0:
        raise ValueError("target_width 必须大于 0")
    return pyramid_resize(image, target_width / image.width)


def resize_to_height(image: Image.Image, target_height: int) -> Image.Image:
    """保持宽高比缩放到指定高度。"""

    if target_height <= 0:
        raise ValueError("target_height 必须大于 0")
    return pyramid_resize(image, target_height / image.height)


def resize_limit_long_side(image: Image.Image, max_side: int = 4096) -> Image.Image:
    """若长边超过限制，则等比缩小；否则返回副本。"""

    if max_side <= 0:
        raise ValueError("max_side 必须大于 0")
    long_side = max(image.size)
    if long_side <= max_side:
        return image.copy()
    return pyramid_resize(image, max_side / long_side)


def demo(input_path: str | Path, output_path: str | Path = "demo_resize.png", scale: float = 0.5) -> Path:
    """独立演示：读取图片并保存缩放结果。"""

    with Image.open(input_path) as image:
        result = pyramid_resize(image, scale)
    output = Path(output_path)
    result.save(output)
    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="金字塔缩放 demo：python -m src.preprocess.resize 图片路径")
    parser.add_argument("image")
    parser.add_argument("--output", default="demo_resize.png")
    parser.add_argument("--scale", type=float, default=0.5)
    args = parser.parse_args()
    print(demo(args.image, args.output, args.scale))

"""二值化算法。

本模块手写实现灰度图到黑白二值图的转换，不调用 cv2.threshold、
cv2.adaptiveThreshold、PIL.Image.convert("1") 等现成二值化接口。

统一输出规则：
- 文字 / 前景 = 0
- 背景 = 255
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from src.preprocess.grayscale import to_grayscale_array


def _ensure_gray(gray: np.ndarray) -> np.ndarray:
    """检查并返回二维 uint8 灰度矩阵。"""

    if not isinstance(gray, np.ndarray):
        raise TypeError("灰度图必须是 np.ndarray")
    if gray.ndim != 2:
        raise ValueError("二值化输入必须是二维灰度数组")
    if gray.size == 0:
        raise ValueError("空图像无法进行二值化")
    return gray.astype(np.uint8, copy=False)


def build_integral_image(gray_array: np.ndarray) -> np.ndarray:
    """构建带零边框的积分图。

    积分图 integral[y, x] 表示原图左上角到当前位置左上邻域的像素值总和。
    这里返回 shape 为 (height + 1, width + 1) 的数组，第一行和第一列为 0，
    这样后续计算贴边窗口时不需要写额外的边界分支。

    积分图的作用是加速局部窗口求和：如果每个像素都重新遍历窗口，
    时间复杂度会随 window_size 变大明显上升；有了积分图后，任意矩形区域
    只需要四个角的加减即可得到像素和。
    """

    source = _ensure_gray(gray_array).astype(np.float64, copy=False)
    height, width = source.shape
    integral = np.zeros((height + 1, width + 1), dtype=np.float64)
    integral[1:, 1:] = source.cumsum(axis=0).cumsum(axis=1)
    return integral


def local_sum_from_integral(
    integral: np.ndarray,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
) -> float:
    """根据积分图 O(1) 计算左闭右开矩形区域的像素和。

    区域坐标为 x: [x1, x2)、y: [y1, y2)。积分图提前累计了从左上角
    到各位置的总和，所以一个矩形区域可以由右下、右上、左下、左上
    四个累计值相减得到，不需要再次遍历该区域内的所有像素。
    """

    if not isinstance(integral, np.ndarray):
        raise TypeError("integral 必须是 np.ndarray")
    if integral.ndim != 2:
        raise ValueError("integral 必须是二维数组")
    if x1 > x2 or y1 > y2:
        raise ValueError("矩形区域坐标必须满足 x1 <= x2 且 y1 <= y2")

    max_y, max_x = integral.shape
    if not (0 <= x1 <= x2 < max_x and 0 <= y1 <= y2 < max_y):
        raise ValueError("矩形区域坐标超出积分图范围")

    return float(integral[y2, x2] - integral[y1, x2] - integral[y2, x1] + integral[y1, x1])


def otsu_threshold(gray: np.ndarray) -> int:
    """手写 Otsu 阈值：选择类间方差最大的灰度值。"""

    source = _ensure_gray(gray)
    hist = np.bincount(source.ravel(), minlength=256).astype(np.float64)
    total = source.size
    if total == 0:
        raise ValueError("空图像无法计算阈值")

    gray_values = np.arange(256, dtype=np.float64)
    sum_total = float(np.dot(gray_values, hist))
    weight_background = 0.0
    sum_background = 0.0
    best_threshold = 0
    best_variance = -1.0

    for level in range(256):
        weight_background += hist[level]
        if weight_background == 0:
            continue
        weight_foreground = total - weight_background
        if weight_foreground == 0:
            break

        sum_background += level * hist[level]
        mean_background = sum_background / weight_background
        mean_foreground = (sum_total - sum_background) / weight_foreground
        variance = weight_background * weight_foreground * (mean_background - mean_foreground) ** 2
        if variance > best_variance:
            best_variance = variance
            best_threshold = level

    return int(best_threshold)


def binarize_otsu(gray: np.ndarray) -> np.ndarray:
    """使用 Otsu 自动阈值进行二值化。"""

    return global_threshold(gray, otsu_threshold(gray))


def adaptive_binarize(gray_array: np.ndarray, window_size: int = 25, C: float = 10) -> np.ndarray:
    """局部自适应二值化。

    局部阈值的思想是：每个像素不再使用整张图共享的单一阈值，而是使用
    自己附近 window_size x window_size 区域的平均灰度 local_mean 作为参考。
    当 pixel < local_mean - C 时认为它比附近背景更暗，判定为文字 / 前景 0；
    否则判定为背景 255。

    全局阈值二值化在阴影、反光、局部过亮或过暗时容易失败，因为单一阈值
    无法同时适应整张图不同区域的光照。自适应二值化让每个像素参考自己的
    邻域平均值，因此更适合处理 OCR 图片中常见的光照不均问题。

    参数 window_size 越大，参考区域越大，结果通常更平滑，但可能丢失局部
    细节；window_size 越小，局部适应能力更强，但更容易受噪声影响。
    参数 C 用于调整阈值灵敏度：C 越大，阈值 local_mean - C 越低，越容易把
    像素判为背景；C 越小，越容易保留更多前景文字。

    OCR 场景通常需要统一成黑字白底，即文字 / 前景为 0、背景为 255，
    这样后续版面分析、去噪和识别模块可以稳定地理解前景与背景。
    """

    if window_size <= 0 or window_size % 2 == 0:
        raise ValueError("window_size 必须为正奇数")

    source = _ensure_gray(gray_array)
    height, width = source.shape
    radius = window_size // 2
    integral = build_integral_image(source)

    y0 = np.maximum(np.arange(height) - radius, 0)
    y1 = np.minimum(np.arange(height) + radius + 1, height)
    x0 = np.maximum(np.arange(width) - radius, 0)
    x1 = np.minimum(np.arange(width) + radius + 1, width)

    # 通过广播一次性得到所有像素对应窗口的左上/右下坐标。
    sums = (
        integral[y1[:, None], x1[None, :]]
        - integral[y0[:, None], x1[None, :]]
        - integral[y1[:, None], x0[None, :]]
        + integral[y0[:, None], x0[None, :]]
    )
    areas = (y1 - y0)[:, None] * (x1 - x0)[None, :]
    means = sums / areas
    binary = np.where(source < means - C, 0, 255)
    return binary.astype(np.uint8)


def save_binary(binary_array: np.ndarray, output_path: str) -> None:
    """将二值图保存到本地，自动创建输出目录。"""

    if not isinstance(binary_array, np.ndarray):
        raise TypeError("binary_array 必须是 np.ndarray")
    if binary_array.ndim != 2:
        raise ValueError("二值图必须是二维数组")

    output = Path(output_path)
    if output.parent != Path("."):
        output.parent.mkdir(parents=True, exist_ok=True)

    Image.fromarray(binary_array.astype(np.uint8, copy=False), mode="L").save(output)


def simple_global_binarize(gray_array: np.ndarray, threshold: int = 127) -> np.ndarray:
    """简单全局阈值二值化，作为自适应二值化的对照实验。

    全局阈值只用一个固定 threshold 判断整张图：pixel < threshold 输出 0，
    否则输出 255。当图片存在阴影、反光或局部光照不均时，单一阈值往往
    无法同时适应亮区和暗区，这也是 OCR 预处理常使用自适应阈值的原因。
    """

    if not 0 <= threshold <= 255:
        raise ValueError("threshold 必须在 0~255 之间")

    source = _ensure_gray(gray_array)
    binary = np.where(source < threshold, 0, 255)
    return binary.astype(np.uint8)


def global_threshold(gray: np.ndarray, threshold: int = 127) -> np.ndarray:
    """兼容旧接口：固定阈值二值化。"""

    return simple_global_binarize(gray, threshold)


def adaptive_mean_threshold(gray: np.ndarray, window_size: int = 31, c: float = 10.0) -> np.ndarray:
    """兼容旧接口：局部均值自适应二值化。"""

    return adaptive_binarize(gray, window_size=window_size, C=c)


def demo(input_path: str | Path, output_path: str | Path = "demo_binary.png") -> Path:
    """独立演示：读取图片并保存自适应二值化结果。"""

    with Image.open(input_path) as image:
        gray = to_grayscale_array(image)
    output = Path(output_path)
    save_binary(adaptive_binarize(gray), str(output))
    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="二值化 demo：python -m src.preprocess.binarize 图片路径")
    parser.add_argument("image")
    parser.add_argument("--output", default="demo_binary.png")
    args = parser.parse_args()
    print(demo(args.image, args.output))

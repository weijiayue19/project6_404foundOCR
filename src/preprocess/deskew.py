"""倾斜检测与矫正。

不使用 cv2.HoughLines。这里采用“水平投影方差最大化”估计文本行倾角：
候选角度旋转后，文字行越水平，行投影越集中、相邻行变化越明显。
PIL 仅用于旋转图片，不负责核心角度估计。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from src.preprocess.binarize import adaptive_mean_threshold
from src.preprocess.grayscale import image_from_gray_array, to_grayscale_array


def _score_horizontal_projection(binary: np.ndarray) -> float:
    """计算水平投影起伏分数，分数越大说明文字行越接近水平。"""

    ink = (binary < 128).astype(np.float32)
    projection = ink.sum(axis=1)
    if projection.size < 2:
        return 0.0
    diff = np.diff(projection)
    return float(np.mean(diff * diff) + np.var(projection) * 0.1)


def estimate_skew_angle(
    gray_or_binary: np.ndarray,
    angle_min: float = -8.0,
    angle_max: float = 8.0,
    angle_step: float = 0.5,
) -> float:
    """估计需要旋转矫正的角度。

    返回值为“应传给 PIL rotate 的角度”。例如文本整体顺时针倾斜 3 度时，
    通常返回约 +3 度，用 `image.rotate(angle)` 可逆时针转回水平。
    """

    if angle_step <= 0:
        raise ValueError("angle_step 必须大于 0")
    if angle_min > angle_max:
        raise ValueError("angle_min 不能大于 angle_max")

    source = gray_or_binary.astype(np.uint8, copy=False)
    if source.ndim != 2:
        raise ValueError("倾斜估计输入必须是二维数组")
    binary = np.where(source > 127, 255, 0).astype(np.uint8)

    best_angle = 0.0
    best_score = -1.0
    angles = np.arange(angle_min, angle_max + angle_step * 0.5, angle_step)
    base_image = image_from_gray_array(binary)
    for angle in angles:
        rotated = base_image.rotate(float(angle), expand=True, fillcolor=255)
        score = _score_horizontal_projection(np.asarray(rotated, dtype=np.uint8))
        if score > best_score:
            best_score = score
            best_angle = float(angle)
    return best_angle


def deskew_image(
    image: Image.Image,
    angle_min: float = -8.0,
    angle_max: float = 8.0,
    angle_step: float = 0.5,
    fill_color: int | tuple[int, int, int] = 255,
) -> Image.Image:
    """检测倾斜角并返回矫正后的图片。"""

    gray = to_grayscale_array(image)
    binary = adaptive_mean_threshold(gray, window_size=31, c=10)
    angle = estimate_skew_angle(binary, angle_min, angle_max, angle_step)
    if abs(angle) < angle_step * 0.5:
        return image.copy()
    return image.rotate(angle, expand=True, fillcolor=fill_color)


def demo(input_path: str | Path, output_path: str | Path = "demo_deskew.png") -> Path:
    """独立演示：读取图片并保存倾斜矫正结果。"""

    with Image.open(input_path) as image:
        result = deskew_image(image)
    output = Path(output_path)
    result.save(output)
    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="倾斜矫正 demo：python -m src.preprocess.deskew 图片路径")
    parser.add_argument("image")
    parser.add_argument("--output", default="demo_deskew.png")
    args = parser.parse_args()
    print(demo(args.image, args.output))

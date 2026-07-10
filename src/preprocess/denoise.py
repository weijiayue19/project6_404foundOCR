"""去噪算法。

不使用 cv2.medianBlur、scipy.signal.medfilt、skimage.filters 等现成滤波函数。
中值滤波、均值滤波和孤立点去除均通过 numpy/循环手写实现。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from src.preprocess.grayscale import image_from_gray_array, to_grayscale_array


def _ensure_2d_image(image_array: np.ndarray, name: str = "image_array") -> np.ndarray:
    """检查灰度图或二值图输入，并转换为 uint8 二维数组。"""

    if not isinstance(image_array, np.ndarray):
        raise TypeError(f"{name} 必须是 np.ndarray")
    if image_array.ndim != 2:
        raise ValueError(f"{name} 必须是二维灰度图或二值图数组")
    if image_array.size == 0:
        raise ValueError(f"{name} 不能为空")
    return np.clip(image_array, 0, 255).astype(np.uint8, copy=False)


def _validate_kernel_size(k_size: int) -> int:
    """校验中值滤波窗口大小，仅支持 3、5、7。"""

    if k_size not in {3, 5, 7}:
        raise ValueError("k_size 只支持 3、5、7")
    return k_size // 2


def median_filter(image_array: np.ndarray, k_size: int = 3) -> np.ndarray:
    """手写滑动窗口中值滤波。

    中值滤波非常适合去除椒盐噪声：椒盐噪声通常表现为孤立的纯黑点或纯白点，
    它们在局部窗口内属于极端值。把窗口内像素排序后取中位数，可以自然忽略
    这些极端值，使中心像素恢复到邻域中的主流灰度。

    相比均值滤波，中值滤波不会把黑白极端噪点直接参与平均，因此不容易把
    文字笔画边缘抹成灰色，更能保留 OCR 需要的文字边缘和笔画结构。

    处理过程：
    1. 使用 edge padding 复制边界像素，保证边缘位置也有完整 k_size x k_size 窗口；
    2. 滑动窗口逐像素扫描；
    3. 将窗口内像素展开并排序；
    4. 取排序后的中间值作为当前像素的新值。
    """

    radius = _validate_kernel_size(k_size)
    source = _ensure_2d_image(image_array)
    padded = np.pad(source, radius, mode="edge")
    height, width = source.shape
    output = np.empty_like(source)

    for y in range(height):
        for x in range(width):
            window = padded[y : y + k_size, x : x + k_size]
            sorted_values = np.sort(window.reshape(-1))
            output[y, x] = sorted_values[len(sorted_values) // 2]

    return output


def add_salt_pepper_noise(image_array: np.ndarray, amount: float = 0.02) -> np.ndarray:
    """为灰度图或二值图添加椒盐噪声，便于测试中值滤波效果。

    amount 表示被污染像素占总像素数的比例。被选中的像素一半设为 0
    （pepper，黑点），一半设为 255（salt，白点）。
    """

    if not 0 <= amount <= 1:
        raise ValueError("amount 必须在 0~1 之间")

    source = _ensure_2d_image(image_array)
    noisy = source.copy()
    total_pixels = noisy.size
    noise_pixels = int(round(total_pixels * amount))
    if noise_pixels == 0:
        return noisy

    rng = np.random.default_rng()
    indices = rng.choice(total_pixels, size=noise_pixels, replace=False)
    half = noise_pixels // 2
    flat = noisy.reshape(-1)
    flat[indices[:half]] = 0
    flat[indices[half:]] = 255
    return noisy


def save_image(array: np.ndarray, output_path: str | Path) -> None:
    """保存二维灰度图或二值图，并自动创建输出目录。"""

    source = _ensure_2d_image(array, name="array")
    output = Path(output_path)
    if output.parent != Path("."):
        output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(source, mode="L").save(output)


def mean_filter(gray: np.ndarray, kernel_size: int = 3) -> np.ndarray:
    """手写均值滤波，用窗口平均值平滑图像。"""

    radius = _validate_kernel_size(kernel_size)
    source = _ensure_2d_image(gray).astype(np.float32, copy=False)

    padded = np.pad(source, radius, mode="edge")
    height, width = source.shape
    output = np.empty((height, width), dtype=np.uint8)
    for y in range(height):
        for x in range(width):
            window = padded[y : y + kernel_size, x : x + kernel_size]
            output[y, x] = np.clip(np.rint(window.mean()), 0, 255)
    return output


def remove_isolated_pixels(binary: np.ndarray, min_same_neighbors: int = 2) -> np.ndarray:
    """移除二值图中的孤立噪点。

    对每个像素统计 8 邻域中与自身同色的数量；若数量小于阈值，则翻转为
    邻域中的主色。该方法对椒盐噪声和扫描件孤立黑点很直观。
    """

    if not 0 <= min_same_neighbors <= 8:
        raise ValueError("min_same_neighbors 必须在 0~8 之间")
    source = np.where(_ensure_2d_image(binary, name="binary") > 127, 255, 0).astype(np.uint8)

    padded = np.pad(source, 1, mode="edge")
    output = source.copy()
    height, width = source.shape
    for y in range(height):
        for x in range(width):
            neighbors = padded[y : y + 3, x : x + 3].copy().ravel()
            center = source[y, x]
            neighbors = np.delete(neighbors, 4)
            same = int(np.count_nonzero(neighbors == center))
            if same < min_same_neighbors:
                white_count = int(np.count_nonzero(neighbors == 255))
                output[y, x] = 255 if white_count >= 4 else 0
    return output


def demo(input_path: str | Path, output_path: str | Path = "demo_denoise.png", k_size: int = 3) -> Path:
    """独立演示：读取图片、添加椒盐噪声并保存中值滤波结果。"""

    with Image.open(input_path) as image:
        gray = to_grayscale_array(image)
    noisy = add_salt_pepper_noise(gray)
    result = image_from_gray_array(median_filter(noisy, k_size=k_size))
    output = Path(output_path)
    result.save(output)
    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="去噪 demo：python -m src.preprocess.denoise 图片路径")
    parser.add_argument("image")
    parser.add_argument("--output", default="demo_denoise.png")
    parser.add_argument("--k-size", type=int, default=3)
    args = parser.parse_args()
    print(demo(args.image, args.output, args.k_size))

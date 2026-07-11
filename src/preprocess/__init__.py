"""手写图像预处理算法包。

本包只使用 PIL 负责图片读写/旋转等基础能力，使用 numpy 做像素矩阵计算；
核心灰度、二值化和滤波均在各模块内实现，
不调用 OpenCV 的 cvtColor、threshold、medianBlur 等成品接口。
"""

from src.preprocess.binarize import adaptive_mean_threshold, binarize_otsu, global_threshold, otsu_threshold
from src.preprocess.denoise import mean_filter, median_filter, remove_isolated_pixels
from src.preprocess.grayscale import image_from_gray_array, rgb_to_gray, save_gray, to_grayscale, to_grayscale_array

__all__ = [
    "adaptive_mean_threshold",
    "binarize_otsu",
    "global_threshold",
    "image_from_gray_array",
    "mean_filter",
    "median_filter",
    "otsu_threshold",
    "remove_isolated_pixels",
    "rgb_to_gray",
    "save_gray",
    "to_grayscale",
    "to_grayscale_array",
]

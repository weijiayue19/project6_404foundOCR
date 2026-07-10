"""手写图像预处理算法包。

本包只使用 PIL 负责图片读写/旋转等基础能力，使用 numpy 做像素矩阵计算；
核心灰度、二值化、滤波、倾斜估计和缩放采样均在各模块内实现，
不调用 OpenCV 的 cvtColor、threshold、medianBlur、HoughLines、resize 等成品接口。
"""

from src.preprocess.binarize import adaptive_mean_threshold, binarize_otsu, global_threshold, otsu_threshold
from src.preprocess.denoise import mean_filter, median_filter, remove_isolated_pixels
from src.preprocess.deskew import deskew_image, estimate_skew_angle
from src.preprocess.grayscale import image_from_gray_array, rgb_to_gray, save_gray, to_grayscale, to_grayscale_array
from src.preprocess.resize import pyramid_resize, resize_limit_long_side, resize_to_height, resize_to_width

__all__ = [
    "adaptive_mean_threshold",
    "binarize_otsu",
    "deskew_image",
    "estimate_skew_angle",
    "global_threshold",
    "image_from_gray_array",
    "mean_filter",
    "median_filter",
    "otsu_threshold",
    "pyramid_resize",
    "remove_isolated_pixels",
    "resize_limit_long_side",
    "resize_to_height",
    "resize_to_width",
    "rgb_to_gray",
    "save_gray",
    "to_grayscale",
    "to_grayscale_array",
]

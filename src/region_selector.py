"""识别区域坐标转换与手写区域裁剪。

GUI 的 Canvas 显示的是缩放并居中的预览图，本模块负责在画布坐标和原图坐标
之间转换，便于框选局部 OCR 区域。核心逻辑不依赖 Tkinter，可单独测试。

图像坐标系说明：
- 原点 `(0, 0)` 在图片左上角；
- x 轴向右增大，范围通常是 `[0, image_width]`；
- y 轴向下增大，范围通常是 `[0, image_height]`；
- 本模块使用左闭右开矩形 `[left, right) x [top, bottom)`，正好对应 numpy
  切片 `array[top:bottom, left:right]`。

局部裁剪能减少 OCR 的无效计算：用户只关心图片中的某个表格、段落或截图区域时，
先裁掉无关背景和其他文字，可以降低输入尺寸、减少干扰内容，并可能提升识别准确率。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps


Box = tuple[int, int, int, int]


def normalize_box(x1: int, y1: int, x2: int, y2: int) -> Box:
    """把两个任意方向的点归一化为 `(left, top, right, bottom)`。

    用户鼠标框选不一定总是从左上拖到右下，也可能从右下往左上拖。
    坐标归一化的作用就是把两个点统一转换成左上角和右下角，便于后续
    边界裁剪和 numpy 切片。
    """

    left, right = sorted((int(round(x1)), int(round(x2))))
    top, bottom = sorted((int(round(y1)), int(round(y2))))
    return left, top, right, bottom


def validate_box(box: Box, image_width: int, image_height: int) -> Box:
    """校验并裁剪矩形框，防止坐标越界。

    边界裁剪会把坐标限制到图片范围内：x 在 `[0, image_width]`，
    y 在 `[0, image_height]`。如果裁剪后区域宽度或高度为 0，说明
    该框无法形成有效局部图像，会抛出清晰异常。
    """

    if image_width <= 0 or image_height <= 0:
        raise ValueError("图片宽高必须大于 0")

    left, top, right, bottom = normalize_box(*box)
    left = max(0, min(left, image_width))
    right = max(0, min(right, image_width))
    top = max(0, min(top, image_height))
    bottom = max(0, min(bottom, image_height))

    if right <= left or bottom <= top:
        raise ValueError("选择区域太小或完全超出图片范围，无法裁剪")
    return left, top, right, bottom


def crop_region(image_array: np.ndarray, x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
    """使用 numpy 数组切片手写裁剪局部图像。

    输入可以是二维灰度图 `(H, W)`，也可以是三维 RGB/RGBA 图 `(H, W, C)`。
    裁剪流程是：用户给出两个点 -> 坐标归一化 -> 限制在图片范围内 ->
    使用 `image_array[top:bottom, left:right]` 返回局部图像。

    这里不调用 OpenCV 的 ROI / GUI 接口，也不调用 PIL 的 `crop()`；PIL 只用于
    demo 读取和保存图片，核心裁剪由 numpy 切片完成。
    """

    if not isinstance(image_array, np.ndarray):
        raise TypeError("image_array 必须是 np.ndarray")
    if image_array.ndim not in {2, 3}:
        raise ValueError("image_array 必须是二维灰度图或三维彩色图数组")
    if image_array.size == 0:
        raise ValueError("image_array 不能为空")

    height, width = image_array.shape[:2]
    left, top, right, bottom = validate_box((x1, y1, x2, y2), width, height)
    return image_array[top:bottom, left:right].copy()


@dataclass(frozen=True, slots=True)
class PreviewTransform:
    """原图到画布预览图的缩放与偏移参数。"""

    original_width: int
    original_height: int
    preview_width: int
    preview_height: int
    offset_x: int
    offset_y: int

    @property
    def scale_x(self) -> float:
        return self.preview_width / self.original_width

    @property
    def scale_y(self) -> float:
        return self.preview_height / self.original_height

    def canvas_to_image_point(self, x: int, y: int) -> tuple[int, int]:
        """把画布坐标转换为原图坐标，并自动裁剪到图像范围内。"""

        image_x = round((x - self.offset_x) / self.scale_x)
        image_y = round((y - self.offset_y) / self.scale_y)
        image_x = max(0, min(image_x, self.original_width))
        image_y = max(0, min(image_y, self.original_height))
        return image_x, image_y

    def canvas_rect_to_image_rect(self, start: tuple[int, int], end: tuple[int, int]) -> tuple[int, int, int, int]:
        """把画布矩形转换为原图矩形 `(left, top, right, bottom)`。"""

        x1, y1 = self.canvas_to_image_point(*start)
        x2, y2 = self.canvas_to_image_point(*end)
        return validate_box(normalize_box(x1, y1, x2, y2), self.original_width, self.original_height)


def build_preview_transform(
    original_size: tuple[int, int],
    canvas_size: tuple[int, int],
    padding: int = 24,
) -> PreviewTransform:
    """根据原图尺寸和 Canvas 尺寸计算预览缩放参数。"""

    original_width, original_height = original_size
    canvas_width, canvas_height = canvas_size
    if original_width <= 0 or original_height <= 0:
        raise ValueError("原图尺寸必须大于 0")
    target_width = max(canvas_width - padding, 1)
    target_height = max(canvas_height - padding, 1)
    scale = min(target_width / original_width, target_height / original_height, 1.0)
    preview_width = max(int(round(original_width * scale)), 1)
    preview_height = max(int(round(original_height * scale)), 1)
    offset_x = (canvas_width - preview_width) // 2
    offset_y = (canvas_height - preview_height) // 2
    return PreviewTransform(original_width, original_height, preview_width, preview_height, offset_x, offset_y)


class RegionSelector:
    """与 Tkinter Canvas 配合使用的轻量框选状态机。"""

    def __init__(self) -> None:
        self.start: tuple[int, int] | None = None
        self.end: tuple[int, int] | None = None
        self.region: tuple[int, int, int, int] | None = None

    def begin(self, x: int, y: int) -> None:
        self.start = (x, y)
        self.end = (x, y)
        self.region = None

    def update(self, x: int, y: int) -> tuple[int, int, int, int] | None:
        if self.start is None:
            return None
        self.end = (x, y)
        left, right = sorted((self.start[0], x))
        top, bottom = sorted((self.start[1], y))
        return left, top, right, bottom

    def finish(self, x: int, y: int, transform: PreviewTransform) -> tuple[int, int, int, int]:
        if self.start is None:
            raise ValueError("尚未开始框选")
        self.end = (x, y)
        self.region = transform.canvas_rect_to_image_rect(self.start, self.end)
        return self.region

    def clear(self) -> None:
        self.start = None
        self.end = None
        self.region = None


def demo() -> tuple[int, int, int, int]:
    """独立演示：把预览框选坐标映射到原图坐标。"""

    transform = build_preview_transform((4000, 2000), (1000, 600))
    selector = RegionSelector()
    selector.begin(100, 100)
    return selector.finish(500, 300, transform)


def run_cli_demo(
    input_path: str | Path,
    output_path: str | Path,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
) -> Path:
    """命令行 demo：读取图片，按给定坐标裁剪并保存局部图像。"""

    with Image.open(input_path) as image:
        corrected = ImageOps.exif_transpose(image)
        array = np.asarray(corrected)

    cropped = crop_region(array, x1, y1, x2, y2)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(cropped.astype(np.uint8)).save(output)
    return output


def run_tkinter_gui_demo(input_path: str | Path, output_path: str | Path = "outputs/region/selected_region.png") -> None:
    """Tkinter GUI demo：鼠标框选区域，点击按钮后保存 numpy 裁剪结果。

    该 demo 只负责演示区域选择和裁剪，不调用 OpenCV GUI，也不强制调用 OCR。
    项目正式 GUI 的“识别选区”按钮逻辑已经通过 `OcrRequest.region` 接入
    `OcrEngine`，最终会只对裁剪后的局部图像进行 OCR。
    """

    import tkinter as tk
    from tkinter import messagebox, ttk

    from PIL import ImageTk

    source = ImageOps.exif_transpose(Image.open(input_path))
    if source.mode not in {"RGB", "RGBA", "L"}:
        source = source.convert("RGB")

    root = tk.Tk()
    root.title("区域裁剪 demo")
    root.geometry("900x650")
    root.minsize(700, 480)

    canvas = tk.Canvas(root, background="#ffffff", highlightthickness=0)
    canvas.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

    state: dict[str, object] = {
        "start": None,
        "end": None,
        "transform": None,
        "photo": None,
    }

    def redraw() -> None:
        canvas.delete("all")
        width = max(canvas.winfo_width(), 320)
        height = max(canvas.winfo_height(), 240)
        transform = build_preview_transform(source.size, (width, height), padding=24)
        preview = source.copy()
        preview.thumbnail((transform.preview_width, transform.preview_height), Image.Resampling.LANCZOS)
        photo = ImageTk.PhotoImage(preview)
        state["photo"] = photo
        state["transform"] = transform
        canvas.create_image(width // 2, height // 2, image=photo, anchor=tk.CENTER)

    def on_press(event: tk.Event) -> None:
        state["start"] = (event.x, event.y)
        state["end"] = (event.x, event.y)

    def on_drag(event: tk.Event) -> None:
        start = state.get("start")
        if start is None:
            return
        state["end"] = (event.x, event.y)
        canvas.delete("selection")
        left, top, right, bottom = normalize_box(start[0], start[1], event.x, event.y)
        canvas.create_rectangle(left, top, right, bottom, outline="#1e88e5", width=2, tags="selection")

    def save_selected_region() -> None:
        start = state.get("start")
        end = state.get("end")
        transform = state.get("transform")
        if start is None or end is None or not isinstance(transform, PreviewTransform):
            messagebox.showwarning("提示", "请先拖拽选择一个区域。")
            return
        try:
            box = transform.canvas_rect_to_image_rect(start, end)
            cropped = crop_region(np.asarray(source), *box)
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(cropped.astype(np.uint8)).save(output)
        except Exception as exc:
            messagebox.showerror("裁剪失败", str(exc))
            return
        messagebox.showinfo("裁剪完成", f"已保存：{output}")

    button_bar = ttk.Frame(root)
    button_bar.pack(fill=tk.X, padx=12, pady=(0, 12))
    ttk.Button(button_bar, text="保存选区", command=save_selected_region).pack(side=tk.LEFT)
    ttk.Label(button_bar, text="拖拽图片区域生成矩形框，保存时使用 numpy 切片裁剪。").pack(side=tk.LEFT, padx=12)

    canvas.bind("<Configure>", lambda _event: redraw())
    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_drag)
    redraw()
    root.mainloop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="区域裁剪 demo：使用 numpy 切片裁剪图片局部区域")
    parser.add_argument("image", nargs="?", help="输入图片路径")
    parser.add_argument("--output", default="outputs/region/cropped_region.png", help="裁剪输出路径")
    parser.add_argument("--box", nargs=4, type=int, metavar=("X1", "Y1", "X2", "Y2"), help="裁剪框两个点坐标")
    parser.add_argument("--gui", action="store_true", help="启动 Tkinter 框选 demo")
    args = parser.parse_args()

    if args.image is None:
        print(demo())
    elif args.gui:
        run_tkinter_gui_demo(args.image, args.output)
    elif args.box is not None:
        print(run_cli_demo(args.image, args.output, *args.box))
    else:
        parser.error("请提供 --box X1 Y1 X2 Y2，或使用 --gui 启动框选 demo")

"""Cross-platform monochrome pixel styling for the OCR desktop UI."""

from __future__ import annotations

import math
import random
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk


PAPER = "#f4f3ee"
PANEL = "#ffffff"
INK = "#171717"
MUTED = "#6f6f69"
SOFT = "#e7e5de"
GRID = "#d1cfc6"
SUCCESS = "#315c3a"
ERROR = "#9b2f2f"


# One shared silhouette keeps the mascot consistent at every size.  ``.`` is
# the eye cut-out; spaces remain transparent.
DINO_SPRITE = (
    "          #######  ",
    "         ######### ",
    "         ##.###### ",
    "         ######### ",
    "         ######### ",
    "         ####      ",
    "         #######   ",
    "        #####      ",
    "#      ######      ",
    "##    ########     ",
    "###  #########     ",
    "############## ##  ",
    " ############  ##  ",
    "  ##########       ",
    "   ########        ",
    "    ###  ###       ",
    "    ##    ##       ",
    "    ##    ##       ",
)


def draw_pixel_dino(
    canvas: tk.Canvas,
    x: int,
    y: int,
    pixel: int,
    *,
    foreground: str = INK,
    eye_color: str = PANEL,
    tag: str | tuple[str, ...] | None = None,
) -> None:
    """Draw the shared dinosaur sprite from its top-left pixel."""

    item_options = {"tag": tag} if tag is not None else {}
    for row_index, row in enumerate(DINO_SPRITE):
        for column_index, cell in enumerate(row):
            if cell not in {"#", "."}:
                continue
            color = eye_color if cell == "." else foreground
            left = x + column_index * pixel
            top = y + row_index * pixel
            canvas.create_rectangle(
                left,
                top,
                left + pixel,
                top + pixel,
                fill=color,
                outline=color,
                width=0,
                **item_options,
            )


def draw_pixel_border(
    canvas: tk.Canvas,
    width: int,
    height: int,
    *,
    line_color: str = GRID,
    accent_color: str = INK,
    tag: str = "pixel-border",
) -> None:
    """Draw an orthogonal stepped border with chunky pixel corner anchors."""

    canvas.delete(tag)
    draw_pixel_box(
        canvas,
        1,
        1,
        max(1, width - 2),
        max(1, height - 2),
        line_color=line_color,
        accent_color=accent_color,
        tag=tag,
        pixel=4,
        width=2,
    )


def draw_pixel_box(
    canvas: tk.Canvas,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    *,
    fill: str | None = None,
    line_color: str = GRID,
    accent_color: str = INK,
    tag: str = "pixel-box",
    pixel: int = 4,
    width: int = 2,
    show_corners: bool = True,
) -> None:
    """Draw a stepped, blocky rectangle inside an arbitrary canvas region."""

    canvas.delete(tag)
    left = int(round(min(x1, x2)))
    top = int(round(min(y1, y2)))
    right = int(round(max(x1, x2)))
    bottom = int(round(max(y1, y2)))
    box_width = right - left
    box_height = bottom - top
    if box_width < 18 or box_height < 18:
        if fill is not None:
            stroke = max(1, int(width))
            canvas.create_rectangle(
                left,
                top,
                right,
                bottom,
                fill=line_color,
                outline="",
                width=0,
                tag=tag,
            )
            canvas.create_rectangle(
                left + stroke,
                top + stroke,
                right - stroke,
                bottom - stroke,
                fill=fill,
                outline="",
                width=0,
                tag=tag,
            )
            return
        canvas.create_rectangle(
            left,
            top,
            right,
            bottom,
            fill=fill or "",
            outline=line_color,
            width=width,
            tag=tag,
        )
        return

    p = max(2, int(pixel))
    step = min(max(p * 3, 10), max(10, min(box_width, box_height) // 3))
    stroke = max(1, int(width))

    def outline_path(inset: int = 0) -> tuple[int, ...]:
        inner_left = left + inset
        inner_top = top + inset
        inner_right = right - inset
        inner_bottom = bottom - inset
        inner_width = max(1, inner_right - inner_left)
        inner_height = max(1, inner_bottom - inner_top)
        inner_step = min(max(p * 3, 10), max(10, min(inner_width, inner_height) // 3))
        return (
            inner_left + inner_step,
            inner_top,
            inner_right - inner_step,
            inner_top,
            inner_right - inner_step,
            inner_top + p,
            inner_right - p,
            inner_top + p,
            inner_right - p,
            inner_top + inner_step,
            inner_right,
            inner_top + inner_step,
            inner_right,
            inner_bottom - inner_step,
            inner_right - p,
            inner_bottom - inner_step,
            inner_right - p,
            inner_bottom - p,
            inner_right - inner_step,
            inner_bottom - p,
            inner_right - inner_step,
            inner_bottom,
            inner_left + inner_step,
            inner_bottom,
            inner_left + inner_step,
            inner_bottom - p,
            inner_left + p,
            inner_bottom - p,
            inner_left + p,
            inner_bottom - inner_step,
            inner_left,
            inner_bottom - inner_step,
            inner_left,
            inner_top + inner_step,
            inner_left + p,
            inner_top + inner_step,
            inner_left + p,
            inner_top + p,
            inner_left + inner_step,
            inner_top + p,
            inner_left + inner_step,
            inner_top,
        )

    outline = outline_path()
    if fill is not None and hasattr(canvas, "create_polygon"):
        canvas.create_polygon(*outline, fill=line_color, outline="", width=0, tag=tag)
        canvas.create_polygon(*outline_path(stroke), fill=fill, outline="", width=0, tag=tag)
    else:
        if fill is not None:
            canvas.create_rectangle(
                left + p,
                top + p,
                right - p,
                bottom - p,
                fill=fill,
                outline=fill,
                width=0,
                tag=tag,
            )
        canvas.create_line(*outline, fill=line_color, width=stroke, tag=tag)

    if show_corners:
        corner_blocks = (
            (left + p, top + step, left + p * 2, top + step + p),
            (left + step, top + p, left + step + p, top + p * 2),
            (right - p * 2, top + step, right - p, top + step + p),
            (right - step - p, top + p, right - step, top + p * 2),
            (left + p, bottom - step - p, left + p * 2, bottom - step),
            (left + step, bottom - p * 2, left + step + p, bottom - p),
            (right - p * 2, bottom - step - p, right - p, bottom - step),
            (right - step - p, bottom - p * 2, right - step, bottom - p),
        )
        for bounds in corner_blocks:
            canvas.create_rectangle(
                *bounds,
                fill=accent_color,
                outline=accent_color,
                width=0,
                tag=tag,
            )


class PixelBorderFrame(tk.Frame):
    """Content frame backed by a scalable stepped pixel border."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        padding: int | tuple[int, int] = 12,
        background: str = PANEL,
    ) -> None:
        if isinstance(padding, tuple):
            padx, pady = padding
        else:
            padx = pady = padding
        super().__init__(
            master,
            background=background,
            borderwidth=0,
            highlightthickness=0,
            padx=padx,
            pady=pady,
        )
        self._border_canvas = tk.Canvas(
            self,
            background=background,
            borderwidth=0,
            highlightthickness=0,
        )
        self._border_canvas.place(
            x=-padx,
            y=-pady,
            relwidth=1,
            relheight=1,
            width=padx * 2,
            height=pady * 2,
        )
        self.bind("<Configure>", self._redraw_pixel_border, add="+")

    def _redraw_pixel_border(self, _event: tk.Event | None = None) -> None:
        draw_pixel_border(
            self._border_canvas,
            self.winfo_width(),
            self.winfo_height(),
        )


class PixelScrollbar(tk.Canvas):
    """Small canvas-drawn scrollbar that avoids native arrow-button styling."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        orient: str = tk.VERTICAL,
        command: object | None = None,
        background: str = PANEL,
        thickness: int = 12,
        thumb_fill: str = INK,
        thumb_line: str | None = None,
        thumb_accent: str = PANEL,
        always_show_thumb: bool = False,
    ) -> None:
        self.orient = tk.HORIZONTAL if str(orient).lower().startswith("h") else tk.VERTICAL
        self.command = command
        self.thickness = thickness
        self.thumb_fill = thumb_fill
        self.thumb_line = thumb_line or thumb_fill
        self.thumb_accent = thumb_accent
        self.always_show_thumb = always_show_thumb
        self._first = 0.0
        self._last = 1.0
        self._drag_offset = 0
        self._dragging = False
        size_options = (
            {"height": thickness, "width": 120}
            if self.orient == tk.HORIZONTAL
            else {"width": thickness, "height": 120}
        )
        super().__init__(
            master,
            background=background,
            borderwidth=0,
            highlightthickness=0,
            bd=0,
            cursor="sb_h_double_arrow" if self.orient == tk.HORIZONTAL else "sb_v_double_arrow",
            **size_options,
        )
        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<B1-Motion>", self._on_drag, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")

    def set(self, first: float | str, last: float | str) -> None:
        self._first = min(1.0, max(0.0, float(first)))
        self._last = min(1.0, max(self._first, float(last)))
        self._redraw()

    def _redraw(self, _event: tk.Event | None = None) -> None:
        self.delete("all")
        width = max(self.winfo_width(), self.thickness)
        height = max(self.winfo_height(), self.thickness)
        visible = self._last - self._first
        if self.orient == tk.HORIZONTAL:
            center = height // 2
            self.create_rectangle(2, center - 1, width - 2, center + 1, fill=GRID, outline=GRID)
            for x in range(10, width - 10, 34):
                self.create_rectangle(x, center - 3, x + 2, center + 3, fill=SOFT, outline=SOFT)
        else:
            center = width // 2
            self.create_rectangle(center - 1, 2, center + 1, height - 2, fill=GRID, outline=GRID)
            for y in range(10, height - 10, 34):
                self.create_rectangle(center - 3, y, center + 3, y + 2, fill=SOFT, outline=SOFT)

        if visible >= 0.995 and not self.always_show_thumb:
            return
        x1, y1, x2, y2 = self._thumb_bounds()
        draw_pixel_box(
            self,
            x1,
            y1,
            x2,
            y2,
            fill=self.thumb_fill,
            line_color=self.thumb_line,
            accent_color=self.thumb_accent,
            tag="scrollbar-thumb",
            pixel=3,
            width=1,
        )

    def _thumb_bounds(self) -> tuple[int, int, int, int]:
        width = max(self.winfo_width(), self.thickness)
        height = max(self.winfo_height(), self.thickness)
        margin = 1
        visible = min(1.0, max(0.0, self._last - self._first))
        if self.orient == tk.HORIZONTAL:
            track_length = max(1, width - margin * 2)
            thumb_length = min(track_length, max(24, int(track_length * visible)))
            travel = max(1, track_length - thumb_length)
            left = margin + int(round(travel * self._first / max(0.001, 1.0 - visible)))
            return left, 2, left + thumb_length, height - 2

        track_length = max(1, height - margin * 2)
        thumb_length = min(track_length, max(28, int(track_length * visible)))
        travel = max(1, track_length - thumb_length)
        top = margin + int(round(travel * self._first / max(0.001, 1.0 - visible)))
        return 2, top, width - 2, top + thumb_length

    def _event_position(self, event: tk.Event) -> int:
        return int(event.x if self.orient == tk.HORIZONTAL else event.y)

    def _on_press(self, event: tk.Event) -> None:
        if self._last - self._first >= 0.995:
            return
        position = self._event_position(event)
        x1, y1, x2, y2 = self._thumb_bounds()
        start = x1 if self.orient == tk.HORIZONTAL else y1
        end = x2 if self.orient == tk.HORIZONTAL else y2
        if start <= position <= end:
            self._dragging = True
            self._drag_offset = position - start
            return
        self._move_thumb_to(position - (end - start) // 2)

    def _on_drag(self, event: tk.Event) -> None:
        if not self._dragging:
            return
        self._move_thumb_to(self._event_position(event) - self._drag_offset)

    def _on_release(self, _event: tk.Event) -> None:
        self._dragging = False

    def _move_thumb_to(self, thumb_start: int) -> None:
        visible = min(1.0, max(0.0, self._last - self._first))
        x1, y1, x2, y2 = self._thumb_bounds()
        if self.orient == tk.HORIZONTAL:
            track_length = max(1, self.winfo_width() - 2)
            thumb_length = x2 - x1
        else:
            track_length = max(1, self.winfo_height() - 2)
            thumb_length = y2 - y1
        travel = max(1, track_length - thumb_length)
        fraction = min(1.0 - visible, max(0.0, (thumb_start - 1) / travel * (1.0 - visible)))
        if self.command is not None:
            self.command("moveto", fraction)


class CutCornerButton(tk.Canvas):
    """Canvas button with a small square removed from each corner."""

    VARIANTS = {
        "default": {
            "background": PANEL,
            "foreground": INK,
            "border": INK,
            "border_width": 2,
            "active": "#eceae3",
            "pressed": SOFT,
            "disabled_background": "#deddd7",
            "disabled_foreground": "#92918b",
            "disabled_border": GRID,
            "padding": (12, 8),
        },
        "primary": {
            "background": INK,
            "foreground": PANEL,
            "border": INK,
            "border_width": 1,
            "active": "#303030",
            "pressed": "#424242",
            "disabled_background": "#a5a49f",
            "disabled_foreground": "#e9e8e2",
            "disabled_border": "#a5a49f",
            "padding": (14, 9),
        },
        "quiet": {
            "background": PAPER,
            "foreground": INK,
            "border": GRID,
            "border_width": 1,
            "active": "#eceae3",
            "pressed": SOFT,
            "disabled_background": SOFT,
            "disabled_foreground": MUTED,
            "disabled_border": GRID,
            "padding": (10, 7),
        },
    }

    def __init__(
        self,
        master: tk.Misc,
        *,
        text: str,
        command: object | None = None,
        variant: str = "default",
        font_family: str = "TkDefaultFont",
        state: str = tk.NORMAL,
        outer_background: str = PAPER,
        takefocus: bool | str = True,
        min_width: int | None = None,
        min_height: int | None = None,
    ) -> None:
        self._text = text
        self._command = command
        self._variant = variant if variant in self.VARIANTS else "default"
        self._state = str(state)
        self._outer_background = outer_background
        self._min_width = min_width
        self._min_height = min_height
        self._hover = False
        self._pressed = False
        self._font = tkfont.Font(family=font_family, size=10, weight="bold")
        self._cut_size = max(5, int(round(self._font.metrics("linespace") * 0.38)))
        self._target_width, self._target_height = self._measure()

        super().__init__(
            master,
            width=self._target_width,
            height=self._target_height,
            background=outer_background,
            borderwidth=0,
            highlightthickness=0,
            bd=0,
            cursor="hand2" if self._state != tk.DISABLED else "arrow",
            takefocus=takefocus,
        )
        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Motion>", self._on_motion, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.bind("<Return>", self._on_keyboard_invoke, add="+")
        self.bind("<space>", self._on_keyboard_invoke, add="+")
        self.bind("<FocusIn>", self._redraw, add="+")
        self.bind("<FocusOut>", self._redraw, add="+")
        self._redraw()

    def configure(self, cnf: object | None = None, **kwargs: object) -> None:
        if isinstance(cnf, str):
            return super().configure(cnf)
        if cnf:
            kwargs.update(dict(cnf))  # type: ignore[arg-type]

        should_resize = False
        if "text" in kwargs:
            self._text = str(kwargs.pop("text"))
            should_resize = True
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "state" in kwargs:
            self._state = str(kwargs.pop("state"))
        if "variant" in kwargs:
            variant = str(kwargs.pop("variant"))
            self._variant = variant if variant in self.VARIANTS else "default"
            should_resize = True
        if "outer_background" in kwargs:
            self._outer_background = str(kwargs.pop("outer_background"))
            kwargs["background"] = self._outer_background
        if "min_width" in kwargs:
            min_width = kwargs.pop("min_width")
            self._min_width = int(min_width) if min_width is not None else None
            should_resize = True
        if "min_height" in kwargs:
            min_height = kwargs.pop("min_height")
            self._min_height = int(min_height) if min_height is not None else None
            should_resize = True
        if kwargs:
            super().configure(**kwargs)

        if should_resize:
            self._target_width, self._target_height = self._measure()
            super().configure(width=self._target_width, height=self._target_height)
        self._sync_cursor()
        self._redraw()

    config = configure

    def cget(self, key: str) -> object:
        if key == "text":
            return self._text
        if key == "command":
            return self._command
        if key == "state":
            return self._state
        if key == "variant":
            return self._variant
        if key == "outer_background":
            return self._outer_background
        if key == "min_width":
            return self._min_width
        if key == "min_height":
            return self._min_height
        return super().cget(key)

    def invoke(self) -> object | None:
        if self._is_disabled() or not callable(self._command):
            return None
        return self._command()

    def _measure(self) -> tuple[int, int]:
        colors = self.VARIANTS[self._variant]
        padx, pady = colors["padding"]
        width = max(38, self._font.measure(self._text) + padx * 2)
        height = max(32, self._font.metrics("linespace") + pady * 2)
        if self._min_width is not None:
            width = max(width, self._min_width)
        if self._min_height is not None:
            height = max(height, self._min_height)
        return width, height

    def _is_disabled(self) -> bool:
        return self._state == tk.DISABLED

    def _sync_cursor(self) -> None:
        if self._is_disabled():
            self._hover = False
            self._pressed = False
        super().configure(cursor="arrow" if self._is_disabled() else "hand2")

    def _shape_path(self, width: int, height: int, inset: int = 0) -> tuple[int, ...]:
        left = inset
        top = inset
        right = max(left, width - inset)
        bottom = max(top, height - inset)
        cut = min(
            self._cut_size,
            max(1, (right - left) // 3),
            max(1, (bottom - top) // 3),
        )
        return (
            left + cut,
            top,
            right - cut,
            top,
            right - cut,
            top + cut,
            right,
            top + cut,
            right,
            bottom - cut,
            right - cut,
            bottom - cut,
            right - cut,
            bottom,
            left + cut,
            bottom,
            left + cut,
            bottom - cut,
            left,
            bottom - cut,
            left,
            top + cut,
            left + cut,
            top + cut,
            left + cut,
            top,
        )

    def _contains_event(self, event: tk.Event) -> bool:
        width = max(1, self.winfo_width())
        height = max(1, self.winfo_height())
        cut = min(self._cut_size, max(1, width // 3), max(1, height // 3))
        inside_bounds = 0 <= event.x <= width and 0 <= event.y <= height
        inside_cutout = (
            (event.x <= cut and event.y <= cut)
            or (event.x >= width - cut and event.y <= cut)
            or (event.x <= cut and event.y >= height - cut)
            or (event.x >= width - cut and event.y >= height - cut)
        )
        return inside_bounds and not inside_cutout

    def _redraw(self, _event: tk.Event | None = None) -> None:
        self.delete("all")
        width = max(self._target_width, self.winfo_width())
        height = max(self._target_height, self.winfo_height())
        colors = self.VARIANTS[self._variant]
        if self._is_disabled():
            fill = str(colors["disabled_background"])
            foreground = str(colors["disabled_foreground"])
            border = str(colors["disabled_border"])
        elif self._pressed:
            fill = str(colors["pressed"])
            foreground = str(colors["foreground"])
            border = str(colors["border"])
        elif self._hover:
            fill = str(colors["active"])
            foreground = str(colors["foreground"])
            border = str(colors["border"])
        else:
            fill = str(colors["background"])
            foreground = str(colors["foreground"])
            border = str(colors["border"])

        border_width = max(0, int(colors["border_width"]))
        path = self._shape_path(width - 1, height - 1)
        if border_width > 0:
            self.create_polygon(*path, fill=border, outline="", width=0)
            inset_path = self._shape_path(width - 1, height - 1, border_width)
            self.create_polygon(*inset_path, fill=fill, outline="", width=0)
        else:
            self.create_polygon(*path, fill=fill, outline="", width=0)
        self.create_text(
            width // 2,
            height // 2,
            text=self._text,
            fill=foreground,
            font=self._font,
            anchor=tk.CENTER,
        )

    def _on_enter(self, event: tk.Event) -> None:
        if not self._is_disabled():
            self._hover = self._contains_event(event)
            self._redraw()

    def _on_motion(self, event: tk.Event) -> None:
        if self._is_disabled():
            return
        hover = self._contains_event(event)
        if hover != self._hover:
            self._hover = hover
            self._redraw()

    def _on_leave(self, _event: tk.Event) -> None:
        self._hover = False
        self._pressed = False
        self._redraw()

    def _on_press(self, event: tk.Event) -> None:
        if self._is_disabled() or not self._contains_event(event):
            return
        self.focus_set()
        self._pressed = True
        self._redraw()

    def _on_release(self, event: tk.Event) -> None:
        should_invoke = self._pressed and self._contains_event(event)
        self._pressed = False
        self._redraw()
        if should_invoke:
            self.invoke()

    def _on_keyboard_invoke(self, _event: tk.Event) -> str:
        self.invoke()
        return "break"


class PixelKeyButton(tk.Canvas):
    """Canvas-drawn keycap button for start-screen mascot actions."""

    def __init__(
        self,
        master: tk.Misc,
        *,
        key: str,
        command: object | None = None,
        font_family: str = "TkDefaultFont",
        outer_background: str = PANEL,
        size: int = 58,
        state: str = tk.NORMAL,
    ) -> None:
        self._key = key[:1].upper() or "?"
        self._command = command
        self._outer_background = outer_background
        self._size = max(48, int(size))
        self._state = str(state)
        self._hover = False
        self._pressed = False
        self._font = tkfont.Font(family=font_family, size=23, weight="bold")
        super().__init__(
            master,
            width=self._size,
            height=self._size,
            background=outer_background,
            borderwidth=0,
            highlightthickness=0,
            bd=0,
            cursor="hand2" if self._state != tk.DISABLED else "arrow",
            takefocus=True,
        )
        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<Enter>", self._on_enter, add="+")
        self.bind("<Leave>", self._on_leave, add="+")
        self.bind("<ButtonPress-1>", self._on_press, add="+")
        self.bind("<ButtonRelease-1>", self._on_release, add="+")
        self.bind("<Return>", self._on_keyboard_invoke, add="+")
        self.bind("<space>", self._on_keyboard_invoke, add="+")
        self.bind("<FocusIn>", self._redraw, add="+")
        self.bind("<FocusOut>", self._redraw, add="+")
        self._redraw()

    def configure(self, cnf: object | None = None, **kwargs: object) -> None:
        if isinstance(cnf, str):
            return super().configure(cnf)
        if cnf:
            kwargs.update(dict(cnf))  # type: ignore[arg-type]
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "key" in kwargs:
            self._key = str(kwargs.pop("key"))[:1].upper() or "?"
        if "state" in kwargs:
            self._state = str(kwargs.pop("state"))
            self._sync_cursor()
        if "outer_background" in kwargs:
            self._outer_background = str(kwargs.pop("outer_background"))
            kwargs["background"] = self._outer_background
        if kwargs:
            super().configure(**kwargs)
        self._redraw()

    config = configure

    def cget(self, key: str) -> object:
        if key == "command":
            return self._command
        if key == "key":
            return self._key
        if key == "state":
            return self._state
        if key == "outer_background":
            return self._outer_background
        return super().cget(key)

    def invoke(self) -> object | None:
        if self._is_disabled() or not callable(self._command):
            return None
        return self._command()

    def _is_disabled(self) -> bool:
        return self._state == tk.DISABLED

    def _sync_cursor(self) -> None:
        if self._is_disabled():
            self._hover = False
            self._pressed = False
        super().configure(cursor="arrow" if self._is_disabled() else "hand2")

    def _redraw(self, _event: tk.Event | None = None) -> None:
        self.delete("all")
        width = max(self._size, self.winfo_width())
        height = max(self._size, self.winfo_height())
        pressed_offset = 4 if self._pressed and not self._is_disabled() else 0
        fill = "#ffffff" if not self._hover else "#f7f6f1"
        foreground = INK
        if self._is_disabled():
            fill = SOFT
            foreground = MUTED

        draw_pixel_box(
            self,
            7,
            10,
            width - 5,
            height - 3,
            fill="#686866",
            line_color=INK,
            accent_color=INK,
            tag="key-shadow",
            pixel=4,
            width=2,
        )
        draw_pixel_box(
            self,
            3,
            3 + pressed_offset,
            width - 8,
            height - 10 + pressed_offset,
            fill=fill,
            line_color=INK,
            accent_color=INK,
            tag="key-top",
            pixel=4,
            width=3,
        )
        self.create_line(
            14,
            15 + pressed_offset,
            width - 19,
            15 + pressed_offset,
            fill="#d9d9d6",
            width=3,
            tag="key-detail",
        )
        self.create_line(
            14,
            height - 20 + pressed_offset,
            width - 20,
            height - 20 + pressed_offset,
            fill="#d1d0ca",
            width=3,
            tag="key-detail",
        )
        self.create_text(
            width // 2,
            height // 2 - 3 + pressed_offset,
            text=self._key,
            fill=foreground,
            font=self._font,
            anchor=tk.CENTER,
            tag="key-letter",
        )

    def _on_enter(self, _event: tk.Event) -> None:
        if not self._is_disabled():
            self._hover = True
            self._redraw()

    def _on_leave(self, _event: tk.Event) -> None:
        self._hover = False
        self._pressed = False
        self._redraw()

    def _on_press(self, _event: tk.Event) -> None:
        if self._is_disabled():
            return
        self.focus_set()
        self._pressed = True
        self._redraw()

    def _on_release(self, _event: tk.Event) -> None:
        should_invoke = self._pressed and not self._is_disabled()
        self._pressed = False
        self._redraw()
        if should_invoke:
            self.invoke()

    def _on_keyboard_invoke(self, _event: tk.Event) -> str:
        self.invoke()
        return "break"


class PixelKeyPanel(tk.Canvas):
    """Dedicated start-screen key area with a long-press manual-drive lock."""

    HOLD_MS = 620

    def __init__(
        self,
        master: tk.Misc,
        *,
        boost_command: object | None = None,
        jump_command: object | None = None,
        on_lock_change: object | None = None,
        font_family: str = "TkDefaultFont",
        outer_background: str = PAPER,
        width: int = 154,
        height: int = 78,
    ) -> None:
        self._outer_background = outer_background
        self._panel_width = max(132, int(width))
        self._panel_height = max(72, int(height))
        self._locked = False
        self._hold_after_id: str | None = None
        self._on_lock_change = on_lock_change
        super().__init__(
            master,
            width=self._panel_width,
            height=self._panel_height,
            background=outer_background,
            borderwidth=0,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )
        self.j_button = PixelKeyButton(
            self,
            key="J",
            command=boost_command,
            font_family=font_family,
            outer_background=outer_background,
            size=54,
            state=tk.DISABLED,
        )
        self.k_button = PixelKeyButton(
            self,
            key="K",
            command=jump_command,
            font_family=font_family,
            outer_background=outer_background,
            size=54,
            state=tk.DISABLED,
        )
        self.j_button.place(x=18, y=12)
        self.k_button.place(x=82, y=12)
        for button in (self.j_button, self.k_button):
            button.bind("<ButtonPress-1>", self._on_blank_press, add="+")
            button.bind("<ButtonRelease-1>", self._cancel_hold, add="+")
            button.bind("<Leave>", self._cancel_hold, add="+")
        self.bind("<Configure>", self._redraw, add="+")
        self.bind("<ButtonPress-1>", self._on_blank_press, add="+")
        self.bind("<ButtonRelease-1>", self._cancel_hold, add="+")
        self.bind("<Leave>", self._cancel_hold, add="+")
        self._redraw()

    def set_locked(self, locked: bool) -> None:
        next_locked = bool(locked)
        if next_locked == self._locked:
            return
        self._locked = next_locked
        button_state = tk.NORMAL if self._locked else tk.DISABLED
        self.j_button.configure(state=button_state)
        self.k_button.configure(state=button_state)
        self._redraw()
        if callable(self._on_lock_change):
            self._on_lock_change(self._locked)

    def is_locked(self) -> bool:
        return self._locked

    def _on_blank_press(self, _event: tk.Event) -> None:
        self._cancel_hold()
        self._hold_after_id = self.after(self.HOLD_MS, self._toggle_locked)

    def _toggle_locked(self) -> None:
        self._hold_after_id = None
        self.set_locked(not self._locked)

    def _cancel_hold(self, _event: tk.Event | None = None) -> None:
        if self._hold_after_id is None:
            return
        try:
            self.after_cancel(self._hold_after_id)
        except tk.TclError:
            pass
        self._hold_after_id = None

    def _redraw(self, _event: tk.Event | None = None) -> None:
        self.delete("panel-border")
        width = max(self._panel_width, self.winfo_width())
        height = max(self._panel_height, self.winfo_height())
        color = INK if self._locked else MUTED
        border_options = {
            "outline": color,
            "width": 2,
            "tag": "panel-border",
        }
        if not self._locked:
            border_options["dash"] = (4, 4)
        self.create_rectangle(2, 2, width - 3, height - 3, **border_options)
        if self._locked:
            for x, y in ((8, 8), (width - 14, 8), (8, height - 14), (width - 14, height - 14)):
                self.create_rectangle(
                    x,
                    y,
                    x + 6,
                    y + 6,
                    fill=INK,
                    outline=INK,
                    width=0,
                    tag="panel-border",
                )


def configure_pixel_theme(root: tk.Misc, font_family: str) -> ttk.Style:
    """Apply a predictable ttk theme on both macOS and Windows."""

    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    root.configure(background=PAPER)
    root.option_add("*TCombobox*Listbox.background", PANEL)
    root.option_add("*TCombobox*Listbox.foreground", INK)
    root.option_add("*TCombobox*Listbox.selectBackground", PANEL)
    root.option_add("*TCombobox*Listbox.selectForeground", INK)
    root.option_add("*TCombobox*Listbox.selectBorderWidth", 0)
    style.configure(".", font=(font_family, 10), background=PAPER, foreground=INK)
    style.configure("App.TFrame", background=PAPER)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Rail.TFrame", background=PANEL)
    style.configure("Status.TFrame", background=INK)

    style.configure("TLabel", background=PAPER, foreground=INK)
    style.configure("Panel.TLabel", background=PANEL, foreground=INK)
    style.configure("Muted.TLabel", background=PAPER, foreground=MUTED)
    style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED)
    style.configure("Status.TLabel", background=INK, foreground=PANEL)
    style.configure("Eyebrow.TLabel", background=PAPER, foreground=MUTED, font=(font_family, 9, "bold"))
    style.configure("Title.TLabel", background=PAPER, foreground=INK, font=(font_family, 25, "bold"))
    style.configure("PanelTitle.TLabel", background=PANEL, foreground=INK, font=(font_family, 12, "bold"))
    style.configure("CardTitle.TLabel", background=PANEL, foreground=INK, font=(font_family, 15, "bold"))

    style.configure(
        "Pixel.TButton",
        background=PANEL,
        foreground=INK,
        bordercolor=INK,
        lightcolor=INK,
        darkcolor=INK,
        borderwidth=1,
        relief="flat",
        padding=(12, 8),
        font=(font_family, 10, "bold"),
    )
    style.map(
        "Pixel.TButton",
        background=[("pressed", SOFT), ("active", "#eceae3"), ("disabled", "#deddd7")],
        foreground=[("disabled", "#92918b")],
        bordercolor=[("focus", INK), ("disabled", GRID)],
    )
    style.configure(
        "Icon.Pixel.TButton",
        background=PANEL,
        bordercolor=GRID,
        lightcolor=GRID,
        darkcolor=GRID,
        borderwidth=1,
        relief="flat",
        padding=(7, 7),
    )
    style.map(
        "Icon.Pixel.TButton",
        background=[("pressed", SOFT), ("active", "#eceae3"), ("disabled", "#f0efea")],
        bordercolor=[("focus", INK), ("active", INK), ("disabled", GRID)],
    )
    style.configure(
        "Primary.Pixel.TButton",
        background=INK,
        foreground=PANEL,
        bordercolor=INK,
        lightcolor=INK,
        darkcolor=INK,
        borderwidth=1,
        relief="flat",
        padding=(14, 9),
        font=(font_family, 10, "bold"),
    )
    style.map(
        "Primary.Pixel.TButton",
        background=[("pressed", "#424242"), ("active", "#303030"), ("disabled", "#a5a49f")],
        foreground=[("disabled", "#e9e8e2")],
    )
    style.configure(
        "Quiet.Pixel.TButton",
        background=PAPER,
        foreground=INK,
        bordercolor=GRID,
        lightcolor=GRID,
        darkcolor=GRID,
        borderwidth=1,
        relief="flat",
        padding=(10, 7),
    )
    style.configure(
        "Flat.Pixel.TButton",
        background=PAPER,
        foreground=INK,
        bordercolor=PAPER,
        lightcolor=PAPER,
        darkcolor=PAPER,
        borderwidth=0,
        relief="flat",
        padding=(10, 7),
        font=(font_family, 10, "bold"),
    )
    style.map(
        "Flat.Pixel.TButton",
        background=[("pressed", SOFT), ("active", "#eceae3"), ("disabled", PAPER)],
        foreground=[("disabled", MUTED)],
        bordercolor=[("focus", PAPER), ("active", PAPER), ("disabled", PAPER)],
        lightcolor=[("focus", PAPER), ("active", PAPER), ("disabled", PAPER)],
        darkcolor=[("focus", PAPER), ("active", PAPER), ("disabled", PAPER)],
    )

    style.configure(
        "Pixel.TLabelframe",
        background=PANEL,
        bordercolor=INK,
        lightcolor=INK,
        darkcolor=INK,
        relief="flat",
        borderwidth=0,
    )
    style.configure(
        "Pixel.TLabelframe.Label",
        background=PANEL,
        foreground=INK,
        font=(font_family, 11, "bold"),
        padding=(2, 0),
    )
    style.configure(
        "Pixel.TCombobox",
        fieldbackground=PANEL,
        background=PANEL,
        foreground=INK,
        bordercolor=INK,
        arrowcolor=INK,
        padding=6,
    )
    style.map(
        "Pixel.TCombobox",
        fieldbackground=[("readonly", PANEL), ("focus", PANEL), ("!disabled", PANEL)],
        background=[("readonly", PANEL), ("focus", PANEL), ("!disabled", PANEL)],
        foreground=[("readonly", INK), ("focus", INK), ("!disabled", INK)],
        selectbackground=[("readonly", PANEL), ("focus", PANEL), ("!disabled", PANEL)],
        selectforeground=[("readonly", INK), ("focus", INK), ("!disabled", INK)],
    )
    style.configure(
        "Pixel.TEntry",
        fieldbackground=PANEL,
        foreground=INK,
        bordercolor=INK,
        lightcolor=INK,
        darkcolor=INK,
        insertcolor=INK,
        padding=(10, 8),
    )
    style.map(
        "Pixel.TEntry",
        bordercolor=[("focus", INK), ("disabled", GRID)],
        fieldbackground=[("disabled", SOFT)],
        foreground=[("disabled", MUTED)],
    )
    style.configure(
        "Search.Pixel.TEntry",
        fieldbackground=PANEL,
        foreground=INK,
        bordercolor=GRID,
        lightcolor=GRID,
        darkcolor=GRID,
        insertcolor=INK,
        relief="flat",
        borderwidth=1,
        padding=(10, 8),
    )
    style.map(
        "Search.Pixel.TEntry",
        bordercolor=[("focus", INK), ("disabled", PANEL)],
        lightcolor=[("focus", INK), ("disabled", PANEL)],
        darkcolor=[("focus", INK), ("disabled", PANEL)],
        fieldbackground=[("disabled", PANEL)],
        foreground=[("disabled", MUTED)],
    )
    style.configure("Pixel.TCheckbutton", background=PANEL, foreground=INK, padding=3)
    style.map("Pixel.TCheckbutton", background=[("active", PANEL)])
    return style


class PixelScene(tk.Canvas):
    """Interactive pixel landscape that previews the two OCR modes."""

    RUN_SPEEDS = {"idle": 3.2, "fast": 7.0, "jump": 6.0}
    FRAME_DELAYS_MS = {"idle": 55, "fast": 34, "jump": 40}
    JUMP_AIR_FRAMES = 40
    JUMP_TAKEOFF_DISTANCE = 145.0
    JUMP_LANDING_DISTANCE = -95.0
    CRASH_RED_TICKS = 44
    CRASH_REBOUND_TICKS = 18
    BIRD_HIT_RED_TICKS = 44
    BIRD_HIT_REBOUND_TICKS = 18
    DISTANCE_METERS_PER_PIXEL = 0.18

    def __init__(self, master: tk.Misc, *, width: int = 420, height: int = 260) -> None:
        super().__init__(
            master,
            width=width,
            height=height,
            background=PAPER,
            highlightthickness=0,
            bd=0,
        )
        self.mode = "idle"
        self.requested_mode = "idle"
        self.frame = 0
        self.world_offset = 0.0
        self.world_speed = 0.0
        self.obstacles: list[tuple[float, int, int, str, int]] = []
        self._next_obstacle_id = 1
        self._cleared_obstacle_ids: set[int] = set()
        self._next_obstacle_gap = 0.0
        self._rng = random.Random()
        self._next_obstacle_gap = self._random_initial_obstacle_gap()
        self._boost_ticks = 0
        self._manual_jump_lift_px = 0.0
        self._manual_jump_velocity = 0.0
        self._manual_jump_count = 0
        self._max_manual_jumps = 2
        self._manual_action_ticks = 0
        self._crash_ticks = 0
        self._bird_hit_ticks: dict[int, int] = {}
        self._distance_meters = 0.0
        self._trees_skipped = 0
        self._tree_crashes = 0
        self._birds_hit = 0
        self._scored_tree_skip_ids: set[int] = set()
        self._scored_tree_crash_ids: set[int] = set()
        self._scored_bird_hit_ids: set[int] = set()
        self._manual_drive = False
        self._animation_id: str | None = None
        self.bind("<Configure>", self._redraw)
        self.after_idle(self._ensure_animation)

    def set_mode(self, mode: str) -> None:
        """Switch between idle and active runner speeds."""

        next_mode = mode if mode in {"idle", "fast", "jump"} else "idle"
        if next_mode == self.requested_mode:
            return
        self.requested_mode = next_mode
        self._activate_mode(next_mode)

        self._redraw()
        self._ensure_animation()

    def _activate_mode(self, mode: str) -> None:
        self.mode = mode
        if not self.obstacles and self._next_obstacle_gap <= 0:
            self._next_obstacle_gap = self._random_initial_obstacle_gap()

    def set_manual_drive(self, enabled: bool) -> None:
        next_manual_drive = bool(enabled)
        if self._manual_drive == next_manual_drive:
            return
        self._manual_drive = next_manual_drive
        if not self._manual_drive:
            self._boost_ticks = 0
            self._manual_jump_lift_px = 0.0
            self._manual_jump_velocity = 0.0
            self._manual_jump_count = 0
            self._manual_action_ticks = 0
            self.mode = self.requested_mode
            self._ensure_animation()
            self._redraw()

    def boost(self) -> None:
        """Temporarily speed up the runner and background motion."""

        if not self._manual_drive:
            return
        self._activate_user_action_mode("fast")
        self._boost_ticks = max(self._boost_ticks, 34)
        self._manual_action_ticks = max(self._manual_action_ticks, 96)
        self._ensure_animation()
        self._redraw()

    def manual_jump(self) -> None:
        """Trigger a jump even when no obstacle is nearby."""

        if not self._manual_drive:
            return
        self._activate_user_action_mode("jump")
        if self._manual_jump_lift_px <= 0.0 and self._manual_jump_velocity <= 0.0:
            self._manual_jump_count = 0
        if self._manual_jump_count >= self._max_manual_jumps:
            return
        height = max(self.winfo_height(), 180)
        power = self._manual_jump_power(height)
        self._manual_jump_count += 1
        if self._manual_jump_count == 1:
            self._manual_jump_velocity = power
        else:
            self._manual_jump_velocity = max(power * 0.92, self._manual_jump_velocity)
        self._manual_action_ticks = max(self._manual_action_ticks, 96)
        self._ensure_animation()
        self._redraw()

    def _activate_user_action_mode(self, mode: str) -> None:
        if mode in {"fast", "jump"}:
            self.mode = mode

    def _random_initial_obstacle_gap(self) -> float:
        return self._rng.uniform(38.0, 128.0)

    def _random_obstacle_gap(self) -> float:
        roll = self._rng.random()
        if roll < 0.30:
            return self._rng.uniform(125.0, 210.0)
        if roll < 0.82:
            return self._rng.uniform(210.0, 350.0)
        return self._rng.uniform(350.0, 520.0)

    def _update_obstacles(self, width: int) -> None:
        speed = max(0.0, self.world_speed)
        if speed > 0:
            self.obstacles = [
                (x - speed, size_bias, obstacle_id, kind, altitude)
                for x, size_bias, obstacle_id, kind, altitude in self.obstacles
                if x > -150
            ]
            obstacle_ids = {
                obstacle_id
                for _x, _size_bias, obstacle_id, _kind, _altitude in self.obstacles
            }
            self._bird_hit_ticks = {
                obstacle_id: ticks
                for obstacle_id, ticks in self._bird_hit_ticks.items()
                if obstacle_id in obstacle_ids
            }
            self._cleared_obstacle_ids.intersection_update(obstacle_ids)

        if self._crash_ticks > 0:
            return

        if speed < 0.35:
            return

        spawn_line = width + 120.0
        if self.obstacles:
            rightmost = max(x for x, _size_bias, _obstacle_id, _kind, _altitude in self.obstacles)
            if spawn_line - rightmost < self._next_obstacle_gap:
                return
        else:
            self._next_obstacle_gap -= speed
            if self._next_obstacle_gap > 0:
                return

        self.obstacles.append(self._make_obstacle(spawn_line))
        self._next_obstacle_id += 1
        self._next_obstacle_gap = self._random_obstacle_gap()

    def _make_obstacle(self, spawn_line: float) -> tuple[float, int, int, str, int]:
        if self._rng.random() < 0.34:
            return (
                spawn_line + self._rng.uniform(0.0, 170.0),
                self._rng.choice((-1, 0, 0, 1)),
                self._next_obstacle_id,
                "bird",
                self._rng.choice((116, 130, 146)),
            )
        return (
            spawn_line + self._rng.uniform(0.0, 150.0),
            self._rng.choice((-1, 0, 0, 1, 2)),
            self._next_obstacle_id,
            "cactus",
            0,
        )

    def _ensure_animation(self) -> None:
        if self._animation_id is None:
            self._animation_id = self.after(16, self._tick)

    def _tick(self) -> None:
        self._animation_id = None
        if not self.winfo_exists():
            return

        self.frame += 1
        if self._crash_ticks > 0:
            self._crash_ticks -= 1
        if self._bird_hit_ticks:
            self._bird_hit_ticks = {
                obstacle_id: ticks - 1
                for obstacle_id, ticks in self._bird_hit_ticks.items()
                if ticks > 1
            }
        if self._boost_ticks > 0:
            self._boost_ticks -= 1
        if self._manual_action_ticks > 0:
            self._manual_action_ticks -= 1

        motion_mode = self._active_motion_mode()
        base_speed = self.RUN_SPEEDS[motion_mode]
        target_speed = base_speed * 1.85 if self._boost_ticks > 0 else base_speed
        self.world_speed += (target_speed - self.world_speed) * 0.24
        if abs(self.world_speed) < 0.02 and target_speed == 0.0:
            self.world_speed = 0.0
        self.world_offset += self.world_speed
        self._update_distance_stat()

        width = max(self.winfo_width(), 280)
        height = max(self.winfo_height(), 180)
        self._update_manual_jump(height)
        if (
            self.mode != self.requested_mode
            and self._boost_ticks <= 0
            and not self._manual_jump_active()
        ):
            self.mode = self.requested_mode
        self._update_obstacles(width)
        self._update_tree_skip_stats(width, height)
        self._update_user_action_feedback(width, height)

        self._redraw()
        should_continue = (
            self.world_speed != 0.0
            or bool(self.obstacles)
            or self._boost_ticks > 0
            or self._manual_action_ticks > 0
            or self._manual_jump_active()
            or self._crash_ticks > 0
            or bool(self._bird_hit_ticks)
        )
        if should_continue:
            delay = (
                24
                if self._boost_ticks > 0
                else self.FRAME_DELAYS_MS[motion_mode]
            )
            self._animation_id = self.after(delay, self._tick)

    def _active_motion_mode(self) -> str:
        if self._manual_drive and self.mode in {"fast", "jump"}:
            return self.mode
        return self.requested_mode

    def _redraw(self, _event: tk.Event | None = None) -> None:
        width = max(self.winfo_width(), 280)
        height = max(self.winfo_height(), 180)
        self.delete("all")
        self._draw_background(width, height)
        self._draw_score_board(width, height)

        ground = height - 105
        self.create_line(0, ground, width, ground, fill=INK, width=2)
        ground_offset = int(-self.world_offset) % 53
        for x in range(-53 + ground_offset, width + 53, 53):
            self.create_line(x, ground + 9, x + 7, ground + 9, fill=GRID, width=2)

        scale = max(4, min(6, width // 72))
        dino_x = int(width * 0.31) - 10 * scale
        dino_y = ground - 18 * scale

        streak_offset = int(-self.world_offset * 1.35) % 110
        if self.mode == "fast":
            for x in range(-90 + streak_offset, dino_x - 20, 110):
                self.create_line(x, ground - 34, x + 34, ground - 34, fill=GRID, width=2)
                self.create_line(x + 19, ground - 21, x + 54, ground - 21, fill=GRID, width=2)
        self._draw_scene_obstacles(width, ground, scale)
        jump_lift = max(
            self._auto_jump_lift(dino_x, scale, height),
            self._manual_jump_lift(height),
        )
        jump_lift = min(jump_lift, max(0, dino_y - 8))
        if jump_lift > 0:
            dino_y -= jump_lift
        else:
            bob = 3 if self.mode == "fast" else 2
            if self._crash_rebound_active():
                bob = 0
            dino_y -= bob if self.frame % 4 < 2 else 0

        rebound_x = self._crash_rebound_offset(scale)
        dino_color = ERROR if self._crash_ticks > 0 else INK
        self._draw_dino(dino_x + rebound_x, dino_y, scale, foreground=dino_color)

    def _draw_score_board(self, width: int, height: int) -> None:
        self._ensure_stats_state()
        ground = height - 105
        compact = height < 420 or width < 560
        board_width = 118 if compact else 136
        row_height = 28 if compact else 38
        board_height = row_height * 4
        x = max(18, int(width * 0.04))
        y = max(118, int(height * 0.22))
        if y + board_height > ground - 12:
            y = max(18, ground - board_height - 14)

        stats = (
            ("distance", f"{int(self._distance_meters):d} m"),
            ("tree", f"{self._trees_skipped:d}"),
            ("crash", f"{self._tree_crashes:d}"),
            ("bird", f"{self._birds_hit:d}"),
        )
        icon_x = x + 14
        value_x = x + board_width - 10
        value_font_size = 12 if compact else 16
        for index, (icon, value) in enumerate(stats):
            row_y = y + index * row_height
            center_y = row_y + row_height // 2
            if index > 0:
                line_y = row_y
                self.create_line(
                    x,
                    line_y,
                    x + board_width,
                    line_y,
                    fill=SOFT,
                    width=1,
                    dash=(2, 4),
                )
            self._draw_score_icon(icon, icon_x, center_y)
            self.create_text(
                value_x,
                center_y,
                text=value,
                anchor=tk.E,
                fill=INK,
                font=("TkFixedFont", value_font_size, "bold"),
            )

    def _draw_score_icon(self, kind: str, x: int, center_y: int) -> None:
        color = "#aaa8a1"
        if kind == "distance":
            y = center_y - 9
            self.create_arc(
                x - 9,
                y,
                x + 9,
                y + 18,
                start=20,
                extent=140,
                outline=color,
                style=tk.ARC,
                width=2,
            )
            self.create_line(x, center_y, x + 5, center_y - 5, fill=color, width=2)
            self.create_line(x - 9, center_y + 7, x + 9, center_y + 7, fill=color, width=1, dash=(2, 4))
            return
        if kind == "tree":
            self._draw_cactus(x - 1, center_y + 10, 2, color=color)
            return
        if kind == "crash":
            y = center_y - 9
            self.create_rectangle(x - 8, y + 3, x + 8, y + 16, fill=color, outline=color, width=0)
            self.create_rectangle(x - 5, y, x + 5, y + 5, fill=color, outline=color, width=0)
            self.create_line(x - 5, y + 8, x - 2, y + 11, fill=PAPER, width=2)
            self.create_line(x - 2, y + 8, x - 5, y + 11, fill=PAPER, width=2)
            self.create_line(x + 2, y + 8, x + 5, y + 11, fill=PAPER, width=2)
            self.create_line(x + 5, y + 8, x + 2, y + 11, fill=PAPER, width=2)
            return
        self._draw_bird(x - 12, center_y - 5, 2, wing_up=True, color=color)

    def _draw_background(self, width: int, height: int) -> None:
        """Render soft parallax layers behind the runner."""

        cloud_offset = int(self.world_offset * 0.14) % 360
        cloud_color = "#deddd7"
        for index, base_x in enumerate(range(-280, width + 420, 360)):
            x = base_x - cloud_offset
            y = 88 + (index % 3) * 52
            self._draw_cloud(x, y, 5 if index % 2 else 6, cloud_color)

        distant_ground = height - 106
        cactus_offset = int(self.world_offset * 0.48) % 285
        for index, base_x in enumerate(range(-180, width + 390, 285)):
            x = base_x - cactus_offset
            pixel = 3 if index % 2 else 4
            self._draw_distant_cactus(x, distant_ground, pixel)

    def _draw_cloud(self, x: int, y: int, p: int, color: str) -> None:
        blocks = ((0, 2, 2, 3), (2, 1, 4, 3), (4, 0, 7, 3), (7, 1, 9, 3), (9, 2, 12, 3))
        for x1, y1, x2, y2 in blocks:
            self.create_rectangle(
                x + x1 * p,
                y + y1 * p,
                x + x2 * p,
                y + y2 * p,
                fill=color,
                outline=color,
                width=0,
            )

    def _draw_distant_cactus(self, x: int, ground: int, p: int) -> None:
        color = "#c6c4bc"
        self.create_rectangle(x, ground - 9 * p, x + 2 * p, ground, fill=color, outline=color)
        self.create_rectangle(x - 2 * p, ground - 6 * p, x, ground - 4 * p, fill=color, outline=color)
        self.create_rectangle(x - 3 * p, ground - 8 * p, x - 2 * p, ground - 4 * p, fill=color, outline=color)
        self.create_rectangle(x + 2 * p, ground - 7 * p, x + 4 * p, ground - 5 * p, fill=color, outline=color)
        self.create_rectangle(x + 4 * p, ground - 9 * p, x + 5 * p, ground - 5 * p, fill=color, outline=color)

    def _update_user_action_feedback(self, width: int, height: int) -> None:
        if (
            not self._manual_drive
            or not self.obstacles
        ):
            return
        scale = max(4, min(6, width // 72))
        dino_center = int(width * 0.31)
        manual_lift = self._manual_jump_lift(height)
        collided_obstacle = self._collided_obstacle(
            dino_center,
            scale,
            manual_lift,
            height,
        )
        if collided_obstacle is not None:
            obstacle_id, kind = collided_obstacle
            if kind == "bird":
                self._trigger_bird_hit(obstacle_id)
            else:
                self._trigger_crash(obstacle_id)
            return
        self._mark_manual_clear(dino_center, scale, manual_lift)

    def _update_distance_stat(self) -> None:
        if self.world_speed <= 0.0:
            return
        self._ensure_stats_state()
        self._distance_meters += self.world_speed * self.DISTANCE_METERS_PER_PIXEL

    def _update_tree_skip_stats(self, width: int, height: int) -> None:
        if not self.obstacles:
            return
        scale = max(4, min(6, width // 72))
        dino_x = int(width * 0.31) - 10 * scale
        jump_lift = max(
            self._auto_jump_lift(dino_x, scale, height),
            self._manual_jump_lift(height),
        )
        self._mark_tree_clear(int(width * 0.31), scale, jump_lift)

    def _collided_obstacle(
        self,
        dino_center: int,
        scale: int,
        manual_lift: int,
        height: int,
    ) -> tuple[int, str] | None:
        if self._crash_ticks > 0:
            return None
        ground = height - 105
        collision_window = max(28, scale * 8)
        for obstacle_x, size_bias, obstacle_id, kind, altitude in self.obstacles:
            if obstacle_id in self._cleared_obstacle_ids:
                continue
            if (
                kind == "cactus"
                and manual_lift <= scale * 8
                and abs(obstacle_x - dino_center) <= collision_window
            ):
                return (obstacle_id, kind)
            if kind == "bird" and self._dino_hits_bird(
                dino_center,
                manual_lift,
                scale,
                ground,
                obstacle_x,
                size_bias,
                altitude,
            ):
                return (obstacle_id, kind)
        return None

    def _dino_hits_bird(
        self,
        dino_center: int,
        manual_lift: int,
        scale: int,
        ground: int,
        bird_x: float,
        size_bias: int,
        altitude: int,
    ) -> bool:
        if manual_lift <= scale * 10:
            return False
        bird_left, bird_top, bird_right, bird_bottom = self._bird_bounds(
            bird_x,
            ground,
            scale,
            size_bias,
            altitude,
        )
        dino_left = dino_center - 9 * scale
        dino_right = dino_center + 9 * scale
        dino_top = ground - 18 * scale - manual_lift
        dino_bottom = ground - 2 * scale - manual_lift
        return (
            dino_left <= bird_right
            and dino_right >= bird_left
            and dino_top <= bird_bottom
            and dino_bottom >= bird_top
        )

    def _trigger_crash(self, obstacle_id: int) -> None:
        self._record_tree_crash(obstacle_id)
        self._crash_ticks = self.CRASH_RED_TICKS
        self._boost_ticks = 0
        self._manual_action_ticks = 0
        self._remove_obstacle(obstacle_id)
        self._manual_jump_lift_px = 0.0
        self._manual_jump_velocity = 0.0
        self._manual_jump_count = 0

    def _trigger_bird_hit(self, obstacle_id: int) -> None:
        self._record_bird_hit(obstacle_id)
        self._bird_hit_ticks[obstacle_id] = self.BIRD_HIT_RED_TICKS
        self._cleared_obstacle_ids.add(obstacle_id)

    def _remove_obstacle(self, obstacle_id: int) -> None:
        self.obstacles = [
            (x, size_bias, current_id, kind, altitude)
            for x, size_bias, current_id, kind, altitude in self.obstacles
            if current_id != obstacle_id
        ]
        self._bird_hit_ticks.pop(obstacle_id, None)
        self._cleared_obstacle_ids.discard(obstacle_id)
        if not self.obstacles:
            self._next_obstacle_gap = self._random_initial_obstacle_gap()

    def _mark_manual_clear(
        self,
        dino_center: int,
        scale: int,
        manual_lift: int,
    ) -> None:
        self._mark_tree_clear(dino_center, scale, manual_lift)

    def _mark_tree_clear(
        self,
        dino_center: int,
        scale: int,
        jump_lift: int,
    ) -> None:
        self._ensure_stats_state()
        if jump_lift <= scale * 8:
            return
        clear_window = max(34, scale * 9)
        for obstacle_x, _size_bias, obstacle_id, kind, _altitude in self.obstacles:
            if kind != "cactus":
                continue
            if obstacle_id in self._cleared_obstacle_ids:
                continue
            if abs(obstacle_x - dino_center) <= clear_window:
                self._record_tree_skip(obstacle_id)
                return

    def _record_tree_skip(self, obstacle_id: int) -> None:
        self._ensure_stats_state()
        if obstacle_id in self._scored_tree_skip_ids:
            return
        self._scored_tree_skip_ids.add(obstacle_id)
        self._cleared_obstacle_ids.add(obstacle_id)
        self._trees_skipped += 1

    def _record_tree_crash(self, obstacle_id: int) -> None:
        self._ensure_stats_state()
        if obstacle_id in self._scored_tree_crash_ids:
            return
        self._scored_tree_crash_ids.add(obstacle_id)
        self._tree_crashes += 1

    def _record_bird_hit(self, obstacle_id: int) -> None:
        self._ensure_stats_state()
        if obstacle_id in self._scored_bird_hit_ids:
            return
        self._scored_bird_hit_ids.add(obstacle_id)
        self._birds_hit += 1

    def _ensure_stats_state(self) -> None:
        if not hasattr(self, "_distance_meters"):
            self._distance_meters = 0.0
        if not hasattr(self, "_trees_skipped"):
            self._trees_skipped = 0
        if not hasattr(self, "_tree_crashes"):
            self._tree_crashes = 0
        if not hasattr(self, "_birds_hit"):
            self._birds_hit = 0
        if not hasattr(self, "_scored_tree_skip_ids"):
            self._scored_tree_skip_ids = set()
        if not hasattr(self, "_scored_tree_crash_ids"):
            self._scored_tree_crash_ids = set()
        if not hasattr(self, "_scored_bird_hit_ids"):
            self._scored_bird_hit_ids = set()
        if not hasattr(self, "_cleared_obstacle_ids"):
            self._cleared_obstacle_ids = set()
        if not hasattr(self, "_bird_hit_ticks"):
            self._bird_hit_ticks = {}

    @staticmethod
    def _smooth_step(value: float) -> float:
        clamped = max(0.0, min(1.0, value))
        return clamped * clamped * (3.0 - 2.0 * clamped)

    def _auto_jump_lift(self, dino_x: int, scale: int, height: int) -> int:
        if self._manual_drive or self.world_speed < 0.35:
            return 0
        dino_center = dino_x + 10 * scale
        takeoff_distance = self.JUMP_TAKEOFF_DISTANCE
        landing_distance = self.JUMP_LANDING_DISTANCE
        strongest_arc = 0.0
        for obstacle_x, _size_bias, _obstacle_id, kind, _altitude in self.obstacles:
            if kind != "cactus":
                continue
            distance = obstacle_x - dino_center
            if landing_distance <= distance <= takeoff_distance:
                progress = (takeoff_distance - distance) / (
                    takeoff_distance - landing_distance
                )
                strongest_arc = max(strongest_arc, self._jump_arc(progress))
        if strongest_arc <= 0.0:
            return 0
        return int(strongest_arc * min(108, max(76, height // 3)))

    def _manual_jump_active(self) -> bool:
        return self._manual_jump_lift_px > 0.0 or self._manual_jump_velocity > 0.0

    def _update_manual_jump(self, height: int) -> None:
        if not self._manual_jump_active():
            self._manual_jump_lift_px = 0.0
            self._manual_jump_velocity = 0.0
            self._manual_jump_count = 0
            return
        self._manual_jump_lift_px += self._manual_jump_velocity
        self._manual_jump_velocity -= self._manual_jump_gravity(height)
        ceiling = self._manual_jump_height(height) * 1.08
        if self._manual_jump_lift_px > ceiling:
            self._manual_jump_lift_px = ceiling
            self._manual_jump_velocity = min(self._manual_jump_velocity, 0.0)
        if self._manual_jump_lift_px <= 0.0:
            self._manual_jump_lift_px = 0.0
            self._manual_jump_velocity = 0.0
            self._manual_jump_count = 0

    def _manual_jump_height(self, height: int) -> int:
        return min(108, max(76, height // 3))

    def _manual_jump_power(self, height: int) -> float:
        return self._manual_jump_gravity(height) * self.JUMP_AIR_FRAMES / 2.0

    def _manual_jump_gravity(self, height: int) -> float:
        jump_height = self._manual_jump_height(height)
        return 8.0 * jump_height / (self.JUMP_AIR_FRAMES * self.JUMP_AIR_FRAMES)

    def _manual_jump_lift(self, height: int) -> int:
        if not self._manual_jump_active():
            return 0
        return int(min(self._manual_jump_lift_px, self._manual_jump_height(height) * 1.08))

    def _crash_rebound_active(self) -> bool:
        if self._crash_ticks <= 0:
            return False
        elapsed = self.CRASH_RED_TICKS - self._crash_ticks
        return elapsed <= self.CRASH_REBOUND_TICKS

    def _crash_rebound_offset(self, scale: int) -> int:
        if self._crash_ticks <= 0:
            return 0
        elapsed = self.CRASH_RED_TICKS - self._crash_ticks
        progress = max(0.0, min(1.0, elapsed / max(1, self.CRASH_REBOUND_TICKS)))
        max_retreat = max(26, scale * 8)
        retreat_turn = 0.24
        if progress < retreat_turn:
            amount = self._smooth_step(progress / retreat_turn)
        else:
            amount = 1.0 - self._smooth_step((progress - retreat_turn) / (1.0 - retreat_turn))
        return -int(max_retreat * amount)

    @staticmethod
    def _jump_arc(progress: float) -> float:
        clamped = max(0.0, min(1.0, progress))
        return max(0.0, 4.0 * clamped * (1.0 - clamped))

    def _draw_scene_obstacles(self, width: int, ground: int, scale: int) -> None:
        for obstacle_x, size_bias, obstacle_id, kind, altitude in self.obstacles:
            if obstacle_x < -90 or obstacle_x > width + 160:
                continue
            if kind == "bird":
                pixel = self._bird_pixel(scale, size_bias)
                bird_top = self._bird_top(ground, altitude)
                wing_up = (self.frame + obstacle_id * 3) % 12 < 6
                hit_ticks = self._bird_hit_ticks.get(obstacle_id, 0)
                bird_x = int(obstacle_x) + self._bird_hit_rebound_offset(scale, hit_ticks)
                bird_color = ERROR if hit_ticks > 0 else INK
                self._draw_bird(bird_x, bird_top, pixel, wing_up=wing_up, color=bird_color)
            else:
                pixel = max(3, scale - 1 + size_bias)
                self._draw_cactus(int(obstacle_x), ground, pixel)

    def _draw_dino(self, x: int, y: int, p: int, *, foreground: str = INK) -> None:
        draw_pixel_dino(self, x, y, p, foreground=foreground, eye_color=PAPER)

    def _draw_cactus(self, x: int, ground: int, p: int, *, color: str = INK) -> None:
        self.create_rectangle(x, ground - 10 * p, x + 2 * p, ground, fill=color, outline=color)
        self.create_rectangle(x - 2 * p, ground - 7 * p, x, ground - 5 * p, fill=color, outline=color)
        self.create_rectangle(x - 3 * p, ground - 9 * p, x - 2 * p, ground - 5 * p, fill=color, outline=color)
        self.create_rectangle(x + 2 * p, ground - 8 * p, x + 4 * p, ground - 6 * p, fill=color, outline=color)
        self.create_rectangle(x + 4 * p, ground - 10 * p, x + 5 * p, ground - 6 * p, fill=color, outline=color)

    def _draw_bird(self, x: int, y: int, p: int, *, wing_up: bool, color: str = INK) -> None:
        self.create_rectangle(x + 3 * p, y + 3 * p, x + 8 * p, y + 6 * p, fill=color, outline=color)
        self.create_rectangle(x + 8 * p, y + 2 * p, x + 10 * p, y + 4 * p, fill=color, outline=color)
        self.create_rectangle(x + 10 * p, y + 3 * p, x + 12 * p, y + 4 * p, fill=color, outline=color)
        self.create_rectangle(x, y + 4 * p, x + 3 * p, y + 5 * p, fill=color, outline=color)
        self.create_rectangle(x + 1 * p, y + 2 * p, x + 3 * p, y + 4 * p, fill=color, outline=color)
        if wing_up:
            self.create_rectangle(x + 4 * p, y, x + 7 * p, y + 2 * p, fill=color, outline=color)
            self.create_rectangle(x + 5 * p, y - 2 * p, x + 6 * p, y, fill=color, outline=color)
        else:
            self.create_rectangle(x + 4 * p, y + 6 * p, x + 7 * p, y + 8 * p, fill=color, outline=color)
            self.create_rectangle(x + 5 * p, y + 8 * p, x + 6 * p, y + 10 * p, fill=color, outline=color)

    def _bird_hit_rebound_offset(self, scale: int, hit_ticks: int) -> int:
        if hit_ticks <= 0:
            return 0
        elapsed = self.BIRD_HIT_RED_TICKS - hit_ticks
        progress = max(0.0, min(1.0, elapsed / max(1, self.BIRD_HIT_REBOUND_TICKS)))
        max_retreat = max(26, scale * 8)
        retreat_turn = 0.24
        if progress < retreat_turn:
            amount = self._smooth_step(progress / retreat_turn)
        else:
            amount = 1.0 - self._smooth_step((progress - retreat_turn) / (1.0 - retreat_turn))
        return int(max_retreat * amount)

    def _bird_bounds(
        self,
        bird_x: float,
        ground: int,
        scale: int,
        size_bias: int,
        altitude: int,
    ) -> tuple[int, int, int, int]:
        p = self._bird_pixel(scale, size_bias)
        top = self._bird_top(ground, altitude)
        left = int(bird_x)
        return (left, top - 2 * p, left + 12 * p, top + 10 * p)

    @staticmethod
    def _bird_pixel(scale: int, size_bias: int) -> int:
        return max(2, scale - 2 + size_bias)

    @staticmethod
    def _bird_top(ground: int, altitude: int) -> int:
        return max(18, ground - altitude)


class MiniPixelGameScene(PixelScene):
    """Small manual runner scene for the compact game window."""

    RUN_SPEEDS = {"idle": 0.0, "fast": 7.0, "jump": 6.0}
    DEFAULT_WIDTH = 430
    DEFAULT_HEIGHT = 210
    MIN_WIDTH = 320
    MIN_HEIGHT = 160
    TOP_PADDING = 13
    BIRD_ALTITUDES = (58, 70, 82)

    def __init__(
        self,
        master: tk.Misc,
        *,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
    ) -> None:
        super().__init__(master, width=width, height=height)
        self.set_manual_drive(True)
        self.set_mode("idle")

    def _random_initial_obstacle_gap(self) -> float:
        return self._rng.uniform(32.0, 96.0)

    def _random_obstacle_gap(self) -> float:
        roll = self._rng.random()
        if roll < 0.34:
            return self._rng.uniform(112.0, 180.0)
        if roll < 0.84:
            return self._rng.uniform(180.0, 285.0)
        return self._rng.uniform(285.0, 390.0)

    def _make_obstacle(self, spawn_line: float) -> tuple[float, int, int, str, int]:
        if self._rng.random() < 0.36:
            return (
                spawn_line + self._rng.uniform(0.0, 126.0),
                self._rng.choice((-1, 0, 0, 1)),
                self._next_obstacle_id,
                "bird",
                self._rng.choice(self.BIRD_ALTITUDES),
            )
        return (
            spawn_line + self._rng.uniform(0.0, 112.0),
            self._rng.choice((-1, 0, 0, 1)),
            self._next_obstacle_id,
            "cactus",
            0,
        )

    def _redraw(self, _event: tk.Event | None = None) -> None:
        width = max(self.winfo_width(), self.MIN_WIDTH)
        height = max(self.winfo_height(), self.MIN_HEIGHT)
        self.delete("all")
        draw_pixel_box(
            self,
            2,
            2,
            width - 3,
            height - 3,
            fill=PAPER,
            line_color=GRID,
            accent_color=INK,
            tag="mini-game-shell",
            pixel=3,
            width=1,
            show_corners=True,
        )
        self._draw_score_board(width, height)

        ground = self._mini_ground(height)
        self.create_line(12, ground, width - 12, ground, fill=INK, width=2)
        ground_offset = int(-self.world_offset) % 39
        for x in range(12 - 39 + ground_offset, width - 8, 39):
            self.create_line(x, ground + 7, x + 6, ground + 7, fill=GRID, width=2)

        scale = self._mini_scale(width, height)
        dino_x = int(width * 0.26) - 10 * scale
        dino_y = ground - 18 * scale
        self._draw_scene_obstacles(width, ground, scale)

        jump_lift = max(
            self._auto_jump_lift(dino_x, scale, height),
            self._manual_jump_lift(height),
        )
        jump_lift = min(jump_lift, max(0, dino_y - self.TOP_PADDING - 12))
        if jump_lift > 0:
            dino_y -= jump_lift
        else:
            bob = 3 if self.frame % 4 < 2 else 0
            if self._crash_rebound_active():
                bob = 0
            dino_y -= bob

        rebound_x = self._crash_rebound_offset(scale)
        dino_color = ERROR if self._crash_ticks > 0 else INK
        self._draw_dino(dino_x + rebound_x, dino_y, scale, foreground=dino_color)

    def _draw_score_board(self, width: int, _height: int) -> None:
        self._ensure_stats_state()
        self.create_text(
            16,
            14,
            text=self._compact_score_text(),
            anchor=tk.NW,
            fill=INK,
            font=("TkFixedFont", 11, "bold"),
        )
        self.create_line(16, 34, min(width - 18, 122), 34, fill=SOFT, width=1)

    def _compact_score_text(self) -> str:
        self._ensure_stats_state()
        return "/".join(
            (
                self._score_distance(self._distance_meters),
                self._score_count(self._trees_skipped),
                self._score_count(self._tree_crashes),
                self._score_count(self._birds_hit),
            )
        )

    @staticmethod
    def _score_distance(value: float) -> str:
        return str(max(0, int(value)))

    @staticmethod
    def _score_count(value: int) -> str:
        return f"{max(0, min(999, int(value))):03d}"

    def _mini_ground(self, height: int) -> int:
        return height - max(42, min(58, height // 4))

    def _mini_scale(self, width: int, height: int) -> int:
        return max(3, min(5, width // 92, height // 42))

    @staticmethod
    def _bird_top(ground: int, altitude: int) -> int:
        return max(42, ground - altitude)


class PixelProcessRail(tk.Canvas):
    """Compact OCR status card with the dinosaur and useful live context."""

    LABELS = {
        "idle": "等待图片",
        "ready": "Enter 键开始 OCR 处理",
        "working": "OCR 处理中",
        "done": "OCR 处理结束",
        "error": "OCR 处理失败",
    }
    MOTION_TAG = "process-rail-motion"
    STATIC_TAG = "process-rail-static"
    MAX_DETAILED_TEXT_NODES = 18
    MAX_DETAILED_OBSTACLES = 12

    def __init__(
        self,
        master: tk.Misc,
        font_family: str,
        *,
        status_var: tk.Variable | None = None,
        image_var: tk.Variable | None = None,
        saved_var: tk.Variable | None = None,
    ) -> None:
        super().__init__(
            master,
            height=68,
            background=PANEL,
            highlightthickness=0,
            bd=0,
        )
        self.font_family = font_family
        self.status_var = status_var
        self.image_var = image_var
        self.saved_var = saved_var
        self.state = "idle"
        self.phase = "idle"
        self.run_active = False
        self.run_mode = "text"
        self.total_items = 1
        self.completed_items = 0
        self.frame = 0
        self.world_offset = 0.0
        self._text_slot = 0.0
        self._document_display_stage = 0
        self._document_queued_until = 0
        self._document_jump_queue: list[int] = []
        self._jump_start_stage = 0
        self._jump_end_stage = 0
        self._jump_frame = 0
        self._jump_steps = 8
        self._animation_id: str | None = None
        self._animation_paused = False
        self._layout_ready = False
        self._info_traces: list[tuple[tk.Variable, str]] = []
        self._layout: dict[str, int] | None = None
        self._status_label_item: int | None = None
        for variable in (status_var, image_var, saved_var):
            if variable is not None:
                trace_name = variable.trace_add("write", self._on_info_change)
                self._info_traces.append((variable, trace_name))
        self.bind("<Configure>", self._on_configure)
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _on_configure(self, _event: tk.Event | None = None) -> None:
        if not self._layout_ready:
            try:
                width = self.winfo_width()
                height = self.winfo_height()
            except tk.TclError:
                return
            if width < 240 or height < 40:
                return
            self._layout_ready = True
        self._redraw()

    def _on_info_change(self, *_args: object) -> None:
        try:
            exists = self.winfo_exists()
        except tk.TclError:
            return
        if exists and not self._animation_paused:
            self._on_configure()

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        self._cancel_animation()
        for variable, trace_name in self._info_traces:
            try:
                variable.trace_remove("write", trace_name)
            except tk.TclError:
                pass
        self._info_traces.clear()

    def configure_run(self, mode: str, total: int, completed: int = 0) -> None:
        """Set OCR animation context without tying animation to OCR workers."""

        next_mode = mode if mode in {"text", "document"} else "text"
        next_total = max(1, int(total or 1))
        next_completed = self._clamp_completed(completed, next_total)
        context_changed = (
            not self.run_active
            or next_mode != self.run_mode
            or next_total != self.total_items
            or (next_completed == 0 and self.state in {"done", "error"})
        )

        self.run_active = True
        self.run_mode = next_mode
        self.total_items = next_total
        if context_changed:
            self.completed_items = next_completed
            self._text_slot = self._initial_text_slot(next_completed)
            self._document_display_stage = next_completed
            self._document_queued_until = next_completed
            self._document_jump_queue.clear()
            self._jump_start_stage = next_completed
            self._jump_end_stage = next_completed
            self._jump_frame = 0
        else:
            self._advance_completed(next_completed)

        if self.state == "working":
            self._activate_working_phase()
            self._ensure_animation()
        elif self.state == "done" and self.run_mode == "document":
            self._queue_document_jumps_to(self.total_items)
            if self.phase != "document_jump":
                self._start_next_document_jump()
            self._ensure_animation()
        self._on_configure()

    def update_run_progress(self, completed: int, total: int | None = None) -> None:
        """Advance the displayed OCR item count from a coarse progress event."""

        if total is not None and max(1, int(total or 1)) != self.total_items:
            self.configure_run(self.run_mode, total, completed)
            return
        if not self.run_active:
            self.configure_run(self.run_mode, total or 1, completed)
            return

        self._advance_completed(self._clamp_completed(completed, self.total_items))
        if self.state == "working":
            if self.run_mode == "text":
                self.phase = "text_running"
            elif self.phase != "document_jump":
                self._start_next_document_jump()
        self._on_configure()
        self._ensure_animation()

    def set_state(self, state: str) -> None:
        next_state = state if state in self.LABELS else "idle"
        self.state = next_state

        if next_state in {"idle", "ready"}:
            self._cancel_animation()
            self._reset_run_context()
            self.phase = next_state
            self.frame = 0
            self._on_configure()
            return

        if next_state == "error":
            self._cancel_animation()
            self.phase = "error"
            self.frame = 0
            self._on_configure()
            return

        if next_state == "working":
            if not self.run_active:
                self.run_active = True
                self.run_mode = "text"
                self.total_items = 1
                self.completed_items = 0
                self._text_slot = 0.0
            self._activate_working_phase()
            self._on_configure()
            self._ensure_animation()
            return

        if next_state == "done":
            if self.run_active and self.run_mode == "document":
                self.completed_items = self.total_items
                self._queue_document_jumps_to(self.total_items)
                if self.phase != "document_jump":
                    self._start_next_document_jump()
                if self.phase != "document_jump":
                    self.phase = "done"
                    self._cancel_animation()
                self._on_configure()
                self._ensure_animation()
                return
            if self.run_active and self.run_mode == "text":
                self.completed_items = self.total_items
                if self.total_items <= 1:
                    if self._text_slot >= 1.0:
                        self._text_slot = 1.0
                        self.phase = "done"
                        self._cancel_animation()
                    else:
                        self.phase = "text_running"
                        self._on_configure()
                        self._ensure_animation()
                        return
                else:
                    self._text_slot = float(max(0, self.total_items - 1))
            self._cancel_animation()
            self.phase = "done"
            self.frame = 0
            self._on_configure()

    def set_animation_paused(self, paused: bool) -> None:
        """Stop hidden progress animation without changing OCR state."""

        next_paused = bool(paused)
        if self._animation_paused == next_paused:
            return
        self._animation_paused = next_paused
        if next_paused:
            self._cancel_animation()
            return
        self._on_configure()
        self._ensure_animation()

    def _reset_run_context(self) -> None:
        self.run_active = False
        self.run_mode = "text"
        self.total_items = 1
        self.completed_items = 0
        self.world_offset = 0.0
        self._text_slot = 0.0
        self._document_display_stage = 0
        self._document_queued_until = 0
        self._document_jump_queue.clear()
        self._jump_start_stage = 0
        self._jump_end_stage = 0
        self._jump_frame = 0

    def _cancel_animation(self) -> None:
        if self._animation_id is None:
            return
        try:
            self.after_cancel(self._animation_id)
        except tk.TclError:
            pass
        self._animation_id = None

    def _activate_working_phase(self) -> None:
        self.frame = 0
        if self.run_mode == "document":
            if self.phase != "document_jump":
                self.phase = "document_jogging"
                self._document_display_stage = min(
                    self._document_display_stage,
                    self.total_items,
                )
        else:
            self.phase = "text_running"
            self._text_slot = self._initial_text_slot(self.completed_items)

    def _advance_completed(self, completed: int) -> None:
        completed = self._clamp_completed(completed, self.total_items)
        if self.run_mode == "document":
            if completed > self.completed_items:
                self._queue_document_jumps_to(completed)
            self.completed_items = max(self.completed_items, completed)
            return
        self.completed_items = max(self.completed_items, completed)

    def _queue_document_jumps_to(self, target_stage: int) -> None:
        target_stage = self._clamp_completed(target_stage, self.total_items)
        if target_stage <= self._document_queued_until:
            return
        for stage in range(self._document_queued_until + 1, target_stage + 1):
            self._document_jump_queue.append(stage)
        self._document_queued_until = target_stage

    def _start_next_document_jump(self) -> None:
        if self.state == "error":
            return
        while self._document_jump_queue:
            target_stage = self._document_jump_queue.pop(0)
            if target_stage <= self._document_display_stage:
                continue
            self._jump_start_stage = self._document_display_stage
            self._jump_end_stage = min(target_stage, self.total_items)
            self._jump_frame = 0
            self._jump_steps = 20
            self.phase = "document_jump"
            return
        if self.state == "done" and self._document_display_stage >= self.total_items:
            self.phase = "done"
        elif self.state == "working":
            self.phase = "document_jogging"

    def _clamp_completed(self, completed: int, total: int) -> int:
        try:
            value = int(completed)
        except (TypeError, ValueError):
            value = 0
        return max(0, min(max(1, total), value))

    def _initial_text_slot(self, completed: int) -> float:
        if self.total_items <= 1:
            return 0.0
        if completed <= 0:
            return -0.35
        return float(min(self.total_items - 1, completed - 1))

    def _text_target_slot(self) -> float:
        if self.total_items <= 1:
            return 1.0
        if self.state == "done":
            return float(self.total_items - 1)
        return float(min(self.total_items - 1, self.completed_items))

    def _should_draw_track(self) -> bool:
        return self.run_active and self.state in {"working", "done", "error"}

    def _should_animate(self) -> bool:
        if self._animation_paused:
            return False
        if self.state == "error":
            return False
        if (
            self.state == "done"
            and self.run_mode == "text"
            and self.total_items <= 1
            and self.phase == "text_running"
            and self._text_slot < 1.0
        ):
            return True
        if self.phase == "document_jump":
            return True
        return self.state == "working" and self.phase in {
            "text_running",
            "document_jogging",
        }

    def _frame_delay(self) -> int:
        if self.phase == "text_running":
            return 108
        if self.phase == "document_jump":
            return 86
        return 118

    def _ensure_animation(self) -> None:
        if self._animation_id is not None or not self._should_animate():
            return
        try:
            self._animation_id = self.after(self._frame_delay(), self._tick)
        except tk.TclError:
            self._animation_id = None

    def _tick(self) -> None:
        self._animation_id = None
        try:
            exists = self.winfo_exists()
        except tk.TclError:
            return
        if not exists or not self._should_animate():
            return

        self.frame = (self.frame + 1) % 8
        needs_full_redraw = False
        if self.phase == "text_running":
            if self.total_items <= 1:
                step = 0.045 if self.state == "done" else 0.022
                self._text_slot = min(1.0, self._text_slot + step)
                if self.state == "done" and self._text_slot >= 1.0:
                    self.phase = "done"
            else:
                target_slot = self._text_target_slot()
                delta = target_slot - self._text_slot
                if abs(delta) < 0.03:
                    self._text_slot = target_slot
                else:
                    self._text_slot += delta * 0.32
            self.world_offset += 5.2
        elif self.phase == "document_jogging":
            self.world_offset += 2.1
        elif self.phase == "document_jump":
            self.world_offset += 3.2
            self._jump_frame += 1
            if self._jump_frame >= self._jump_steps:
                self._document_display_stage = self._jump_end_stage
                needs_full_redraw = True
                if self._document_jump_queue:
                    self._start_next_document_jump()
                elif self.state == "done" and self._document_display_stage >= self.total_items:
                    self.phase = "done"
                elif self.state == "working":
                    self.phase = "document_jogging"

        if needs_full_redraw:
            self._on_configure()
        else:
            self._redraw_dynamic()
        if self._should_animate():
            try:
                self._animation_id = self.after(self._frame_delay(), self._tick)
            except tk.TclError:
                self._animation_id = None

    def _redraw(self, _event: tk.Event | None = None) -> None:
        if self._animation_paused:
            return
        if not self._layout_ready:
            return
        try:
            width = max(self.winfo_width(), 720)
            height = max(self.winfo_height(), 68)
        except tk.TclError:
            return
        self.delete("all")
        self._layout = self._layout_metrics(width, height)
        self._status_label_item = None
        draw_pixel_border(self, width, height)
        color = ERROR if self.state == "error" else SUCCESS if self.state == "done" else MUTED
        self._status_label_item = self.create_text(
            76,
            22,
            text=self._status_label_text(),
            anchor=tk.W,
            fill=color,
            font=(self.font_family, 11, "bold"),
        )

        detail = str(self.status_var.get()) if self.status_var is not None else ""
        detail_width = (
            max(160, self._layout["track_start"] - 96)
            if self._should_draw_track()
            else max(180, width - 520)
        )
        self.create_text(
            76,
            44,
            text=detail,
            anchor=tk.W,
            fill=MUTED,
            width=detail_width,
            font=(self.font_family, 9),
        )

        image_text = str(self.image_var.get()) if self.image_var is not None else ""
        saved_text = str(self.saved_var.get()) if self.saved_var is not None else ""
        self.create_text(
            width - 18,
            22,
            text=image_text,
            anchor=tk.E,
            fill=INK,
            font=(self.font_family, 9, "bold"),
        )
        self.create_text(
            width - 18,
            46,
            text=saved_text,
            anchor=tk.E,
            fill=MUTED,
            font=(self.font_family, 9),
        )

        if self._should_draw_track():
            self._draw_track_static(self._layout)
        self._redraw_dynamic()

    def _redraw_dynamic(self) -> None:
        try:
            self.delete(self.MOTION_TAG)
        except tk.TclError:
            return
        self._update_status_label()
        layout = self._layout
        if layout is None:
            try:
                layout = self._layout_metrics(
                    max(self.winfo_width(), 720),
                    max(self.winfo_height(), 68),
                )
            except tk.TclError:
                return
            self._layout = layout

        if self._should_draw_track():
            self._draw_track_runner(layout)
        else:
            top = layout["height"] // 2 - 18
            foreground = ERROR if self.state == "error" else INK
            self._draw_runner(18, top, foreground=foreground, running=False)

    def _layout_metrics(self, width: int, height: int) -> dict[str, int]:
        track_start = max(300, int(width * 0.43))
        track_end = min(width - 190, int(width * 0.76))
        if track_end - track_start < 170:
            track_start = max(260, width - 420)
            track_end = min(width - 160, max(track_start + 170, width - 185))
        return {
            "width": width,
            "height": height,
            "ground": height - 13,
            "track_start": track_start,
            "track_end": max(track_start + 120, track_end),
        }

    def _status_label_text(self) -> str:
        dots = "." * (self.frame % 4 + 1) if self.state == "working" else ""
        return f"{self.LABELS[self.state]}{dots}"

    def _update_status_label(self) -> None:
        if self._status_label_item is None:
            return
        try:
            self.itemconfigure(self._status_label_item, text=self._status_label_text())
        except tk.TclError:
            self._status_label_item = None

    def _draw_track_static(self, layout: dict[str, int]) -> None:
        start = layout["track_start"]
        end = layout["track_end"]
        ground = layout["ground"]
        y = ground - 2
        self.create_line(start, y, end, y, fill=GRID, width=2, tag=self.STATIC_TAG)
        if self.run_mode == "document":
            self._draw_document_obstacles(layout)
        else:
            self._draw_text_nodes(layout)
        self.create_text(
            end,
            24,
            text=f"{min(self.completed_items, self.total_items)}/{self.total_items}",
            anchor=tk.E,
            fill=MUTED,
            font=(self.font_family, 8, "bold"),
            tag=self.STATIC_TAG,
        )

    def _draw_text_nodes(self, layout: dict[str, int]) -> None:
        start = layout["track_start"]
        y = layout["ground"] - 2
        completed = min(self.completed_items, self.total_items)
        if self.total_items <= 1:
            start_x = layout["track_start"]
            end_x = layout["track_end"]
            if completed:
                self.create_line(
                    start_x,
                    y,
                    end_x,
                    y,
                    fill=SUCCESS,
                    width=3,
                    tag=self.STATIC_TAG,
                )
            for x, fill, outline in (
                (start_x, SUCCESS if completed else PANEL, GRID),
                (end_x, SUCCESS if completed else PANEL, INK),
            ):
                self.create_rectangle(
                    x - 4,
                    y - 4,
                    x + 4,
                    y + 4,
                    fill=fill,
                    outline=outline,
                    width=2,
                    tag=self.STATIC_TAG,
                )
            return

        if completed > 0:
            progress_x = self._text_node_x(completed - 1, layout)
            self.create_line(start, y, progress_x, y, fill=SUCCESS, width=3, tag=self.STATIC_TAG)

        if self.total_items <= self.MAX_DETAILED_TEXT_NODES:
            current = min(self.total_items - 1, completed)
            for index in range(self.total_items):
                x = self._text_node_x(index, layout)
                fill = SUCCESS if index < completed else PANEL
                outline = INK if index == current and self.state == "working" else GRID
                self.create_rectangle(
                    x - 3,
                    y - 3,
                    x + 3,
                    y + 3,
                    fill=fill,
                    outline=outline,
                    width=2,
                    tag=self.STATIC_TAG,
                )
            return

        for index in self._sample_indices(self.total_items, 16):
            x = self._text_node_x(index, layout)
            color = SUCCESS if index < completed else GRID
            self.create_line(x, y - 5, x, y + 5, fill=color, width=2, tag=self.STATIC_TAG)

    def _draw_document_obstacles(self, layout: dict[str, int]) -> None:
        ground = layout["ground"]
        passed = min(self._document_display_stage, self.total_items)
        if self.total_items <= self.MAX_DETAILED_OBSTACLES:
            for index in range(self.total_items):
                x = self._document_obstacle_x(index, layout)
                color = SUCCESS if index < passed else INK if index == passed else GRID
                self._draw_obstacle(x, ground, 2, color=color)
            return

        y = ground - 2
        for index in self._sample_indices(self.total_items, 16):
            x = self._document_obstacle_x(index, layout)
            color = SUCCESS if index < passed else INK if index == passed else GRID
            self.create_rectangle(
                x - 2,
                y - 12,
                x + 2,
                y + 2,
                fill=color,
                outline=color,
                width=0,
                tag=self.STATIC_TAG,
            )

    def _sample_indices(self, total: int, limit: int) -> list[int]:
        if total <= limit:
            return list(range(total))
        return sorted({round(index * (total - 1) / (limit - 1)) for index in range(limit)})

    def _draw_track_runner(self, layout: dict[str, int]) -> None:
        pixel = 2
        sprite_width = max(len(row) for row in DINO_SPRITE) * pixel
        sprite_height = len(DINO_SPRITE) * pixel
        ground = layout["ground"]
        center_x, jump_lift = self._runner_center_and_lift(layout)
        running = (
            self.phase in {"text_running", "document_jogging", "document_jump"}
            and self.state != "error"
        )
        bob = 0
        if running and self.phase == "text_running":
            bob = 3 if self.frame % 4 < 2 else 0
            self._draw_speed_lines(center_x, ground)
        elif running and self.phase == "document_jogging":
            bob = 2 if self.frame % 4 < 2 else 0
        self._draw_motion_ground(center_x, ground)
        top = ground - sprite_height - bob - jump_lift
        left = int(center_x - sprite_width / 2)
        foreground = ERROR if self.state == "error" else INK
        self._draw_runner(left, top, foreground=foreground, running=running)

    def _runner_center_and_lift(self, layout: dict[str, int]) -> tuple[float, int]:
        if self.run_mode == "text":
            return self._text_slot_x(self._text_slot, layout), 0
        if self.phase == "document_jump":
            start = self._document_wait_x(self._jump_start_stage, layout)
            end = self._document_wait_x(self._jump_end_stage, layout)
            obstacle = self._document_obstacle_x(
                max(0, min(self.total_items - 1, self._jump_end_stage - 1)),
                layout,
            )
            interval = max(1.0, end - start)
            jump_half = min(28.0, max(11.0, interval * 0.22))
            takeoff = max(start, obstacle - jump_half)
            landing = min(end, obstacle + jump_half)
            t = min(1.0, self._jump_frame / max(1, self._jump_steps))
            if t < 0.34:
                local = t / 0.34
                eased = local * local * (3.0 - 2.0 * local)
                return start + (takeoff - start) * eased, 0
            if t < 0.72:
                local = (t - 0.34) / 0.38
                eased = local * local * (3.0 - 2.0 * local)
                lift = int(math.sin(local * math.pi) * 19)
                return takeoff + (landing - takeoff) * eased, lift
            local = (t - 0.72) / 0.28
            eased = local * local * (3.0 - 2.0 * local)
            return landing + (end - landing) * eased, 0
        stage = min(self._document_display_stage, self.total_items)
        return self._document_wait_x(stage, layout), 0

    def _draw_speed_lines(self, center_x: float, ground: int) -> None:
        offset = int(-self.world_offset * 1.2) % 38
        for index in range(3):
            x = int(center_x - 72 + offset - index * 38)
            self.create_line(
                x,
                ground - 29,
                x + 22,
                ground - 29,
                fill=GRID,
                width=2,
                tag=self.MOTION_TAG,
            )
            self.create_line(
                x + 12,
                ground - 18,
                x + 34,
                ground - 18,
                fill=GRID,
                width=2,
                tag=self.MOTION_TAG,
            )

    def _draw_motion_ground(self, center_x: float, ground: int) -> None:
        if self.state == "error":
            return
        offset = int(-self.world_offset) % 24
        for x in range(int(center_x) - 56 + offset, int(center_x) + 58, 24):
            self.create_line(
                x,
                ground + 5,
                x + 8,
                ground + 5,
                fill=GRID,
                width=2,
                tag=self.MOTION_TAG,
            )

    def _text_node_x(self, index: int, layout: dict[str, int]) -> int:
        if self.total_items <= 1:
            return layout["track_end"]
        span = layout["track_end"] - layout["track_start"]
        return int(layout["track_start"] + span * index / (self.total_items - 1))

    def _text_slot_x(self, slot: float, layout: dict[str, int]) -> float:
        if self.total_items <= 1:
            progress = max(0.0, min(1.0, slot))
            return layout["track_start"] + (
                layout["track_end"] - layout["track_start"]
            ) * progress
        span = layout["track_end"] - layout["track_start"]
        x = layout["track_start"] + span * slot / (self.total_items - 1)
        return max(layout["track_start"] - 46, min(layout["track_end"], x))

    def _document_wait_x(self, stage: int, layout: dict[str, int]) -> float:
        span = layout["track_end"] - layout["track_start"]
        return layout["track_start"] + span * min(stage, self.total_items) / self.total_items

    def _document_obstacle_x(self, index: int, layout: dict[str, int]) -> int:
        left = self._document_wait_x(index, layout)
        right = self._document_wait_x(index + 1, layout)
        return int((left + right) / 2)

    def _draw_runner(
        self,
        x: int,
        y: int,
        *,
        foreground: str = INK,
        running: bool = False,
    ) -> None:
        draw_pixel_dino(
            self,
            x,
            y,
            2,
            foreground=foreground,
            eye_color=PANEL,
            tag=self.MOTION_TAG,
        )
        if not running:
            return
        leg_y = y + (len(DINO_SPRITE) - 1) * 2
        if self.frame % 2:
            feet = (
                (x + 5, leg_y, x + 13, leg_y + 4),
                (x + 20, leg_y, x + 26, leg_y + 2),
            )
        else:
            feet = (
                (x + 8, leg_y, x + 14, leg_y + 2),
                (x + 20, leg_y, x + 30, leg_y + 4),
            )
        for x1, y1, x2, y2 in feet:
            self.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill=foreground,
                outline=foreground,
                width=0,
                tag=self.MOTION_TAG,
            )

    def _draw_obstacle(self, x: int, ground: int, p: int, *, color: str) -> None:
        blocks = (
            (x, ground - 10 * p, x + 2 * p, ground),
            (x - 2 * p, ground - 7 * p, x, ground - 5 * p),
            (x - 3 * p, ground - 9 * p, x - 2 * p, ground - 5 * p),
            (x + 2 * p, ground - 8 * p, x + 4 * p, ground - 6 * p),
            (x + 4 * p, ground - 10 * p, x + 5 * p, ground - 6 * p),
        )
        for x1, y1, x2, y2 in blocks:
            self.create_rectangle(
                x1,
                y1,
                x2,
                y2,
                fill=color,
                outline=color,
                tag=self.STATIC_TAG,
            )

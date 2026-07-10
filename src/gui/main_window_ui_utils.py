"""Small UI helpers for the main OCR window."""

from __future__ import annotations

import tkinter as tk

from PIL import Image, ImageDraw

from src.gui.pixel_theme import INK, PANEL


class Tooltip:
    """Small native tooltip for controls whose labels are intentionally hidden."""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self._after_id: str | None = None
        self._window: tk.Toplevel | None = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, _event: tk.Event | None = None) -> None:
        self._cancel_pending()
        self._after_id = self.widget.after(450, self._show)

    def _show(self) -> None:
        self._after_id = None
        if self._window is not None or not self.widget.winfo_exists():
            return
        window = tk.Toplevel(self.widget)
        window.wm_overrideredirect(True)
        window.wm_geometry(
            f"+{self.widget.winfo_rootx()}+{self.widget.winfo_rooty() + self.widget.winfo_height() + 6}"
        )
        tk.Label(
            window,
            text=self.text,
            background=INK,
            foreground=PANEL,
            borderwidth=0,
            padx=8,
            pady=4,
        ).pack()
        self._window = window

    def _hide(self, _event: tk.Event | None = None) -> None:
        self._cancel_pending()
        if self._window is not None:
            self._window.destroy()
            self._window = None

    def _cancel_pending(self) -> None:
        if self._after_id is not None:
            self.widget.after_cancel(self._after_id)
            self._after_id = None


def draw_result_action_icon(
    kind: str,
    color: str,
    *,
    background: str = "#fbfbf8",
    border: str = "#dedcd6",
    shadow: str = "#eceae4",
) -> Image.Image:
    """Draw the result toolbar button as a crisp line-icon card."""

    width, height, scale = 58, 38, 4
    image = Image.new("RGBA", (width * scale, height * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    def xy(*values: float) -> tuple[int, ...]:
        return tuple(int(round(value * scale)) for value in values)

    def draw_line(*values: float, line_width: float = 2.1) -> None:
        draw.line(xy(*values), fill=color, width=max(1, int(round(line_width * scale))), joint="curve")

    def draw_round_rect(*values: float, radius: float = 3.0, line_width: float = 2.1) -> None:
        draw.rounded_rectangle(
            xy(*values),
            radius=int(round(radius * scale)),
            outline=color,
            width=max(1, int(round(line_width * scale))),
        )

    draw.rounded_rectangle(
        xy(2.5, 3.5, width - 1.5, height - 1.0),
        radius=12 * scale,
        fill=shadow,
        outline=None,
    )
    draw.rounded_rectangle(
        xy(1.5, 1.5, width - 2.5, height - 3.0),
        radius=12 * scale,
        fill=background,
        outline=border,
        width=max(1, int(round(1.1 * scale))),
    )

    if kind == "copy":
        draw_round_rect(21.5, 10.0, 34.0, 24.5, radius=2.6)
        draw_round_rect(26.5, 14.5, 40.0, 29.0, radius=2.6)
    elif kind == "export":
        draw_line(23.5, 17.0, 23.5, 29.0, 36.5, 29.0, 36.5, 17.0)
        draw_line(30.0, 22.5, 30.0, 8.5)
        draw_line(25.5, 13.0, 30.0, 8.5, 34.5, 13.0)
    elif kind == "clear":
        draw_line(20.5, 13.0, 37.5, 13.0)
        draw_round_rect(23.0, 13.5, 35.0, 30.0, radius=2.6)
        draw_line(26.0, 9.5, 32.0, 9.5)
        draw_line(26.0, 17.0, 26.0, 26.0, line_width=1.8)
        draw_line(29.0, 17.0, 29.0, 26.0, line_width=1.8)
        draw_line(32.0, 17.0, 32.0, 26.0, line_width=1.8)
    elif kind == "view":
        draw_line(18.0, 19.0, 23.5, 13.5, 29.0, 11.5, 34.5, 13.5, 40.0, 19.0)
        draw_line(18.0, 19.0, 23.5, 24.5, 29.0, 26.5, 34.5, 24.5, 40.0, 19.0)
        draw.ellipse(
            xy(25.0, 15.0, 33.0, 23.0),
            outline=color,
            width=max(1, int(round(2.1 * scale))),
        )
        draw.ellipse(xy(28.1, 18.1, 29.9, 19.9), fill=color)
    elif kind == "save":
        draw_round_rect(20.0, 8.5, 38.0, 29.5, radius=2.6)
        draw_line(24.0, 8.5, 24.0, 16.0, 34.0, 16.0, 34.0, 8.5)
        draw_line(24.0, 23.0, 34.0, 23.0)
        draw_line(24.0, 26.0, 34.0, 26.0)
    elif kind == "rotate":
        draw_round_rect(27.0, 15.0, 37.0, 25.0, radius=1.5)
        draw.arc(xy(18.0, 8.0, 34.0, 24.0), start=180, end=270, fill=color, width=max(1, int(round(1.8 * scale))))
        draw_line(26.0, 8.0, 31.0, 8.0, 28.2, 12.2, line_width=1.8)
    elif kind == "mirror":
        draw_line(29.0, 7.5, 29.0, 30.5, line_width=1.6)
        draw.polygon(xy(19.0, 12.0, 27.0, 19.0, 19.0, 26.0), outline=color)
        draw.polygon(xy(39.0, 12.0, 31.0, 19.0, 39.0, 26.0), outline=color)
        draw_line(21.5, 19.0, 25.0, 19.0, line_width=1.5)
        draw_line(33.0, 19.0, 36.5, 19.0, line_width=1.5)
    elif kind == "mirror_vertical":
        draw_line(17.0, 19.0, 41.0, 19.0, line_width=1.6)
        draw.polygon(xy(22.0, 9.0, 29.0, 17.0, 36.0, 9.0), outline=color)
        draw.polygon(xy(22.0, 29.0, 29.0, 21.0, 36.0, 29.0), outline=color)
        draw_line(29.0, 11.5, 29.0, 15.0, line_width=1.5)
        draw_line(29.0, 23.0, 29.0, 26.5, line_width=1.5)
    else:
        raise ValueError(f"Unknown result action icon: {kind}")

    return image.resize((width, height), Image.Resampling.LANCZOS)

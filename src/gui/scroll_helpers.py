"""Reusable mouse wheel helpers for Tk scrollable widgets."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable


class WheelBindingManager:
    """Owns one active bind_all wheel target for a window/dialog."""

    def __init__(self) -> None:
        self._owner: tk.Misc | None = None

    def unbind(self, _event: tk.Event | None = None) -> None:
        if self._owner is None:
            return
        try:
            self._owner.unbind_all("<MouseWheel>")
            self._owner.unbind_all("<Button-4>")
            self._owner.unbind_all("<Button-5>")
        except tk.TclError:
            pass
        self._owner = None

    def bind(self, widget: tk.Misc, handler: Callable[[tk.Event], str]) -> None:
        if self._owner is not widget:
            self.unbind()
        widget.bind_all("<MouseWheel>", handler)
        widget.bind_all("<Button-4>", handler)
        widget.bind_all("<Button-5>", handler)
        self._owner = widget


def _clamped_scroll_target(current: float, delta_fraction: float, max_first: float = 1.0) -> float:
    return max(0.0, min(max_first, current + delta_fraction))


def scroll_canvas_by_wheel(canvas: tk.Canvas, event: tk.Event, *, notch_pixels: float = 96.0) -> str:
    number = getattr(event, "num", None)
    if number == 4:
        first, _last = canvas.yview()
        if first <= 0.0:
            return "break"
        canvas.yview_scroll(-4, "units")
        return "break"
    if number == 5:
        _first, last = canvas.yview()
        if last >= 1.0:
            return "break"
        canvas.yview_scroll(4, "units")
        return "break"
    delta = getattr(event, "delta", 0)
    if delta == 0:
        return "break"
    region = canvas.cget("scrollregion").split()
    content_height = float(region[3]) if len(region) == 4 else float(canvas.winfo_height())
    visible_height = max(float(canvas.winfo_height()), 1.0)
    scrollable_height = max(content_height - visible_height, 1.0)
    if content_height <= visible_height:
        return "break"
    pixels = -delta / 120 * notch_pixels if abs(delta) >= 120 else -delta * 6
    first, last = canvas.yview()
    if (pixels < 0 and first <= 0.0) or (pixels > 0 and last >= 1.0):
        return "break"
    target = _clamped_scroll_target(first, pixels / scrollable_height, max(0.0, 1.0 - (last - first)))
    if abs(target - first) > 0.0001:
        canvas.yview_moveto(target)
    return "break"


def scroll_text_by_wheel(text_widget: tk.Text, event: tk.Event) -> str:
    number = getattr(event, "num", None)
    first, last = text_widget.yview()
    if number == 4:
        if first > 0.0:
            text_widget.yview_scroll(-5, "units")
        return "break"
    if number == 5:
        if last < 1.0:
            text_widget.yview_scroll(5, "units")
        return "break"
    delta = getattr(event, "delta", 0)
    if delta == 0:
        return "break"
    if (delta > 0 and first <= 0.0) or (delta < 0 and last >= 1.0):
        return "break"
    units = max(1, int(abs(delta) / 120 * 8)) if abs(delta) >= 120 else max(1, int(abs(delta) * 0.45))
    text_widget.yview_scroll(-units if delta > 0 else units, "units")
    return "break"

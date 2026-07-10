"""Tk top-level window helpers shared by the GUI."""

from __future__ import annotations

import tkinter as tk

from src.gui.pixel_theme import PAPER


def create_independent_window(
    title: str,
    *,
    resizable: bool = True,
    background: str = PAPER,
) -> tk.Toplevel:
    """Create a standalone document window that macOS treats as a real window.

    Passing a parent to ``tk.Toplevel(parent)`` or calling ``transient(parent)``
    makes macOS group the child with the main window.  These auxiliary app
    windows should be independently selectable/minimizable, so they are created
    without a master and styled as document windows where Tk exposes the macOS
    hook.
    """

    window = tk.Toplevel()
    window.withdraw()
    window.title(title)
    window.configure(background=background)
    if not resizable:
        window.resizable(False, False)
    try:
        style_flags = "closeBox collapseBox resizable" if resizable else "closeBox collapseBox"
        window.tk.call(
            "::tk::unsupported::MacWindowStyle",
            "style",
            window,
            "document",
            style_flags,
        )
    except tk.TclError:
        pass
    return window

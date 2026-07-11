"""Tk top-level window helpers shared by the GUI."""

from __future__ import annotations

import tkinter as tk

from src.gui.pixel_theme import PAPER


def focus_existing_window(window: tk.Toplevel | None) -> bool:
    """Show and focus an existing Toplevel when it is still alive."""

    if window is None:
        return False
    try:
        if not window.winfo_exists():
            return False
        window.deiconify()
        window.lift()
        try:
            window.focus_force()
        except tk.TclError:
            window.focus_set()
        return True
    except tk.TclError:
        return False


def center_window(dialog: tk.Toplevel, owner: tk.Misc | None = None) -> None:
    """Center a top-level window relative to an owner or the screen."""

    parent_window = owner
    if parent_window is not None:
        parent_window.update_idletasks()
    dialog.update_idletasks()
    dialog_width = max(dialog.winfo_width(), dialog.winfo_reqwidth(), 1)
    dialog_height = max(dialog.winfo_height(), dialog.winfo_reqheight(), 1)
    if parent_window is not None:
        parent_x = parent_window.winfo_rootx()
        parent_y = parent_window.winfo_rooty()
        parent_width = max(parent_window.winfo_width(), 1)
        parent_height = max(parent_window.winfo_height(), 1)
        x = parent_x + max((parent_width - dialog_width) // 2, 0)
        y = parent_y + max((parent_height - dialog_height) // 2, 0)
    else:
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x = max((screen_width - dialog_width) // 2, 0)
        y = max((screen_height - dialog_height) // 3, 0)
    dialog.geometry(f"+{x}+{y}")


def show_centered_window(dialog: tk.Toplevel, owner: tk.Misc | None = None) -> None:
    """Center, show, lift, and focus a top-level helper window."""

    center_window(dialog, owner)
    dialog.deiconify()
    dialog.lift()
    try:
        dialog.focus_force()
    except tk.TclError:
        dialog.focus_set()


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

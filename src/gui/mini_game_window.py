"""Compact dinosaur runner window for the OCR desktop UI."""

from __future__ import annotations

import tkinter as tk

from src.gui.pixel_theme import MiniPixelGameScene, PAPER
from src.gui.window_utils import create_independent_window


class MiniPixelGameWindow:
    """A small standalone manual runner scene."""

    WIDTH = MiniPixelGameScene.DEFAULT_WIDTH
    HEIGHT = MiniPixelGameScene.DEFAULT_HEIGHT

    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        self.window: tk.Toplevel | None = None
        self.scene: MiniPixelGameScene | None = None

    def show(self) -> None:
        if self.window is None or not self._window_exists():
            self._create_window()

        window = self.window
        if window is None:
            return
        try:
            window.deiconify()
            window.lift()
            window.focus_force()
            if self.scene is not None:
                self.scene.focus_set()
        except tk.TclError:
            pass

    def destroy(self) -> None:
        if self.window is None:
            return
        try:
            if self.window.winfo_exists():
                self.window.destroy()
        except tk.TclError:
            pass
        self.window = None
        self.scene = None

    def _create_window(self) -> None:
        window = create_independent_window("", resizable=False)
        try:
            window.configure(background=PAPER)
        except tk.TclError:
            pass
        window.protocol("WM_DELETE_WINDOW", self.destroy)

        scene = MiniPixelGameScene(window, width=self.WIDTH, height=self.HEIGHT)
        scene.pack(fill=tk.BOTH, expand=True)
        self._bind_manual_controls(window, scene)

        self.window = window
        self.scene = scene
        self._center_window()
        try:
            scene.focus_set()
        except tk.TclError:
            pass

    def _bind_manual_controls(self, window: tk.Toplevel, scene: MiniPixelGameScene) -> None:
        try:
            scene.configure(takefocus=True)
        except tk.TclError:
            pass

        for sequence in (
            "<KeyPress-j>",
            "<KeyPress-J>",
            "<KeyPress-d>",
            "<KeyPress-D>",
            "<KeyPress-Right>",
        ):
            window.bind(sequence, self._run, add="+")
            scene.bind(sequence, self._run, add="+")

        for sequence in (
            "<KeyPress-k>",
            "<KeyPress-K>",
            "<KeyPress-w>",
            "<KeyPress-W>",
            "<KeyPress-Up>",
            "<space>",
        ):
            window.bind(sequence, self._jump, add="+")
            scene.bind(sequence, self._jump, add="+")

    def _run(self, _event: tk.Event | None = None) -> str:
        if self.scene is not None:
            self.scene.boost()
        return "break"

    def _jump(self, _event: tk.Event | None = None) -> str:
        if self.scene is not None:
            self.scene.manual_jump()
        return "break"

    def _window_exists(self) -> bool:
        try:
            return self.window is not None and self.window.winfo_exists()
        except tk.TclError:
            return False

    def _center_window(self) -> None:
        window = self.window
        if window is None:
            return
        try:
            width = self.WIDTH
            height = self.HEIGHT
            root_x = self.master.winfo_rootx()
            root_y = self.master.winfo_rooty()
            root_width = max(1, self.master.winfo_width())
            root_height = max(1, self.master.winfo_height())
            x = root_x + max(0, (root_width - width) // 2)
            y = root_y + max(0, (root_height - height) // 2)
            window.geometry(f"{width}x{height}+{x}+{y}")
        except tk.TclError:
            pass

"""Small floating dinosaur pet window for the OCR desktop UI."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
import random
import time
import tkinter as tk

from PIL import Image, ImageColor, ImageDraw, ImageTk

from src.app_paths import get_data_dir
from src.gui.pixel_theme import DINO_SPRITE, GRID, INK, PANEL, PAPER, CutCornerButton, draw_pixel_box


class _FloatingDropEvent:
    def __init__(self, data: object) -> None:
        self.data = data
        self._from_floating_pet = True


@dataclass(frozen=True)
class _TransparencyStrategy:
    widget_background: str
    image_mode: str
    image_background: str | tuple[int, int, int, int]
    transparent_color: str | None = None
    native_transparent: bool = False

    @property
    def enabled(self) -> bool:
        return self.transparent_color is not None or self.native_transparent


class FloatingDinoPet:
    """A tiny always-on-top dinosaur window that restores the main workbench."""

    DEFAULT_PIXEL = 4
    MIN_PIXEL = 3
    MAX_PIXEL = 7
    DRAG_THRESHOLD = 5
    OUTER_BACKGROUND = PAPER
    ANIMATION_MS = 180
    EAT_ANIMATION_MS = 85
    EAT_ANIMATION_FRAMES = 6
    DROP_DISPATCH_DELAY_MS = 30
    COMPLETION_AUTO_HIDE_MS = 10_000
    TRANSPARENT_COLOR_KEY = "#010203"
    POSITION_STATE_PATH = get_data_dir() / "gui_state" / "floating_pet_position.json"
    _DND_METHODS = (
        "_substitute_dnd",
        "_dnd_bind",
        "dnd_bind",
        "drag_source_register",
        "drag_source_unregister",
        "drop_target_register",
        "drop_target_unregister",
        "platform_independent_types",
        "platform_specific_types",
        "get_dropfile_tempdir",
        "set_dropfile_tempdir",
    )

    def __init__(
        self,
        master: tk.Tk,
        restore_command: Callable[[], None],
        *,
        drop_command: Callable[[tk.Event], str] | None = None,
        drop_started_command: Callable[[object], None] | None = None,
        dnd_files_type: str | None = None,
        drop_accept_action: str = "copy",
        position_state_path: str | Path | None = None,
    ) -> None:
        self.master = master
        self.restore_command = restore_command
        self.drop_command = drop_command
        self.drop_started_command = drop_started_command
        self._dnd_files_type = dnd_files_type
        self._drop_accept_action = drop_accept_action
        self.window: tk.Toplevel | None = None
        self.image_label: tk.Label | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._photo_cache: dict[tuple[int, int, int, str, int, int], ImageTk.PhotoImage] = {}
        self._pixel = self.DEFAULT_PIXEL
        self._background_color = self.OUTER_BACKGROUND
        self._transparency = self._solid_transparency_strategy()
        self._position_state_path = Path(position_state_path) if position_state_path is not None else self.POSITION_STATE_PATH
        self._position: tuple[int, int] | None = self._load_saved_position()
        self._base_position: tuple[int, int] | None = self._position
        self._last_window_size: tuple[int, int] | None = None
        self._press_pointer: tuple[int, int] | None = None
        self._press_window: tuple[int, int] | None = None
        self._dragged = False
        self._state = "idle"
        self._frame = 0
        self._pose = "idle"
        self._pose_ticks = 0
        self._ambient_motion_enabled = False
        self._animation_after_id: str | None = None
        self._eat_animation_after_id: str | None = None
        self._eating_ticks = 0
        self._restore_blocked_until = 0.0
        self._drop_enabled = False
        self._drop_widgets: list[tk.Widget] = []
        self._drop_dispatch_after_ids: set[str] = set()
        self._completion_auto_hide_after_id: str | None = None
        self._assistant_panel = "normal"
        self._overlay_widgets: list[tk.Widget] = []
        self._overlay_drop_widgets: list[tk.Widget] = []

    def is_visible(self) -> bool:
        window = self.window
        if window is None:
            return False
        try:
            return window.winfo_exists() and window.state() != "withdrawn"
        except tk.TclError:
            return False

    def set_state(self, state: str) -> None:
        self._state = state
        if state != "working" and not self._ambient_motion_enabled:
            self._pose = "idle"
            self._pose_ticks = 0
            self._cancel_animation()
            self._redraw()
            return
        self._redraw()
        self._sync_animation()

    def set_drag_drop_enabled(self, enabled: bool) -> None:
        self._drop_enabled = enabled
        self._sync_drag_drop_registration()

    def play_eat_animation(self) -> None:
        self._eating_ticks = self.EAT_ANIMATION_FRAMES
        self._photo_cache.clear()
        self._redraw()
        if self._eat_animation_after_id is None:
            self._eat_animation_after_id = self.master.after(
                self.EAT_ANIMATION_MS,
                self._advance_eat_animation,
            )

    def show_completion_message(self) -> bool:
        self._snapshot_base_position()
        self._assistant_panel = "complete"
        self._photo_cache.clear()
        visible = self.show()
        self._schedule_completion_auto_hide()
        return visible

    def clear_assistant_panel(self) -> None:
        self._cancel_completion_auto_hide()
        if self._assistant_panel == "normal":
            self._sync_drag_drop_registration()
            return
        self._assistant_panel = "normal"
        self._photo_cache.clear()
        self._clear_overlay_widgets()
        window = self.window
        if window is not None:
            width, height = self._window_size()
            x, y = self._remembered_resident_position()
            self._set_window_geometry(width, height, x=x, y=y)
        self._redraw()
        # Clearing the completion overlay unregisters every TkDND target.
        # Re-register the resident pet immediately so another completed batch
        # can be followed by a fresh drop without restoring the main window.
        self._sync_drag_drop_registration()

    def show(self) -> bool:
        if self.window is None or not self._window_exists():
            self._create_window()

        window = self.window
        if window is None:
            return False

        x, y = self._position or self._default_position()
        width, height = self._window_size()
        keep_bottom_right = self._last_window_size is not None and self._last_window_size != (width, height)
        if keep_bottom_right:
            self._set_window_geometry(width, height, keep_bottom_right=True)
        else:
            self._set_window_geometry(width, height, x=x, y=y)
        self._apply_topmost(window)
        self._ambient_motion_enabled = True
        try:
            window.deiconify()
            window.lift()
            window.update_idletasks()
        except tk.TclError:
            self._ambient_motion_enabled = False
            self._cancel_animation()
            return False
        self._redraw()
        self._sync_animation()
        self._layout_assistant_overlay()
        self._refresh_drag_drop_registration()
        try:
            window.update_idletasks()
        except tk.TclError:
            self._ambient_motion_enabled = False
            self._cancel_animation()
            return False
        return self.is_visible()

    def hide(self) -> None:
        self._ambient_motion_enabled = False
        self._cancel_eat_animation()
        if self.window is None:
            self._cancel_animation()
            return
        try:
            if self.window.winfo_exists():
                self._remember_position()
                self._save_position()
                self._cancel_animation()
                self.window.withdraw()
        except tk.TclError:
            pass

    def destroy(self) -> None:
        self._ambient_motion_enabled = False
        self._cancel_animation()
        self._cancel_eat_animation()
        self._cancel_completion_auto_hide()
        self._cancel_pending_drop_dispatches()
        self._unregister_drag_drop()
        if self.window is None:
            return
        try:
            if self.window.winfo_exists():
                self.window.destroy()
        except tk.TclError:
            pass
        self.window = None
        self.image_label = None
        self._photo = None
        self._photo_cache.clear()
        self._press_pointer = None
        self._press_window = None
        self._dragged = False
        self._clear_overlay_widgets()

    def _create_window(self) -> None:
        self._unregister_drag_drop()
        window = tk.Toplevel(self.master)
        window.withdraw()
        window.title("小恐龙")
        window.resizable(False, False)
        try:
            window.overrideredirect(True)
        except tk.TclError:
            pass
        self._apply_topmost(window)
        try:
            window.configure(background=self._background_color)
        except tk.TclError:
            pass
        window.protocol("WM_DELETE_WINDOW", self.restore_command)

        width, height = self._window_size()
        label = tk.Label(
            window,
            width=width,
            height=height,
            background=self._background_color,
            borderwidth=0,
            highlightthickness=0,
            bd=0,
            cursor="fleur",
        )
        label.pack(fill=tk.BOTH, expand=True)
        self.window = window
        self.image_label = label
        self._configure_transparency()
        self._bind_window_controls(label)
        self._redraw()

    def _solid_transparency_strategy(self) -> _TransparencyStrategy:
        return _TransparencyStrategy(
            widget_background=self.OUTER_BACKGROUND,
            image_mode="RGB",
            image_background=self.OUTER_BACKGROUND,
        )

    def _windowing_system(self) -> str:
        try:
            return str(self.master.tk.call("tk", "windowingsystem")).strip().lower()
        except (AttributeError, tk.TclError):
            return ""

    def _transparency_strategy(self) -> _TransparencyStrategy:
        return getattr(self, "_transparency", self._solid_transparency_strategy())

    def _configure_transparency(self) -> None:
        strategy = self._strategy_for_windowing_system(self._windowing_system())
        try:
            self._apply_transparency_strategy(strategy)
        except tk.TclError:
            strategy = self._solid_transparency_strategy()
            try:
                self._apply_transparency_strategy(strategy)
            except tk.TclError:
                pass
        self._transparency = strategy
        if hasattr(self, "_photo_cache"):
            self._photo_cache.clear()

    def _strategy_for_windowing_system(self, windowing_system: str) -> _TransparencyStrategy:
        if windowing_system == "win32":
            return _TransparencyStrategy(
                widget_background=self.TRANSPARENT_COLOR_KEY,
                image_mode="RGB",
                image_background=self.TRANSPARENT_COLOR_KEY,
                transparent_color=self.TRANSPARENT_COLOR_KEY,
            )
        if windowing_system == "aqua":
            return self._aqua_transparency_strategy()
        return self._solid_transparency_strategy()

    def _aqua_transparency_strategy(self) -> _TransparencyStrategy:
        # Tk/aqua draws child widgets and PhotoImage content over a black backing
        # surface in transparent windows, so native transparency is not safe for
        # the real-time resident pet renderer without platform-specific APIs.
        return self._solid_transparency_strategy()

    def _apply_transparency_strategy(self, strategy: _TransparencyStrategy) -> None:
        window = self.window
        label = self.image_label
        if window is None or label is None:
            return
        window.configure(background=strategy.widget_background)
        label.configure(background=strategy.widget_background)
        if strategy.transparent_color is not None:
            window.attributes("-transparentcolor", strategy.transparent_color)
        if strategy.native_transparent:
            window.attributes("-transparent", True)

    def _refresh_drag_drop_registration(self) -> None:
        self._unregister_drag_drop()
        self._sync_drag_drop_registration()

    def _sync_drag_drop_registration(self) -> None:
        if not self._drop_enabled:
            self._unregister_drag_drop()
            return
        if self._drop_widgets or self.drop_command is None or self._dnd_files_type is None:
            return
        targets = [
            widget
            for widget in (self.window, self.image_label, *getattr(self, "_overlay_drop_widgets", []))
            if widget is not None
        ]
        for widget in targets:
            self._install_drag_drop_methods(widget)
            if not hasattr(widget, "drop_target_register") or not hasattr(widget, "dnd_bind"):
                continue
            try:
                widget.drop_target_register(self._dnd_files_type)
                widget.dnd_bind("<<DropEnter>>", self._accept_drop)
                widget.dnd_bind("<<DropPosition>>", self._accept_drop)
                widget.dnd_bind("<<Drop>>", self._on_drop)
            except tk.TclError as exc:
                try:
                    widget.drop_target_unregister()
                except tk.TclError:
                    pass
                print(f"[WARNING] 浮窗文件拖拽不可用: {exc}")
                continue
            self._drop_widgets.append(widget)

    def _install_drag_drop_methods(self, widget: tk.Widget) -> None:
        for attribute in ("_subst_format_dnd", "_subst_format_str_dnd"):
            if not hasattr(widget, attribute) and hasattr(self.master, attribute):
                setattr(widget, attribute, getattr(self.master, attribute))

        for method_name in self._DND_METHODS:
            if hasattr(widget, method_name):
                continue
            method = getattr(self.master, method_name, None)
            if method is None:
                continue
            function = getattr(method, "__func__", method)
            try:
                setattr(widget, method_name, function.__get__(widget, type(widget)))
            except AttributeError:
                setattr(widget, method_name, method)

    def _unregister_drag_drop(self) -> None:
        for widget in self._drop_widgets:
            try:
                if widget.winfo_exists():
                    widget.dnd_bind("<<DropEnter>>", "")
                    widget.dnd_bind("<<DropPosition>>", "")
                    widget.dnd_bind("<<Drop>>", "")
                    widget.drop_target_unregister()
            except tk.TclError:
                pass
        self._drop_widgets = []

    def _accept_drop(self, _event: tk.Event) -> str:
        self._block_restore_briefly()
        return self._drop_accept_action

    def _on_drop(self, event: tk.Event) -> str:
        self._block_restore_briefly()
        self.play_eat_animation()
        drop_event = _FloatingDropEvent(getattr(event, "data", ""))
        drop_started_command = getattr(self, "drop_started_command", None)
        if drop_started_command is not None:
            try:
                drop_started_command(drop_event)
            except Exception as exc:
                print(f"[WARNING] 浮窗拖拽预处理失败: {exc}")
        if getattr(self, "drop_command", None) is not None:
            self._schedule_drop_dispatch(drop_event)
        return self._drop_accept_action

    def _schedule_drop_dispatch(self, drop_event: _FloatingDropEvent) -> None:
        if not hasattr(self, "_drop_dispatch_after_ids"):
            self._drop_dispatch_after_ids = set()
        after_id: str | None = None

        def dispatch() -> None:
            if after_id is not None:
                self._drop_dispatch_after_ids.discard(after_id)
            drop_command = getattr(self, "drop_command", None)
            if drop_command is not None:
                drop_command(drop_event)  # type: ignore[arg-type]

        try:
            after_id = self.master.after(self.DROP_DISPATCH_DELAY_MS, dispatch)
            self._drop_dispatch_after_ids.add(after_id)
        except (AttributeError, tk.TclError):
            dispatch()

    def _cancel_pending_drop_dispatches(self) -> None:
        for after_id in list(self._drop_dispatch_after_ids):
            try:
                self.master.after_cancel(after_id)
            except (AttributeError, tk.TclError):
                pass
        self._drop_dispatch_after_ids.clear()

    def _block_restore_briefly(self) -> None:
        self._restore_blocked_until = time.monotonic() + 1.2

    def _clear_overlay_widgets(self) -> None:
        self._unregister_drag_drop()
        for widget in self._overlay_widgets:
            try:
                if widget.winfo_exists():
                    widget.destroy()
            except tk.TclError:
                pass
        self._overlay_widgets = []
        self._overlay_drop_widgets = []

    def _layout_assistant_overlay(self) -> None:
        window = self.window
        if window is None:
            self._clear_overlay_widgets()
            return

        self._clear_overlay_widgets()
        if self._assistant_panel == "normal":
            self._sync_drag_drop_registration()
            return
        try:
            width, height = self._window_size()
            self._set_window_geometry(width, height, keep_bottom_right=True)
        except tk.TclError:
            return

        if self._assistant_panel == "complete":
            self._build_completion_overlay(window)
        self._sync_drag_drop_registration()

    def _load_saved_position(self) -> tuple[int, int] | None:
        try:
            data = json.loads(self._position_state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, AttributeError):
            return None
        try:
            x = int(data["x"])
            y = int(data["y"])
        except (KeyError, TypeError, ValueError):
            return None
        return max(0, x), max(0, y)

    def _save_position(self) -> None:
        position = getattr(self, "_base_position", None) or getattr(self, "_position", None)
        if position is None:
            return
        try:
            self._position_state_path.parent.mkdir(parents=True, exist_ok=True)
            self._position_state_path.write_text(
                json.dumps({"x": int(position[0]), "y": int(position[1])}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"[WARNING] 小恐龙位置保存失败: {exc}")

    def _remembered_resident_position(self) -> tuple[int, int]:
        return self._base_position or self._load_saved_position() or self._position or self._default_position()

    def _snapshot_base_position(self) -> None:
        if self._assistant_panel != "normal":
            return
        self._remember_position()
        self._base_position = self._position

    def _build_completion_overlay(self, window: tk.Toplevel) -> None:
        close_button = self._completion_close_button(window)
        close_button.place(x=26, y=24, width=26, height=26)
        bubble = self._speech_bubble(
            window,
            "识别完成，请查看",
            width=278,
            height=92,
            font_size=15,
            anchor=tk.CENTER,
        )
        bubble.place(x=204, y=84, width=278, height=92)
        done = tk.Label(
            window,
            text="已完成",
            background="#f7f6f1",
            foreground=INK,
            anchor=tk.W,
            font=("TkDefaultFont", 16, "bold"),
            borderwidth=2,
            relief=tk.SOLID,
            padx=46,
        )
        done.place(x=58, y=206, width=388, height=44)
        self._bind_window_controls(done)
        button = CutCornerButton(
            window,
            text="返回主页面查看",
            command=self._restore_command_from_control,
            variant="default",
            font_family="TkDefaultFont",
            outer_background=self._background_color,
            min_width=210,
            min_height=44,
        )
        button.place(x=158, y=258, width=210, height=44)
        self._overlay_widgets.extend([close_button, bubble, done, button])
        # Every visible part of the completion card must remain a drop target;
        # otherwise a second batch only works when the file happens to land on
        # an uncovered part of the pet window.
        self._overlay_drop_widgets.extend([close_button, bubble, done, button])

    def _completion_close_button(self, window: tk.Toplevel) -> tk.Canvas:
        canvas = tk.Canvas(
            window,
            width=26,
            height=26,
            background=self._background_color,
            highlightthickness=0,
            bd=0,
            cursor="hand2",
        )

        def redraw(event: tk.Event | None = None) -> None:
            width = max(1, int(getattr(event, "width", 26)))
            height = max(1, int(getattr(event, "height", 26)))
            canvas.delete("all")
            pad = 7
            canvas.create_line(pad, pad, width - pad, height - pad, fill=INK, width=1)
            canvas.create_line(width - pad, pad, pad, height - pad, fill=INK, width=1)

        def close(_event: tk.Event | None = None) -> str:
            self._dismiss_completion_panel()
            return "break"

        canvas.bind("<Configure>", redraw, add="+")
        canvas.bind("<ButtonRelease-1>", close, add="+")
        redraw()
        return canvas

    def _schedule_completion_auto_hide(self) -> None:
        self._cancel_completion_auto_hide()
        try:
            self._completion_auto_hide_after_id = self.master.after(
                self.COMPLETION_AUTO_HIDE_MS,
                self._dismiss_completion_panel,
            )
        except (AttributeError, tk.TclError):
            self._completion_auto_hide_after_id = None

    def _cancel_completion_auto_hide(self) -> None:
        after_id = getattr(self, "_completion_auto_hide_after_id", None)
        if after_id is None:
            return
        try:
            self.master.after_cancel(after_id)
        except (AttributeError, tk.TclError):
            pass
        self._completion_auto_hide_after_id = None

    def _dismiss_completion_panel(self) -> None:
        self._cancel_completion_auto_hide()
        if self._assistant_panel != "complete":
            return
        self.set_state("idle")
        self.clear_assistant_panel()

    def _restore_command_from_control(self) -> None:
        self.restore_command()

    def _speech_bubble(
        self,
        window: tk.Toplevel,
        text: str,
        *,
        width: int,
        height: int,
        font_size: int,
        anchor: str,
    ) -> tk.Canvas:
        canvas = tk.Canvas(
            window,
            width=width,
            height=height,
            background=self._background_color,
            highlightthickness=0,
            bd=0,
        )

        def redraw(event: tk.Event | None = None) -> None:
            actual_width = max(1, int(getattr(event, "width", width)))
            actual_height = max(1, int(getattr(event, "height", height)))
            tail_height = 18
            body_bottom = actual_height - tail_height - 2
            canvas.delete("all")
            draw_pixel_box(
                canvas,
                2,
                2,
                actual_width - 3,
                body_bottom,
                fill=PANEL,
                line_color=INK,
                accent_color=INK,
                pixel=4,
                width=2,
                show_corners=False,
            )
            tail_x = 48
            tail = (
                tail_x,
                body_bottom - 1,
                tail_x - 18,
                actual_height - 4,
                tail_x + 5,
                body_bottom - 1,
            )
            canvas.create_polygon(*tail, fill=PANEL, outline="")
            canvas.create_line(*tail, fill=INK, width=2)
            text_x = actual_width // 2 if anchor == tk.CENTER else 32
            canvas.create_text(
                text_x,
                max(22, body_bottom // 2),
                text=text,
                fill=INK,
                anchor=anchor,
                justify=tk.CENTER if anchor == tk.CENTER else tk.LEFT,
                font=("TkDefaultFont", font_size, "bold"),
            )

        canvas.bind("<Configure>", redraw, add="+")
        redraw()
        self._bind_window_controls(canvas)
        return canvas

    def _bind_window_controls(self, widget: tk.Widget) -> None:
        self._bind_drag_controls(widget)
        self._bind_resize_controls(widget)

    def _bind_overlay_window_controls(self, widget: tk.Widget) -> None:
        self._bind_window_controls(widget)

    def _bind_drag_controls(self, widget: tk.Widget) -> None:
        widget.bind("<ButtonPress-1>", self._on_press, add="+")
        widget.bind("<B1-Motion>", self._on_drag, add="+")
        widget.bind("<ButtonRelease-1>", self._on_release, add="+")

    def _bind_resize_controls(self, widget: tk.Widget) -> None:
        widget.bind("<MouseWheel>", self._on_mouse_wheel, add="+")
        widget.bind("<Button-4>", lambda event: self._resize_by(1), add="+")
        widget.bind("<Button-5>", lambda event: self._resize_by(-1), add="+")

    def _window_exists(self) -> bool:
        try:
            return self.window is not None and self.window.winfo_exists()
        except tk.TclError:
            return False

    def _apply_topmost(self, window: tk.Toplevel) -> None:
        try:
            window.attributes("-topmost", True)
        except tk.TclError:
            pass

    def _default_position(self) -> tuple[int, int]:
        screen_width = self.master.winfo_screenwidth()
        screen_height = self.master.winfo_screenheight()
        width, height = self._window_size()
        x = max(0, screen_width - width - 28)
        y = max(0, screen_height - height - 84)
        return x, y

    def _set_window_geometry(
        self,
        width: int,
        height: int,
        *,
        x: int | None = None,
        y: int | None = None,
        keep_bottom_right: bool = False,
    ) -> None:
        window = self.window
        if window is None:
            return
        if x is None or y is None:
            x, y = self._anchored_position(width, height, keep_bottom_right=keep_bottom_right)
        self._position = (x, y)
        self._last_window_size = (width, height)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _anchored_position(self, width: int, height: int, *, keep_bottom_right: bool) -> tuple[int, int]:
        if not keep_bottom_right:
            return self._position or self._default_position()

        old_x, old_y = self._current_window_position()
        old_width, old_height = self._current_window_size()
        return (
            max(0, old_x + old_width - width),
            max(0, old_y + old_height - height),
        )

    def _current_window_position(self) -> tuple[int, int]:
        window = self.window
        if window is not None:
            try:
                return window.winfo_x(), window.winfo_y()
            except tk.TclError:
                pass
        return self._position or self._default_position()

    def _current_window_size(self) -> tuple[int, int]:
        if self._last_window_size is not None:
            return self._last_window_size
        window = self.window
        if window is not None:
            try:
                width = max(1, window.winfo_width())
                height = max(1, window.winfo_height())
                if width > 1 and height > 1:
                    return width, height
            except tk.TclError:
                pass
        return self._window_size()

    def _window_size(self) -> tuple[int, int]:
        if self._assistant_panel == "complete":
            return (520, 305)
        padding = self._padding()
        sprite_width = self._dino_sprite_width(self._pixel)
        sprite_height = len(DINO_SPRITE) * self._pixel
        width = max(158, sprite_width + self._dino_left_padding() + self._dino_right_padding())
        height = max(150, sprite_height + padding * 2 + self._jump_room() + 28)
        return width, height

    def _padding(self) -> int:
        return max(6, self._pixel * 2)

    def _dino_left_padding(self) -> int:
        return max(14, self._pixel * 4)

    def _dino_right_padding(self) -> int:
        return max(24, self._pixel * 4)

    def _dino_sprite_width(self, pixel: int) -> int:
        return max(len(row) for row in DINO_SPRITE) * pixel

    def _dino_x(self, width: int, pixel: int | None = None) -> int:
        sprite_width = self._dino_sprite_width(pixel or self._pixel)
        return max(self._dino_left_padding(), (width - sprite_width) // 2)

    def _jump_room(self) -> int:
        return self._pixel * 8

    def _remember_position(self) -> None:
        window = self.window
        if window is None:
            return
        try:
            self._position = (window.winfo_x(), window.winfo_y())
            if self._assistant_panel == "normal":
                self._base_position = self._position
                self._save_position()
            width = max(1, window.winfo_width())
            height = max(1, window.winfo_height())
            if width > 1 and height > 1:
                self._last_window_size = (width, height)
        except tk.TclError:
            pass

    def _redraw(self) -> None:
        label = self.image_label
        window = self.window
        if label is None or window is None:
            return
        try:
            width, height = self._window_size()
            label.configure(
                width=width,
                height=height,
                background=self._transparency_strategy().widget_background,
            )
            self._photo = self._photo_for_frame(width, height, window)
            label.configure(image=self._photo)
        except tk.TclError:
            pass

    def _photo_for_frame(
        self,
        width: int,
        height: int,
        master: tk.Misc,
    ) -> ImageTk.PhotoImage:
        key = self._frame_cache_key(width, height)
        photo = self._photo_cache.get(key)
        if photo is None:
            photo = ImageTk.PhotoImage(self._render_image(width, height), master=master)
            self._photo_cache[key] = photo
        return photo

    def _frame_cache_key(self, width: int, height: int) -> tuple[int, int, int, str, int, int]:
        if not self._motion_active():
            return (width, height, self._pixel, "idle", 0, 0)
        pose = self._pose if self._pose in {"run", "jump"} else "run"
        if pose == "jump":
            return (width, height, self._pixel, pose, 0, self._pose_ticks)
        return (width, height, self._pixel, pose, self._frame % 2, 0)

    def _render_image(self, width: int, height: int) -> Image.Image:
        if self._assistant_panel != "normal":
            return self._render_assistant_image(width, height)
        image = self._new_pet_image(width, height)
        draw = ImageDraw.Draw(image)
        if self._transparency_strategy().enabled:
            self._draw_transparent_scene_details(draw, width, height)
        else:
            self._draw_soft_scene_background(draw, width, height)
        x = self._dino_x(width)
        offset_y = self._padding() + self._current_jump_offset()
        fill = self._ink_fill(image)
        self._draw_dino_image(draw, x, offset_y, fill)
        self._draw_motion_feet(draw, x, offset_y, fill)
        self._draw_eating_details(
            draw,
            x,
            offset_y,
            self._pixel,
            fill,
            background_fill=self._pet_image_background_fill(image),
        )
        return image

    def _new_pet_image(self, width: int, height: int) -> Image.Image:
        strategy = self._transparency_strategy()
        return Image.new(strategy.image_mode, (width, height), strategy.image_background)

    def _pet_image_background_fill(self, image: Image.Image) -> str | tuple[int, int, int] | tuple[int, int, int, int]:
        background = self._transparency_strategy().image_background
        if image.mode == "RGBA":
            if isinstance(background, tuple):
                return background
            return ImageColor.getrgb(str(background)) + (255,)
        if isinstance(background, tuple):
            return background[:3]
        return background

    def _render_assistant_image(self, width: int, height: int) -> Image.Image:
        image = Image.new("RGB", (width, height), self._background_color)
        draw = ImageDraw.Draw(image)
        self._draw_soft_scene_background(draw, width, height)
        self._draw_assistant_border(draw, width, height)
        fill = self._ink_fill(image)

        pixel = max(5, min(7, self._pixel + 1))
        ground = height - 88
        x = 48
        y = ground - len(DINO_SPRITE) * pixel
        if self._pose == "jump":
            y -= max(10, self._current_jump_offset() // 2)
        elif self._frame % 4 < 2:
            y -= 3
        self._draw_dino_pixels(draw, x, y, pixel, fill)
        self._draw_eating_details(draw, x, y, pixel, fill)
        self._draw_panel_ground(draw, width, ground)
        if self._assistant_panel == "complete":
            self._draw_heart(draw, x + 122, y + 6)
        return image

    def _draw_eating_details(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        pixel: int,
        fill: tuple[int, int, int] | tuple[int, int, int, int],
        *,
        background_fill: str | tuple[int, int, int] | tuple[int, int, int, int] | None = None,
    ) -> None:
        if self._eating_ticks <= 0:
            return

        background = background_fill if background_fill is not None else self._background_color
        progress = (self.EAT_ANIMATION_FRAMES - self._eating_ticks) / max(1, self.EAT_ANIMATION_FRAMES - 1)
        mouth_x = x + 14 * pixel
        mouth_y = y + 3 * pixel
        if self._eating_ticks > 1:
            draw.rectangle(
                (
                    mouth_x,
                    mouth_y,
                    x + 20 * pixel,
                    y + 6 * pixel,
                ),
                fill=background,
            )
            draw.rectangle(
                (
                    x + 13 * pixel,
                    y + 6 * pixel,
                    x + 17 * pixel,
                    y + 7 * pixel,
                ),
                fill=fill,
            )
            self._draw_eaten_paper(draw, x + 19 * pixel, y + 5 * pixel, pixel, progress)

    def _draw_eaten_paper(
        self,
        draw: ImageDraw.ImageDraw,
        mouth_x: int,
        mouth_y: int,
        pixel: int,
        progress: float,
    ) -> None:
        if progress > 0.82:
            return
        start_x = mouth_x + max(26, pixel * 5)
        end_x = mouth_x + pixel
        paper_x = int(start_x + (end_x - start_x) * progress)
        paper_y = int(mouth_y - max(8, pixel * 2))
        shrink = max(0.0, (progress - 0.54) / 0.28)
        size = max(5, int(round(max(11, pixel * 3) * (1.0 - 0.58 * shrink))))
        draw.rectangle(
            (paper_x, paper_y, paper_x + size, paper_y + size),
            fill=PANEL,
            outline=INK,
            width=max(1, pixel // 3),
        )
        line_y = paper_y + max(3, size // 3)
        draw.line((paper_x + 3, line_y, paper_x + size - 3, line_y), fill=GRID, width=1)
        draw.line((paper_x + 3, line_y + 4, paper_x + size - 4, line_y + 4), fill=GRID, width=1)

    def _draw_assistant_border(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        border = INK
        inset = 7
        draw.rounded_rectangle(
            (inset, inset, width - inset - 1, height - inset - 1),
            radius=18,
            outline=border,
            width=2,
        )

    def _draw_dino_pixels(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        pixel: int,
        fill: tuple[int, int, int] | tuple[int, int, int, int],
    ) -> None:
        for row_index, row in enumerate(DINO_SPRITE):
            for column_index, cell in enumerate(row):
                if cell != "#":
                    continue
                left = x + column_index * pixel
                top = y + row_index * pixel
                draw.rectangle((left, top, left + pixel - 1, top + pixel - 1), fill=fill)

    def _draw_panel_ground(self, draw: ImageDraw.ImageDraw, width: int, ground: int) -> None:
        start = 36
        end = min(width - 158, 260)
        draw.line((start, ground, end, ground), fill=INK, width=2)
        for x in range(start, end, 34):
            draw.line((x, ground + 10, x + 9, ground + 10), fill=GRID, width=2)

    def _draw_heart(self, draw: ImageDraw.ImageDraw, x: int, y: int) -> None:
        p = 4
        blocks = (
            (1, 0),
            (2, 0),
            (4, 0),
            (5, 0),
            (0, 1),
            (1, 1),
            (2, 1),
            (3, 1),
            (4, 1),
            (5, 1),
            (6, 1),
            (1, 2),
            (2, 2),
            (3, 2),
            (4, 2),
            (5, 2),
            (2, 3),
            (3, 3),
            (4, 3),
            (3, 4),
        )
        for bx, by in blocks:
            draw.rectangle((x + bx * p, y + by * p, x + (bx + 1) * p - 1, y + (by + 1) * p - 1), fill=INK)

    def _draw_transparent_scene_details(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
    ) -> None:
        self._draw_ground_line(draw, width, height)

    def _draw_soft_scene_background(
        self,
        draw: ImageDraw.ImageDraw,
        width: int,
        height: int,
    ) -> None:
        edge = max(10, self._pixel * 3)
        outer = self._background_color
        draw.rectangle((0, 0, width, height), fill=outer)
        self._draw_cloud(draw, int(width * 0.14), int(height * 0.18), max(2, self._pixel - 1), "#ffffff")
        self._draw_cloud(draw, int(width * 0.58), int(height * 0.13), max(2, self._pixel - 1), "#ecebe6")
        self._draw_ground_line(draw, width, height)

        for inset in range(edge):
            ratio = inset / max(1, edge - 1)
            color = self._blend_color("#ffffff", outer, ratio)
            radius = max(8, edge - inset)
            draw.rounded_rectangle(
                (inset, inset, width - 1 - inset, height - 1 - inset),
                radius=radius,
                outline=color,
                width=1,
            )

    @staticmethod
    def _blend_color(start: str, end: str, ratio: float) -> str:
        ratio = max(0.0, min(1.0, ratio))
        start_rgb = ImageColor.getrgb(start)
        end_rgb = ImageColor.getrgb(end)
        blended = tuple(
            int(round(start_channel + (end_channel - start_channel) * ratio))
            for start_channel, end_channel in zip(start_rgb, end_rgb, strict=True)
        )
        return "#{:02x}{:02x}{:02x}".format(*blended)

    @staticmethod
    def _draw_cloud(
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        pixel: int,
        color: str,
    ) -> None:
        blocks = ((0, 2, 2, 3), (2, 1, 4, 3), (4, 0, 7, 3), (7, 1, 9, 3), (9, 2, 12, 3))
        for x1, y1, x2, y2 in blocks:
            draw.rectangle(
                (x + x1 * pixel, y + y1 * pixel, x + x2 * pixel, y + y2 * pixel),
                fill=color,
            )

    def _draw_ground_line(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        y = self._ground_y(height)
        start = max(self._pixel * 3, int(width * 0.18))
        end = min(width - self._pixel * 3, int(width * 0.84))
        draw.line((start, y, end, y), fill=INK, width=max(1, self._pixel // 2))
        tick = max(6, self._pixel * 2)
        for x in range(start + tick, end, tick * 2):
            draw.line((x, y + self._pixel, x + tick, y + self._pixel), fill=GRID, width=max(1, self._pixel // 2))

    def _ground_y(self, height: int) -> int:
        return height - self._padding()

    def _ink_fill(self, image: Image.Image) -> tuple[int, int, int] | tuple[int, int, int, int]:
        color = ImageColor.getrgb(INK)
        if image.mode == "RGBA":
            return color + (255,)
        return color

    def _draw_dino_image(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        fill: tuple[int, int, int] | tuple[int, int, int, int],
    ) -> None:
        for row_index, row in enumerate(DINO_SPRITE):
            for column_index, cell in enumerate(row):
                if cell != "#":
                    continue
                left = x + column_index * self._pixel
                top = y + row_index * self._pixel
                draw.rectangle(
                    (
                        left,
                        top,
                        left + self._pixel - 1,
                        top + self._pixel - 1,
                    ),
                    fill=fill,
                )

    def _current_jump_offset(self) -> int:
        if not self._motion_active() or self._pose != "jump":
            return self._jump_room()
        phase = min(1.0, max(0.0, self._pose_ticks / 8))
        lift = int(4 * phase * (1 - phase) * self._jump_room())
        return self._jump_room() - lift

    def _draw_motion_feet(
        self,
        draw: ImageDraw.ImageDraw,
        x: int,
        y: int,
        fill: tuple[int, int, int] | tuple[int, int, int, int],
    ) -> None:
        if not self._motion_active():
            return
        p = self._pixel
        leg_y = y + (len(DINO_SPRITE) - 1) * p
        if self._pose == "jump":
            return

        if self._frame % 2:
            feet = (
                (x + int(2.5 * p), leg_y, x + int(6.5 * p), leg_y + 2 * p),
                (x + 10 * p, leg_y, x + 13 * p, leg_y + p),
            )
        else:
            feet = (
                (x + 4 * p, leg_y, x + 7 * p, leg_y + p),
                (x + 10 * p, leg_y, x + 15 * p, leg_y + 2 * p),
            )
        for bounds in feet:
            draw.rectangle(bounds, fill=fill)

    def _motion_active(self) -> bool:
        return self._state == "working" or self._ambient_motion_enabled

    def _sync_animation(self) -> None:
        if not self._motion_active() or not self.is_visible():
            self._cancel_animation()
            return
        if self._animation_after_id is None:
            self._animation_after_id = self.master.after(self.ANIMATION_MS, self._animate)

    def _cancel_animation(self) -> None:
        if self._animation_after_id is None:
            return
        try:
            self.master.after_cancel(self._animation_after_id)
        except tk.TclError:
            pass
        self._animation_after_id = None

    def _cancel_eat_animation(self) -> None:
        if self._eat_animation_after_id is not None:
            try:
                self.master.after_cancel(self._eat_animation_after_id)
            except tk.TclError:
                pass
            self._eat_animation_after_id = None
        self._eating_ticks = 0
        self._photo_cache.clear()

    def _advance_eat_animation(self) -> None:
        self._eat_animation_after_id = None
        if self._eating_ticks <= 0:
            return
        self._eating_ticks -= 1
        self._photo_cache.clear()
        self._redraw()
        if self._eating_ticks > 0:
            self._eat_animation_after_id = self.master.after(
                self.EAT_ANIMATION_MS,
                self._advance_eat_animation,
            )

    def _animate(self) -> None:
        self._animation_after_id = None
        if not self._motion_active() or not self.is_visible():
            self._cancel_animation()
            self._redraw()
            return
        self._frame += 1
        if self._pose_ticks <= 0:
            self._pose = "jump" if random.random() < 0.28 else "run"
            self._pose_ticks = 8 if self._pose == "jump" else random.randint(4, 9)
        else:
            self._pose_ticks -= 1
        self._redraw()
        self._animation_after_id = self.master.after(self.ANIMATION_MS, self._animate)

    def _on_press(self, event: tk.Event) -> None:
        window = self.window
        if window is None:
            return
        self._press_pointer = (event.x_root, event.y_root)
        try:
            self._press_window = (window.winfo_x(), window.winfo_y())
        except tk.TclError:
            self._press_window = None
        self._dragged = False

    def _on_drag(self, event: tk.Event) -> None:
        window = self.window
        if window is None or self._press_pointer is None or self._press_window is None:
            return
        delta_x = event.x_root - self._press_pointer[0]
        delta_y = event.y_root - self._press_pointer[1]
        if max(abs(delta_x), abs(delta_y)) > self.DRAG_THRESHOLD:
            self._dragged = True
        x = self._press_window[0] + delta_x
        y = self._press_window[1] + delta_y
        self._position = (x, y)
        if self._assistant_panel == "normal":
            self._base_position = self._position
        try:
            window.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

    def _on_release(self, event: tk.Event) -> str:
        if self._press_pointer is None:
            return "break"
        delta_x = event.x_root - self._press_pointer[0]
        delta_y = event.y_root - self._press_pointer[1]
        self._remember_position()
        self._press_pointer = None
        self._press_window = None
        if self._dragged or max(abs(delta_x), abs(delta_y)) > self.DRAG_THRESHOLD:
            self._dragged = False
            return "break"
        self._dragged = False
        if self._assistant_panel == "normal" and time.monotonic() >= self._restore_blocked_until:
            self.restore_command()
        return "break"

    def _on_mouse_wheel(self, event: tk.Event) -> str:
        delta = 1 if getattr(event, "delta", 0) > 0 else -1
        self._resize_by(delta)
        return "break"

    def _resize_by(self, delta: int) -> str:
        if self._assistant_panel != "normal":
            return "break"
        next_pixel = max(self.MIN_PIXEL, min(self.MAX_PIXEL, self._pixel + delta))
        if next_pixel == self._pixel:
            return "break"

        window = self.window
        old_width, old_height = self._window_size()
        if window is not None:
            try:
                old_x = window.winfo_x()
                old_y = window.winfo_y()
            except tk.TclError:
                old_x, old_y = self._position or self._default_position()
        else:
            old_x, old_y = self._position or self._default_position()

        self._pixel = next_pixel
        self._photo_cache.clear()
        new_width, new_height = self._window_size()
        new_x = max(0, old_x + (old_width - new_width) // 2)
        new_y = max(0, old_y + (old_height - new_height) // 2)
        self._position = (new_x, new_y)
        self._base_position = self._position
        self._save_position()
        if window is not None:
            try:
                window.geometry(f"{new_width}x{new_height}+{new_x}+{new_y}")
            except tk.TclError:
                pass
        self._redraw()
        self._layout_assistant_overlay()
        return "break"

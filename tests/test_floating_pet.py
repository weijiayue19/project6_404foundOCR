from types import SimpleNamespace
import time
import tkinter as tk

from src.gui.floating_pet import FloatingDinoPet


class _FakeMaster:
    def __init__(self) -> None:
        self.after_calls = []
        self.cancelled = []

    def after(self, delay, callback):
        after_id = f"after-{len(self.after_calls) + 1}"
        self.after_calls.append((delay, callback, after_id))
        return after_id

    def after_idle(self, callback):
        after_id = f"after-{len(self.after_calls) + 1}"
        self.after_calls.append(("idle", callback, after_id))
        return after_id

    def after_cancel(self, after_id):
        self.cancelled.append(after_id)


def _pet_stub(master: _FakeMaster, *, visible: bool = True) -> FloatingDinoPet:
    pet = FloatingDinoPet.__new__(FloatingDinoPet)
    pet.master = master
    pet._state = "idle"
    pet._frame = 0
    pet._pose = "jump"
    pet._pose_ticks = 4
    pet._pixel = FloatingDinoPet.DEFAULT_PIXEL
    pet._background_color = FloatingDinoPet.OUTER_BACKGROUND
    pet._position = None
    pet._last_window_size = None
    pet._ambient_motion_enabled = False
    pet._animation_after_id = None
    pet._eat_animation_after_id = None
    pet._eating_ticks = 0
    pet._restore_blocked_until = 0.0
    pet._drop_dispatch_after_ids = set()
    pet.drop_started_command = None
    pet._assistant_panel = "normal"
    pet._photo_cache = {}
    pet.is_visible = lambda: visible
    pet._redraw = lambda: None
    return pet


def test_ambient_floating_pet_animates_after_non_working_state() -> None:
    master = _FakeMaster()
    pet = _pet_stub(master)
    pet._ambient_motion_enabled = True

    pet.set_state("done")

    assert pet._state == "done"
    assert pet._pose == "jump"
    assert pet._pose_ticks == 4
    assert pet._animation_after_id == "after-1"
    assert master.after_calls[0][0] == FloatingDinoPet.ANIMATION_MS


def test_non_ambient_pet_resets_and_cancels_after_non_working_state() -> None:
    master = _FakeMaster()
    pet = _pet_stub(master)
    pet._animation_after_id = "after-0"

    pet.set_state("ready")

    assert pet._pose == "idle"
    assert pet._pose_ticks == 0
    assert pet._animation_after_id is None
    assert master.cancelled == ["after-0"]
    assert master.after_calls == []


def test_ambient_frame_cache_uses_motion_pose_without_working_state() -> None:
    master = _FakeMaster()
    pet = _pet_stub(master)
    pet._state = "ready"
    pet._ambient_motion_enabled = True
    pet._pose = "jump"
    pet._pose_ticks = 5

    assert pet._frame_cache_key(88, 99) == (88, 99, FloatingDinoPet.DEFAULT_PIXEL, "jump", 0, 5)


def test_resident_pet_is_centered_in_default_window() -> None:
    master = _FakeMaster()
    pet = _pet_stub(master)

    width, _height = pet._window_size()
    sprite_width = pet._dino_sprite_width(FloatingDinoPet.DEFAULT_PIXEL)

    assert width == 158
    assert pet._dino_x(width) == (width - sprite_width) // 2


class _FakeTk:
    def __init__(self, windowing_system: str, *, fail: bool = False) -> None:
        self.windowing_system = windowing_system
        self.fail = fail
        self.calls = []

    def call(self, *args):
        self.calls.append(args)
        if self.fail:
            raise tk.TclError("windowing system unavailable")
        return self.windowing_system


class _TransparencyMaster(_FakeMaster):
    def __init__(self, windowing_system: str, *, fail_windowing_system: bool = False) -> None:
        super().__init__()
        self.tk = _FakeTk(windowing_system, fail=fail_windowing_system)


class _TransparencyWidget:
    def __init__(self, *, fail_attributes: bool = False) -> None:
        self.configure_calls = []
        self.attribute_calls = []
        self.fail_attributes = fail_attributes

    def configure(self, **kwargs):
        self.configure_calls.append(kwargs)

    def attributes(self, *args):
        self.attribute_calls.append(args)
        if self.fail_attributes:
            raise tk.TclError("unsupported transparency")


def _transparency_pet(windowing_system: str, *, fail_attributes: bool = False) -> FloatingDinoPet:
    pet = FloatingDinoPet.__new__(FloatingDinoPet)
    pet.master = _TransparencyMaster(windowing_system)
    pet.window = _TransparencyWidget(fail_attributes=fail_attributes)
    pet.image_label = _TransparencyWidget()
    pet._background_color = FloatingDinoPet.OUTER_BACKGROUND
    pet._photo_cache = {"stale": object()}
    return pet


def test_win32_transparency_uses_color_key_pet_image() -> None:
    pet = _transparency_pet("win32")

    pet._configure_transparency()

    assert pet.window.configure_calls[-1]["background"] == FloatingDinoPet.TRANSPARENT_COLOR_KEY
    assert pet.image_label.configure_calls[-1]["background"] == FloatingDinoPet.TRANSPARENT_COLOR_KEY
    assert pet.window.attribute_calls == [
        ("-transparentcolor", FloatingDinoPet.TRANSPARENT_COLOR_KEY),
    ]
    assert pet._photo_cache == {}

    image = pet._new_pet_image(2, 2)

    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) == (1, 2, 3)


def test_aqua_transparency_falls_back_to_opaque_pet_image() -> None:
    pet = _transparency_pet("aqua")

    pet._configure_transparency()

    assert pet.window.configure_calls[-1]["background"] == FloatingDinoPet.OUTER_BACKGROUND
    assert pet.image_label.configure_calls[-1]["background"] == FloatingDinoPet.OUTER_BACKGROUND
    assert pet.window.attribute_calls == []

    image = pet._new_pet_image(2, 2)

    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) == (244, 243, 238)


def test_unknown_windowing_system_falls_back_to_opaque_pet_image() -> None:
    pet = _transparency_pet("x11")

    pet._configure_transparency()

    assert pet.window.configure_calls[-1]["background"] == FloatingDinoPet.OUTER_BACKGROUND
    assert pet.image_label.configure_calls[-1]["background"] == FloatingDinoPet.OUTER_BACKGROUND
    assert pet.window.attribute_calls == []

    image = pet._new_pet_image(2, 2)

    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) == (244, 243, 238)


def test_windowing_system_tclerror_falls_back_to_opaque_pet_image() -> None:
    pet = _transparency_pet("win32")
    pet.master = _TransparencyMaster("win32", fail_windowing_system=True)

    pet._configure_transparency()

    assert pet.window.configure_calls[-1]["background"] == FloatingDinoPet.OUTER_BACKGROUND
    assert pet.image_label.configure_calls[-1]["background"] == FloatingDinoPet.OUTER_BACKGROUND
    assert pet.window.attribute_calls == []

    image = pet._new_pet_image(2, 2)

    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) == (244, 243, 238)


def test_transparency_tclerror_falls_back_to_opaque_pet_image() -> None:
    pet = _transparency_pet("win32", fail_attributes=True)

    pet._configure_transparency()

    assert pet.window.configure_calls[0]["background"] == FloatingDinoPet.TRANSPARENT_COLOR_KEY
    assert pet.window.configure_calls[-1]["background"] == FloatingDinoPet.OUTER_BACKGROUND
    assert pet.image_label.configure_calls[-1]["background"] == FloatingDinoPet.OUTER_BACKGROUND
    assert pet.window.attribute_calls == [
        ("-transparentcolor", FloatingDinoPet.TRANSPARENT_COLOR_KEY),
    ]

    image = pet._new_pet_image(2, 2)

    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) == (244, 243, 238)


def test_assistant_panel_stays_opaque_with_transparent_strategy() -> None:
    pet = _pet_stub(_FakeMaster())
    pet._transparency = pet._strategy_for_windowing_system("aqua")
    pet._assistant_panel = "complete"

    image = pet._render_image(520, 305)

    assert image.mode == "RGB"
    assert image.getpixel((0, 0)) == (244, 243, 238)


def test_clicking_resident_pet_background_restores_main_window() -> None:
    master = _FakeMaster()
    pet = _pet_stub(master)
    restore_calls = []
    pet.restore_command = lambda: restore_calls.append(True)
    pet._press_pointer = (100, 100)
    pet._press_window = (20, 30)
    pet._dragged = False
    pet._remember_position = lambda: None

    pet._on_release(SimpleNamespace(x_root=101, y_root=100))

    assert restore_calls == [True]
    assert pet._press_pointer is None
    assert pet._press_window is None


def test_dragging_resident_pet_does_not_restore_main_window() -> None:
    master = _FakeMaster()
    pet = _pet_stub(master)
    restore_calls = []
    pet.restore_command = lambda: restore_calls.append(True)
    pet._press_pointer = (100, 100)
    pet._press_window = (20, 30)
    pet._dragged = True
    pet._remember_position = lambda: None

    pet._on_release(SimpleNamespace(x_root=130, y_root=100))

    assert restore_calls == []


def test_mode_prompt_background_does_not_restore_main_window() -> None:
    master = _FakeMaster()
    pet = _pet_stub(master)
    restore_calls = []
    pet.restore_command = lambda: restore_calls.append(True)
    pet._assistant_panel = "mode_prompt"
    pet._press_pointer = (100, 100)
    pet._press_window = (20, 30)
    pet._dragged = False
    pet._remember_position = lambda: None

    pet._on_release(SimpleNamespace(x_root=101, y_root=100))

    assert restore_calls == []


def test_completion_background_does_not_restore_but_button_does() -> None:
    master = _FakeMaster()
    pet = _pet_stub(master)
    restore_calls = []
    pet.restore_command = lambda: restore_calls.append(True)
    pet._assistant_panel = "complete"
    pet._press_pointer = (100, 100)
    pet._press_window = (20, 30)
    pet._dragged = False
    pet._remember_position = lambda: None

    pet._on_release(SimpleNamespace(x_root=101, y_root=100))

    assert restore_calls == []

    pet._restore_command_from_control()

    assert restore_calls == [True]


class _GeometryWindow:
    def __init__(self, x: int, y: int, width: int, height: int) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.geometry_calls = []

    def geometry(self, value):
        self.geometry_calls.append(value)
        size, _, position = value.partition("+")
        width, height = size.split("x")
        self.width = int(width)
        self.height = int(height)
        if position:
            x, _, y = position.partition("+")
            self.x = int(x)
            self.y = int(y)

    def winfo_x(self):
        return self.x

    def winfo_y(self):
        return self.y

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height


def test_panel_resize_keeps_bottom_right_anchor() -> None:
    master = _FakeMaster()
    pet = _pet_stub(master)
    pet.window = _GeometryWindow(760, 610, 180, 150)
    pet._position = (760, 610)
    pet._last_window_size = (180, 150)

    pet._set_window_geometry(520, 335, keep_bottom_right=True)

    assert pet.window.geometry_calls == ["520x335+420+425"]
    assert pet._position == (420, 425)
    assert pet._last_window_size == (520, 335)


def test_resident_click_restore_is_temporarily_blocked_after_drop_hover() -> None:
    master = _FakeMaster()
    pet = _pet_stub(master)
    restore_calls = []
    pet.restore_command = lambda: restore_calls.append(True)
    pet._restore_blocked_until = time.monotonic() + 1
    pet._press_pointer = (100, 100)
    pet._press_window = (20, 30)
    pet._dragged = False
    pet._remember_position = lambda: None

    pet._on_release(SimpleNamespace(x_root=101, y_root=100))

    assert restore_calls == []


def test_eat_animation_opens_then_closes() -> None:
    master = _FakeMaster()
    pet = _pet_stub(master)

    pet.play_eat_animation()

    assert pet._eating_ticks == FloatingDinoPet.EAT_ANIMATION_FRAMES
    assert pet._eat_animation_after_id == "after-1"
    assert master.after_calls[0][0] == FloatingDinoPet.EAT_ANIMATION_MS

    for _ in range(FloatingDinoPet.EAT_ANIMATION_FRAMES):
        _delay, callback, _after_id = master.after_calls[-1]
        callback()

    assert pet._eating_ticks == 0
    assert pet._eat_animation_after_id is None


def test_mode_choice_does_not_clear_overlay_from_button_callback() -> None:
    master = _FakeMaster()
    pet = _pet_stub(master)
    pet._assistant_panel = "mode_prompt"
    pet._mode_choice_pending = False
    pet._mode_buttons = []
    choices = []
    clear_calls = []
    pet.mode_choice_command = lambda mode: choices.append(mode)
    pet.clear_assistant_panel = lambda: clear_calls.append(True)

    pet._choose_mode("document")

    assert choices == []
    assert clear_calls == []

    master.after_calls[0][1]()

    assert choices == ["document"]
    assert clear_calls == []


class _DndMaster:
    _subst_format_dnd = ("%D",)
    _subst_format_str_dnd = "%D"

    def __init__(self) -> None:
        self.after_calls = []

    def after(self, delay, callback):
        after_id = f"after-{len(self.after_calls) + 1}"
        self.after_calls.append((delay, callback, after_id))
        return after_id

    def drop_target_register(self, *dndtypes):
        self.registered_dndtypes = dndtypes

    def dnd_bind(self, sequence=None, func=None, add=None):
        self.dnd_bindings.append((sequence, func, add))
        return "binding-id"

    def drop_target_unregister(self):
        self.unregistered = True


class _DndWidget:
    def __init__(self) -> None:
        self.dnd_bindings = []
        self.unregistered = False

    def winfo_exists(self) -> bool:
        return True


def test_floating_pet_registers_drop_target_and_forwards_drop_event() -> None:
    master = _DndMaster()
    window = _DndWidget()
    label = _DndWidget()
    calls = []
    pet = FloatingDinoPet.__new__(FloatingDinoPet)
    pet.master = master
    pet.window = window
    pet.image_label = label
    pet.drop_command = lambda event: calls.append(event.data) or "break"
    pet.drop_started_command = lambda event: calls.append(("started", event.data))
    pet._dnd_files_type = "DND_Files"
    pet._drop_accept_action = "copy"
    pet._drop_enabled = True
    pet._drop_widgets = []
    pet._drop_dispatch_after_ids = set()
    pet._overlay_widgets = []
    pet.play_eat_animation = lambda: calls.append("eat")

    pet._sync_drag_drop_registration()

    assert window.registered_dndtypes == ("DND_Files",)
    assert label.registered_dndtypes == ("DND_Files",)
    assert [binding[0] for binding in window.dnd_bindings] == [
        "<<DropEnter>>",
        "<<DropPosition>>",
        "<<Drop>>",
    ]
    assert [binding[0] for binding in label.dnd_bindings] == [
        "<<DropEnter>>",
        "<<DropPosition>>",
        "<<Drop>>",
    ]
    assert label.dnd_bindings[0][1](SimpleNamespace(data="dropped.png")) == "copy"
    assert label.dnd_bindings[2][1](SimpleNamespace(data="dropped.png")) == "copy"
    assert calls == ["eat", ("started", "dropped.png")]
    assert master.after_calls[0][0] == FloatingDinoPet.DROP_DISPATCH_DELAY_MS

    master.after_calls[0][1]()

    assert calls == ["eat", ("started", "dropped.png"), "dropped.png"]

    pet.set_drag_drop_enabled(False)

    assert window.unregistered is True
    assert label.unregistered is True
    assert pet._drop_widgets == []

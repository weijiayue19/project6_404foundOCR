from pathlib import Path
import tkinter as tk
from types import SimpleNamespace

from PIL import Image

from src.gui.main_window import COPY, ImageEditState, MainWindow
from src.gui.pixel_theme import INK, PAPER
from src.region_selector import PreviewTransform
from src.task_queue import OCRTask, OCRTaskQueue


class _StringVarStub:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


class _TextStub:
    def __init__(self):
        self.value = ""

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value = value

    def get(self, *_args):
        return self.value


class _ButtonStub:
    def __init__(self):
        self.state = None
        self.configured = []

    def configure(self, **kwargs):
        self.configured.append(kwargs)
        if "state" in kwargs:
            self.state = kwargs["state"]


class _FakeProcess:
    def __init__(self, target, args):
        self.target = target
        self.args = args
        self.started = False

    def start(self):
        self.started = True


class _FakeProcessContext:
    def __init__(self):
        self.processes = []

    def Queue(self):
        return "output-queue"

    def Process(self, target, args):
        process = _FakeProcess(target, args)
        self.processes.append(process)
        return process


class _RootAfterStub:
    def __init__(self):
        self.scheduled = []
        self.cancelled = []
        self.titles = []

    def after(self, delay, callback):
        after_id = f"after-{len(self.scheduled)}"
        self.scheduled.append((after_id, delay, callback))
        return after_id

    def after_cancel(self, after_id):
        self.cancelled.append(after_id)

    def title(self, value):
        self.titles.append(value)


class _WidgetStub:
    def __init__(self):
        self.grid_calls = 0
        self.grid_remove_calls = 0
        self.configured = []

    def __str__(self):
        return f"widget-{id(self)}"

    def grid(self):
        self.grid_calls += 1

    def grid_remove(self):
        self.grid_remove_calls += 1

    def configure(self, **kwargs):
        self.configured.append(kwargs)

    def winfo_exists(self):
        return True


class _PaneStub:
    def __init__(self, width=1000, height=500):
        self.width = width
        self.height = height
        self.children = []
        self.add_calls = []
        self.forget_calls = []
        self.sash_places = []
        self.paneconfigure_calls = []

    def panes(self):
        return [str(child) for child in self.children]

    def add(self, child, **kwargs):
        if child not in self.children:
            self.children.append(child)
        self.add_calls.append((child, kwargs))

    def forget(self, child):
        if child in self.children:
            self.children.remove(child)
        self.forget_calls.append(child)

    def paneconfigure(self, child, **kwargs):
        self.paneconfigure_calls.append((child, kwargs))

    def sash_place(self, index, x, y):
        self.sash_places.append((index, x, y))

    def update_idletasks(self):
        return None

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def winfo_exists(self):
        return True


class _CanvasStub:
    def __init__(self, width=360, height=112):
        self.width = width
        self.height = height
        self.texts = []
        self.images = []
        self.lines = []
        self.deleted = []
        self.scrollregion = "0 0 0 0"
        self.last_xview = None

    def delete(self, *args):
        self.deleted.append(args)

    def create_text(self, *_args, **kwargs):
        self.texts.append(str(kwargs.get("text", "")))

    def create_image(self, *args, **kwargs):
        self.images.append((args, kwargs))

    def create_line(self, *args, **kwargs):
        self.lines.append((args, kwargs))
        return None

    def create_rectangle(self, *_args, **_kwargs):
        return None

    def configure(self, **kwargs):
        if "scrollregion" in kwargs:
            value = kwargs["scrollregion"]
            self.scrollregion = " ".join(str(item) for item in value)

    def cget(self, key):
        if key == "scrollregion":
            return self.scrollregion
        return ""

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def winfo_exists(self):
        return True

    def update_idletasks(self):
        return None

    def canvasx(self, value):
        return value

    def canvasy(self, value):
        return value

    def xview_moveto(self, fraction):
        self.last_xview = fraction


def test_reordering_images_keeps_selected_image_and_results_aligned():
    window = MainWindow.__new__(MainWindow)
    paths = [Path("first.png"), Path("second.png"), Path("third.png")]
    window.batch_image_paths = list(paths)
    window.batch_image_infos = [(path, 10, 10) for path in paths]
    window.image_regions = [None, (1, 2, 8, 9), None]
    window.image_edit_states = [
        ImageEditState(),
        ImageEditState(rotation_quarters=1, mirrored=True, vertical_mirrored=True),
        ImageEditState(rotation_quarters=2),
    ]
    window.current_batch_tasks = [OCRTask(image_path=str(path)) for path in paths]
    window.preview_image_index = 1
    window.image_path = paths[1]
    window._is_recognizing = False
    window.status_var = _StringVarStub()
    window._update_preview_path_label = lambda *_args: None
    window._refresh_preview_selector = lambda: None
    window._render_current_result_text = lambda: "second result"
    window._sync_result_actions = lambda _text: None

    window._move_image(1, 0)

    assert window.batch_image_paths == [paths[1], paths[0], paths[2]]
    assert [Path(task.image_path) for task in window.current_batch_tasks] == [
        paths[1],
        paths[0],
        paths[2],
    ]
    assert window.preview_image_index == 0
    assert window.image_path == paths[1]
    assert window.image_regions == [(1, 2, 8, 9), None, None]
    assert window.image_edit_states[0].rotation_quarters == 1
    assert window.image_edit_states[0].mirrored is True
    assert window.image_edit_states[0].vertical_mirrored is True


def test_selected_index_tracks_the_same_image_when_another_image_moves():
    assert MainWindow._selected_index_after_move(0, 0, 2) == 2
    assert MainWindow._selected_index_after_move(1, 0, 2) == 0
    assert MainWindow._selected_index_after_move(2, 0, 2) == 1
    assert MainWindow._selected_index_after_move(0, 2, 0) == 1
    assert MainWindow._selected_index_after_move(1, 2, 0) == 2
    assert MainWindow._selected_index_after_move(2, 2, 0) == 0


def test_appending_images_keeps_existing_queue_and_regions(tmp_path):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (20, 10), "white").save(first)
    Image.new("RGB", (30, 15), "white").save(second)

    window = MainWindow.__new__(MainWindow)
    window.batch_image_paths = [first]
    window.batch_image_infos = [(first, 20, 10)]
    window.image_regions = [(1, 2, 9, 8)]
    window.image_edit_states = [ImageEditState(rotation_quarters=1, mirrored=True)]
    window.preview_image_index = 0
    window.image_path = first
    window.current_batch_tasks = []
    window.current_result = None
    window.current_recognition_region = None
    window._thumbnail_photo_cache = {}
    window._thumbnail_failed_paths = set()
    window._preview_source_cache = {}
    window._preview_original_size_cache = {}
    window._temporary_image_paths = set()
    window.status_var = _StringVarStub()
    window.saved_status_var = _StringVarStub()
    window._refresh_preview_selector = lambda: None

    window._accept_images([second], append=True)

    assert window.batch_image_paths == [first, second]
    assert window.batch_image_infos == [(first, 20, 10), (second, 30, 15)]
    assert window.image_regions == [(1, 2, 9, 8), None]
    assert [(state.rotation_quarters, state.mirrored) for state in window.image_edit_states] == [
        (1, True),
        (0, False),
    ]
    assert window.preview_image_index == 0
    assert window.image_path == first


def test_rotating_current_image_preserves_transformed_region_and_clears_stale_results():
    window = MainWindow.__new__(MainWindow)
    paths = [Path("first.png"), Path("second.png")]
    window.batch_image_infos = [(paths[0], 10, 20), (paths[1], 10, 10)]
    window.batch_image_paths = list(paths)
    window.image_edit_states = [ImageEditState(), ImageEditState()]
    window.image_regions = [(1, 2, 8, 9), None]
    window.preview_image_index = 0
    window.image_path = paths[0]
    window.preview_original_size = (10, 20)
    window.preview_source = Image.new("RGB", (10, 20), "white")
    window._is_recognizing = False
    window.current_batch_tasks = [
        OCRTask(image_path=str(paths[0]), status=OCRTaskQueue.FINISHED, result_text="old first"),
        OCRTask(image_path=str(paths[1]), status=OCRTaskQueue.FINISHED, result_text="old second"),
    ]
    window.current_batch_tasks[0].extra["recognition_mode"] = "text"
    window.current_batch_tasks[1].extra["recognition_mode"] = "text"
    window._batch_tasks_by_mode = {"text": window.current_batch_tasks, "document": []}
    window._single_result_by_mode = {"text": {"result": object()}}
    window.current_result = object()
    window.current_record_id = "record"
    window.current_recognition_region = (1, 2, 8, 9)
    window.result_text = _TextStub()
    window.copy_feedback_var = _StringVarStub()
    window.status_var = _StringVarStub()
    window.saved_status_var = _StringVarStub()
    window.root = _RootAfterStub()
    window._copy_feedback_after_id = None
    window.copy_button = _ButtonStub()
    window.export_txt_button = _ButtonStub()
    window.clear_result_button = _ButtonStub()
    window._thumbnail_photo_cache = {paths[0]: "cached"}
    window._thumbnail_failed_paths = {paths[0]}
    window.region_selector = SimpleNamespace(clear=lambda: None)
    loaded = []
    window._load_selected_image = lambda *args: loaded.append(args)
    window._refresh_preview_selector = lambda: None
    window._refresh_dino_for_active_mode = lambda: None

    window._rotate_current_image()

    assert window.image_edit_states[0].rotation_quarters == 1
    assert window.image_regions == [(11, 1, 18, 8), None]
    assert window.selected_region == (11, 1, 18, 8)
    assert window.current_recognition_region == (11, 1, 18, 8)
    assert window.current_batch_tasks[0].status == OCRTaskQueue.WAITING
    assert window.current_batch_tasks[1].result_text == "old second"
    assert window.current_result is None
    assert window.current_record_id is None
    assert paths[0] not in window._thumbnail_photo_cache
    assert paths[0] not in window._thumbnail_failed_paths
    assert loaded == [(paths[0], 10, 20)]


def test_region_transform_helpers_follow_image_edit_geometry():
    region = (1, 2, 8, 9)

    assert MainWindow._transform_region_for_image_edit(region, (10, 20), rotate=True) == (11, 1, 18, 8)
    assert MainWindow._transform_region_for_image_edit(region, (10, 20), mirror=True) == (2, 2, 9, 9)
    assert MainWindow._transform_region_for_image_edit(region, (10, 20), mirror_vertical=True) == (1, 11, 8, 18)



def test_clear_result_text_only_clears_current_batch_image():
    window = MainWindow.__new__(MainWindow)
    paths = [Path("first.png"), Path("second.png"), Path("third.png")]
    window.batch_image_infos = [(path, 10, 10) for path in paths]
    window.current_batch_tasks = [
        OCRTask(
            image_path=str(paths[0]),
            status=OCRTaskQueue.FINISHED,
            result_text="first result",
        ),
        OCRTask(
            image_path=str(paths[1]),
            status=OCRTaskQueue.FINISHED,
            result_text="second result",
        ),
        OCRTask(
            image_path=str(paths[2]),
            status=OCRTaskQueue.FINISHED,
            result_text="third result",
        ),
    ]
    window.current_batch_tasks[1].extra["ocr_result"] = object()
    window.current_batch_tasks[1].extra["record_id"] = "record-second"
    window.preview_image_index = 1
    window.current_result = None
    window.current_record_id = "record-second"
    window.current_recognition_region = None
    window.result_text = _TextStub()
    window.status_var = _StringVarStub()
    window.copy_feedback_var = _StringVarStub()
    window.display_mode_var = _StringVarStub("全文拼接")
    window.root = _RootAfterStub()
    window._copy_feedback_after_id = None
    window._is_recognizing = False
    window.copy_button = _ButtonStub()
    window.export_txt_button = _ButtonStub()
    window.clear_result_button = _ButtonStub()

    window.clear_result_text()

    assert [task.result_text for task in window.current_batch_tasks] == [
        "first result",
        "",
        "third result",
    ]
    assert window.current_batch_tasks[1].status == OCRTaskQueue.FINISHED
    assert "ocr_result" not in window.current_batch_tasks[1].extra
    assert "record_id" not in window.current_batch_tasks[1].extra
    assert window.result_text.value == ""
    assert window.copy_button.state == "disabled"
    assert window.clear_result_button.state == "disabled"
    assert window.export_txt_button.state == "normal"
    assert window.status_var.value == "已清空当前图片的识别结果"


def test_start_recognition_only_runs_newly_added_batch_images(monkeypatch):
    window = MainWindow.__new__(MainWindow)
    paths = [Path("first.png"), Path("second.png"), Path("third.png")]
    window.batch_image_paths = list(paths)
    window.batch_image_infos = [(path, 10, 10) for path in paths]
    window.image_regions = [None, None, None]
    window.current_batch_tasks = [
        OCRTask(
            image_path=str(paths[0]),
            status=OCRTaskQueue.FINISHED,
            result_text="first result",
        ),
        OCRTask(
            image_path=str(paths[1]),
            status=OCRTaskQueue.FINISHED,
            result_text="second result",
        ),
    ]
    for task in window.current_batch_tasks:
        task.extra["gui_recorded"] = True
    window.preview_image_index = 0
    window.image_path = paths[0]
    window.ocr_engine = object()
    window.task_queue = object()
    window._is_recognizing = False
    window.recognition_mode = "text"
    window.selected_region = None
    window.current_result = None
    window.current_record_id = None
    window.current_recognition_region = None
    window._batch_process = None
    window._batch_process_queue = None
    window._batch_process_dead_polls = 0
    window.result_text = _TextStub()
    window.status_var = _StringVarStub()
    window.saved_status_var = _StringVarStub()
    window.root = _RootAfterStub()
    window.back_button = _ButtonStub()
    window.mode_switch_box = _ButtonStub()
    window.choose_button = _ButtonStub()
    window.choose_multi_button = _ButtonStub()
    window.preprocess_button = _ButtonStub()
    window.history_search_button = _ButtonStub()
    window.recognize_button = _ButtonStub()
    window.recognize_region_button = _ButtonStub()
    window._set_dino_state = lambda _state: None
    window._refresh_preview_selector = lambda: None
    window._current_preprocess_config = lambda *_args: "preprocess"
    window._current_render_mode = lambda: "plain"
    window._render_current_result_text = lambda: "first result"
    window._sync_result_actions = lambda _text: None
    window._update_current_batch_status = lambda: None
    window._set_result_actions_enabled = lambda _enabled: None
    window._set_copy_feedback = lambda _text: None
    process_context = _FakeProcessContext()
    monkeypatch.setattr("src.gui.main_window.mp.get_context", lambda _name: process_context)

    window.start_recognition()

    assert len(window.current_batch_tasks) == 3
    assert [task.result_text for task in window.current_batch_tasks[:2]] == [
        "first result",
        "second result",
    ]
    assert window.current_batch_tasks[2].status == OCRTaskQueue.WAITING
    assert len(process_context.processes) == 1
    process = process_context.processes[0]
    assert process.started is True
    assert process.args[0] == ["third.png"]
    assert process.args[5] == [None]
    assert process.args[6] == [2]
    assert window.status_var.value == "正在识别新增或待更新的 1 张图片；已有 2 张结果已保留……"


def test_finished_batch_result_is_not_reused_across_recognition_modes():
    window = MainWindow.__new__(MainWindow)
    path = Path("first.png")
    window.batch_image_infos = [(path, 10, 10)]
    window.current_batch_tasks = [
        OCRTask(
            image_path=str(path),
            status=OCRTaskQueue.FINISHED,
            result_text="text result",
        )
    ]
    window.current_batch_tasks[0].extra["recognition_mode"] = "text"
    window.current_batch_tasks[0].extra["region"] = None
    window.image_regions = [None]

    window.recognition_mode = "text"
    assert window._batch_task_can_be_reused(0, use_selected_region=False) is True

    window.recognition_mode = "document"
    assert window._batch_task_can_be_reused(0, use_selected_region=False) is False


def test_switching_recognition_mode_uses_that_modes_batch_results():
    window = MainWindow.__new__(MainWindow)
    paths = [Path("first.png"), Path("second.png")]
    text_task = OCRTask(
        image_path=str(paths[0]),
        status=OCRTaskQueue.FINISHED,
        result_text="快速模式结果",
    )
    text_task.extra["recognition_mode"] = "text"
    text_task.extra["region"] = None

    window.recognition_mode = "text"
    window.batch_image_infos = [(path, 10, 10) for path in paths]
    window.batch_image_paths = list(paths)
    window.current_batch_tasks = [text_task]
    window.preview_image_index = 0
    window.image_path = paths[0]
    window.current_result = None
    window.current_record_id = None
    window.current_recognition_region = None
    window.result_text = _TextStub()
    window.mode_switch_var = _StringVarStub("快速识别")
    window.status_var = _StringVarStub()
    window.root = _RootAfterStub()
    window.mode_switch_box = _ButtonStub()
    window.display_mode_var = _StringVarStub("全文拼接")
    window._is_recognizing = False
    dino_refreshes = []
    window._refresh_dino_for_active_mode = lambda: dino_refreshes.append(window.recognition_mode)
    window._show_mode_toast = lambda *_args: None
    window._sync_result_actions = lambda _text: None

    window._switch_recognition_mode()

    assert window.recognition_mode == "document"
    assert window.current_batch_tasks == []
    assert window.result_text.value == ""
    assert window.status_var.value == "当前图片 1/2：尚未识别；批量进度 0/2"

    window._switch_recognition_mode()

    assert window.recognition_mode == "text"
    assert window.current_batch_tasks == [text_task]
    assert window.result_text.value == "快速模式结果"
    assert window.status_var.value == "当前图片 1/2：识别完成；批量进度 1/2"
    assert dino_refreshes == ["document", "text"]


def test_large_preview_is_limited_but_original_path_and_size_are_kept(tmp_path):
    image_path = tmp_path / "large.png"
    Image.new("RGB", (2400, 1800), "white").save(image_path)

    window = MainWindow.__new__(MainWindow)
    window.batch_image_infos = [(image_path, 2400, 1800)]
    window._preview_source_cache = {}
    window._preview_original_size_cache = {}
    window.image_edit_states = []
    window.status_var = _StringVarStub()
    window._update_preview_path_label = lambda *_args: None
    window._render_preview = lambda: None
    window._update_image_index_status = lambda: None

    window._load_selected_image(image_path, 2400, 1800)

    assert window.image_path == image_path
    assert window.preview_original_size == (2400, 1800)
    assert window.preview_source.size[0] <= MainWindow.PREVIEW_SOURCE_MAX_SIZE[0]
    assert window.preview_source.size[1] <= MainWindow.PREVIEW_SOURCE_MAX_SIZE[1]


def test_transposed_original_size_respects_exif_orientation(tmp_path):
    image_path = tmp_path / "rotated.jpg"
    image = Image.new("RGB", (40, 20), "white")
    exif = image.getexif()
    exif[274] = 6
    image.save(image_path, exif=exif.tobytes())

    with Image.open(image_path) as opened:
        assert MainWindow._transposed_original_size(opened) == (20, 40)


def test_thumbnail_strip_defers_decoding_and_generates_one_thumbnail_per_after(monkeypatch):
    paths = [Path("very-long-file-name-that-should-not-be-drawn.png"), Path("second.png")]
    window = MainWindow.__new__(MainWindow)
    window.root = _RootAfterStub()
    window.thumbnail_canvas = _CanvasStub()
    window.batch_image_infos = [(path, 10, 10) for path in paths]
    window.preview_image_index = 0
    window.ui_font_family = "TkDefaultFont"
    window.thumbnail_photos = []
    window._thumbnail_card_bounds = []
    window._thumbnail_photo_cache = {}
    window._thumbnail_failed_paths = set()
    window._thumbnail_generation_after_id = None

    built = []
    window._build_thumbnail_photo = lambda path: built.append(path) or f"photo:{path.name}"

    window._render_thumbnail_strip()

    assert built == []
    assert "加载中" in window.thumbnail_canvas.texts
    assert all("very-long-file-name" not in text for text in window.thumbnail_canvas.texts)
    assert window.root.scheduled[0][1] == 30

    window.root.scheduled[0][2]()

    assert built == [paths[0]]
    assert window._thumbnail_generation_after_id is not None


def test_thumbnail_failure_is_cached_and_not_retried():
    path = Path("broken.png")
    window = MainWindow.__new__(MainWindow)
    window.root = _RootAfterStub()
    window.thumbnail_canvas = _CanvasStub()
    window.batch_image_infos = [(path, 10, 10)]
    window.preview_image_index = 0
    window.ui_font_family = "TkDefaultFont"
    window.thumbnail_photos = []
    window._thumbnail_card_bounds = []
    window._thumbnail_photo_cache = {}
    window._thumbnail_failed_paths = set()
    window._thumbnail_generation_after_id = None
    calls = []

    def fail(_path):
        calls.append(_path)
        raise ValueError("bad image")

    window._build_thumbnail_photo = fail

    window._render_thumbnail_strip()
    window.root.scheduled[0][2]()

    assert calls == [path]
    assert path in window._thumbnail_failed_paths
    assert "预览失败" in window.thumbnail_canvas.texts
    assert window._thumbnail_generation_after_id is None


def test_workspace_default_sash_uses_reasonable_left_width():
    window = MainWindow.__new__(MainWindow)
    window.root = _RootAfterStub()
    window.workspace_pane = _PaneStub(width=1000)
    window.workspace_pane.children = [_WidgetStub(), _WidgetStub()]
    window._workspace_sash_initialized = False
    window._workspace_sash_after_id = None

    window._set_default_workspace_sash()

    assert window.workspace_pane.sash_places == [(0, 580, 0)]
    assert window._workspace_sash_initialized is True


def test_preview_navigation_pane_can_show_and_hide():
    window = MainWindow.__new__(MainWindow)
    window.root = _RootAfterStub()
    window.preview_vertical_pane = _PaneStub()
    window.preview_canvas_frame = _WidgetStub()
    window.preview_navigation_frame = _WidgetStub()
    window.preview_vertical_pane.children = [window.preview_canvas_frame]
    window._preview_vertical_sash_initialized = True
    window._preview_vertical_sash_after_id = None

    window._set_preview_navigation_visible(True)

    assert window.preview_navigation_frame in window.preview_vertical_pane.children
    assert window.preview_vertical_pane.add_calls[-1][1]["minsize"] == 150
    assert window._preview_vertical_sash_initialized is False
    assert window._preview_vertical_sash_after_id is not None

    window._set_preview_navigation_visible(False)

    assert window.preview_navigation_frame not in window.preview_vertical_pane.children
    assert window.preview_vertical_pane.forget_calls == [window.preview_navigation_frame]
    assert window._preview_vertical_sash_after_id is None
    assert window.root.cancelled


def test_pending_ui_callbacks_are_all_cancelled():
    window = MainWindow.__new__(MainWindow)
    window.root = _RootAfterStub()
    callback_attributes = [
        "_thumbnail_drag_after_id",
        "_preview_after_id",
        "_thumbnail_resize_after_id",
        "_thumbnail_generation_after_id",
        "_preview_layout_after_id",
        "_workspace_sash_after_id",
        "_preview_vertical_sash_after_id",
        "_drop_after_id",
        "_drop_import_after_id",
        "_copy_feedback_after_id",
    ]
    for attribute in callback_attributes:
        setattr(window, attribute, attribute)

    window._cancel_pending_ui_callbacks()

    assert window.root.cancelled == callback_attributes
    assert all(getattr(window, attribute) is None for attribute in callback_attributes)


def test_clear_root_preserves_managed_floating_pet_window():
    class _FakeWindow:
        def __init__(self):
            self.destroyed = False

        def winfo_children(self):
            return []

        def destroy(self):
            self.destroyed = True

    class _FakeFrame:
        def __init__(self):
            self.destroyed = False

        def winfo_children(self):
            return []

        def destroy(self):
            self.destroyed = True

    class _RootStub:
        def __init__(self):
            self.cancelled = []
            self.frame = _FakeFrame()
            self.floating_pet_window = _FakeWindow()
            self.dialog_window = _FakeWindow()

        def winfo_children(self):
            return [self.frame, self.floating_pet_window, self.dialog_window]

    window = MainWindow.__new__(MainWindow)
    window.root = _RootStub()
    window._floating_pet = SimpleNamespace(window=window.root.floating_pet_window)
    window._mini_pixel_game_window = None
    window._start_scene_shortcut_sequences = ()

    window._clear_root()

    assert window.root.frame.destroyed is True
    assert window.root.floating_pet_window.destroyed is False
    assert window.root.dialog_window.destroyed is True


def _selection_window_for(image, original_size=None):
    window = MainWindow.__new__(MainWindow)
    window.preview_canvas = _CanvasStub()
    window.preview_source = image
    window.preview_original_size = original_size or image.size
    window.preview_transform = PreviewTransform(
        original_width=window.preview_original_size[0],
        original_height=window.preview_original_size[1],
        preview_width=100,
        preview_height=50,
        offset_x=10,
        offset_y=20,
    )
    return window


def test_selection_rectangle_uses_dark_ink_on_bright_image():
    window = _selection_window_for(Image.new("RGB", (100, 50), "white"))

    window._draw_selection_rectangle(20, 25, 80, 55)

    assert window.preview_canvas.lines
    assert {kwargs["fill"] for _args, kwargs in window.preview_canvas.lines} == {INK}


def test_selection_rectangle_uses_light_paper_on_dark_image():
    window = _selection_window_for(Image.new("RGB", (100, 50), "black"))

    window._draw_selection_rectangle(20, 25, 80, 55)

    assert window.preview_canvas.lines
    assert {kwargs["fill"] for _args, kwargs in window.preview_canvas.lines} == {PAPER}


def test_preview_luminance_maps_scaled_preview_source_to_original_coordinates():
    image = Image.new("RGB", (100, 50), "white")
    image.putpixel((50, 25), (0, 0, 0))
    window = _selection_window_for(image, original_size=(200, 100))
    window.preview_transform = PreviewTransform(
        original_width=200,
        original_height=100,
        preview_width=100,
        preview_height=50,
        offset_x=10,
        offset_y=20,
    )

    assert window._selection_outline_color(60, 45) == PAPER


def test_multi_image_region_recognition_runs_batch_with_mixed_regions():
    window = MainWindow.__new__(MainWindow)
    window.batch_image_infos = [
        (Path("first.png"), 10, 10),
        (Path("second.png"), 10, 10),
    ]
    window.image_path = Path("second.png")
    window.selected_region = (1, 2, 8, 9)
    calls = []
    window.start_recognition = lambda **kwargs: calls.append(kwargs)

    window._recognize_selected_region()

    assert calls == [{"use_selected_region": True}]


def test_pasted_file_list_is_appended(monkeypatch):
    window = MainWindow.__new__(MainWindow)
    window._is_recognizing = False
    window.batch_image_infos = [(Path("existing.png"), 10, 10)]
    window.status_var = _StringVarStub()
    calls = []
    window._accept_images = lambda paths, *, append: calls.append((paths, append))
    pasted = ["second.png", "third.jpg"]
    monkeypatch.setattr("src.gui.main_window.ImageGrab.grabclipboard", lambda: pasted)

    assert window._paste_clipboard_image() == "break"

    assert calls == [([Path("second.png"), Path("third.jpg")], True)]
    assert window.status_var.value == "已将 2 张图片粘贴到队尾；当前共 3 张"


def test_pasted_bitmap_is_appended_as_temporary_image(monkeypatch, tmp_path):
    window = MainWindow.__new__(MainWindow)
    window._is_recognizing = False
    window.batch_image_infos = [(Path("existing.png"), 10, 10)]
    window.status_var = _StringVarStub()
    window._temporary_directory = SimpleNamespace(name=str(tmp_path))
    calls = []
    window._accept_image = lambda path, **kwargs: calls.append((path, kwargs))
    monkeypatch.setattr(
        "src.gui.main_window.ImageGrab.grabclipboard",
        lambda: Image.new("RGB", (12, 8), "white"),
    )

    assert window._paste_clipboard_image() == "break"

    assert len(calls) == 1
    pasted_path, options = calls[0]
    assert pasted_path.exists()
    assert options == {"temporary": True, "append": True}
    assert window.status_var.value == "已将 1 张图片粘贴到队尾；当前共 2 张"


def test_drop_file_url_is_converted_to_local_path():
    path = MainWindow._path_from_drop_item("file:///Users/mugino/My%20Image.png")

    assert path == Path("/Users/mugino/My Image.png")


def test_windows_drop_file_url_strips_leading_url_slash():
    path = MainWindow._path_from_drop_item("file:///C:/Users/mugino/My%20Image.png")

    assert path == Path("C:/Users/mugino/My Image.png")


def test_windows_drop_braced_paths_with_spaces_are_split():
    window = MainWindow.__new__(MainWindow)
    window.root = SimpleNamespace(tk=tk.Tcl())

    paths = window._paths_from_drop_data(
        "{C:/Users/mugino/My Image.png} {D:/Scans/Page Two.png}"
    )

    assert paths == [
        Path("C:/Users/mugino/My Image.png"),
        Path("D:/Scans/Page Two.png"),
    ]


def test_drop_event_defers_image_import_until_after_callback_returns():
    class _TkStub:
        def splitlist(self, _data):
            return ["/tmp/drop one.png"]

    class _RootStub:
        def __init__(self):
            self.tk = _TkStub()
            self.scheduled = []

        def after(self, delay, callback):
            self.scheduled.append((delay, callback))
            return "after-id"

        def after_cancel(self, _after_id):
            return None

    window = MainWindow.__new__(MainWindow)
    window.root = _RootStub()
    window._drop_after_id = None
    window._is_recognizing = False
    window.recognition_mode = "text"
    window.status_var = _StringVarStub()
    calls = []
    window._accept_dropped_images = lambda paths, *, from_floating_pet=False: calls.append((paths, from_floating_pet))

    assert window._on_image_drop(SimpleNamespace(data="ignored")) == "copy"
    assert calls == []
    assert window.root.scheduled[0][0] == 80

    window.root.scheduled[0][1]()

    assert calls == [([Path("/tmp/drop one.png")], False)]


def test_drop_without_mode_schedules_normal_import_without_pet_prompt():
    class _TkStub:
        def splitlist(self, _data):
            return ["/tmp/drop one.png"]

    class _RootStub:
        def __init__(self):
            self.tk = _TkStub()
            self.scheduled = []

        def state(self):
            return "normal"

        def after(self, delay, callback):
            self.scheduled.append((delay, callback))
            return "after-id"

        def after_cancel(self, _after_id):
            return None

    window = MainWindow.__new__(MainWindow)
    window.root = _RootStub()
    window._drop_after_id = None
    window._is_recognizing = False
    window.recognition_mode = None
    window.status_var = _StringVarStub()
    imported = []
    window._accept_dropped_images = lambda paths, *, from_floating_pet=False: imported.append((paths, from_floating_pet))

    assert window._on_image_drop(SimpleNamespace(data="ignored")) == "copy"

    assert window.status_var.value == "正在导入 1 个文件……"
    assert window.root.scheduled[0][0] == 80
    assert imported == []

    window.root.scheduled[0][1]()

    assert imported == [([Path("/tmp/drop one.png")], False)]


def test_floating_pet_drop_auto_imports_without_mode_prompt():
    class _TkStub:
        def splitlist(self, _data):
            return ["/tmp/drop one.png"]

    class _RootStub:
        def __init__(self):
            self.tk = _TkStub()
            self.withdraw_count = 0
            self.idle_callbacks = []

        def state(self):
            return "normal"

        def withdraw(self):
            self.withdraw_count += 1

        def after_idle(self, callback):
            self.idle_callbacks.append(callback)

    window = MainWindow.__new__(MainWindow)
    window.root = _RootStub()
    window._is_recognizing = False
    window.recognition_mode = None
    window.status_var = _StringVarStub()
    window._is_hiding_to_pet = False
    imported = []
    window._accept_dropped_images = lambda paths, *, from_floating_pet=False: imported.append((paths, from_floating_pet))

    event = SimpleNamespace(data="ignored", _from_floating_pet=True)

    assert window._on_image_drop(event) == "copy"

    assert window.root.withdraw_count == 1
    assert imported == [([Path("/tmp/drop one.png")], True)]


def test_root_duplicate_drop_after_floating_pet_drop_is_ignored():
    class _TkStub:
        def splitlist(self, _data):
            return ["/tmp/drop one.png"]

    class _RootStub:
        def __init__(self):
            self.tk = _TkStub()
            self.withdraw_count = 0
            self.idle_callbacks = []
            self.scheduled = []

        def state(self):
            return "normal"

        def withdraw(self):
            self.withdraw_count += 1

        def after_idle(self, callback):
            self.idle_callbacks.append(callback)

        def after(self, delay, callback):
            self.scheduled.append((delay, callback))
            return "after-id"

    window = MainWindow.__new__(MainWindow)
    window.root = _RootStub()
    window._is_recognizing = False
    window.recognition_mode = "text"
    window.status_var = _StringVarStub()
    window._floating_pet_drop_guard_until = float("inf")
    window._floating_pet_drop_signature = ("/tmp/drop one.png",)

    assert window._on_image_drop(SimpleNamespace(data="ignored")) == "copy"

    assert window.root.withdraw_count == 1
    assert window.root.scheduled == []


def test_accept_dropped_images_imports_without_auto_start_for_normal_window_drop():
    window = MainWindow.__new__(MainWindow)
    window._is_recognizing = False
    window.recognition_mode = "text"
    window._drop_keep_root_hidden = False
    window.batch_image_infos = [(Path("existing.png"), 10, 10)]
    window.image_path = Path("new.png")
    window.status_var = _StringVarStub()
    window._floating_pet = SimpleNamespace(clear_assistant_panel=lambda: None, set_state=lambda _state: None)
    window._mode_for_dropped_paths = lambda paths: "text"
    window._ensure_drop_recognition_mode = lambda mode, *, keep_root_hidden=False: setattr(window, "recognition_mode", mode)
    accepted = []
    started = []
    window._accept_images = lambda paths, *, append: accepted.append((paths, append)) or window.batch_image_infos.append((paths[0], 10, 10))
    window.start_recognition = lambda: started.append(True)

    window._accept_dropped_images([Path("new.png")])

    assert accepted == [([Path("new.png")], True)]
    assert started == []
    assert getattr(window, "_pet_drop_recognition_active", False) is False


def test_accept_dropped_images_auto_starts_recognition_for_floating_pet_drop():
    window = MainWindow.__new__(MainWindow)
    window._is_recognizing = False
    window.recognition_mode = "text"
    window._drop_keep_root_hidden = True
    window.batch_image_infos = [(Path("existing.png"), 10, 10)]
    window.image_path = Path("new.png")
    window.status_var = _StringVarStub()
    window._is_hiding_to_pet = False
    window._floating_pet = SimpleNamespace(clear_assistant_panel=lambda: None, set_state=lambda _state: None)
    window._mode_for_dropped_paths = lambda paths: "text"
    window._ensure_drop_recognition_mode = lambda mode, *, keep_root_hidden=False: setattr(window, "recognition_mode", mode)
    accepted = []
    started = []
    withdrawn = []
    window.root = SimpleNamespace(after_idle=lambda callback: callback(), withdraw=lambda: withdrawn.append(True))
    window._accept_images = lambda paths, *, append: accepted.append((paths, append)) or window.batch_image_infos.append((paths[0], 10, 10))
    window.start_recognition = lambda: started.append(True)

    window._accept_dropped_images([Path("new.png")], from_floating_pet=True)

    assert accepted == [([Path("new.png")], True)]
    assert started == [True]
    assert window._pet_drop_recognition_active is True
    assert withdrawn


def test_pet_drop_queues_while_recognizing_and_starts_after_current_task():
    window = MainWindow.__new__(MainWindow)
    window._is_recognizing = True
    window._pending_pet_drop_queue = []
    window.status_var = _StringVarStub()
    withdrawn = []
    queued = []
    window._should_keep_root_hidden_for_pet_drop = lambda: True
    window._remember_floating_pet_drop_paths = lambda paths: None
    window._enqueue_pending_pet_drop = lambda paths, *, keep_root_hidden: queued.append((paths, keep_root_hidden))

    event = SimpleNamespace(data="queued.png", _from_floating_pet=True)
    window._paths_from_drop_data = lambda data: [Path(data)]

    result = window._on_image_drop(event)

    assert result == COPY
    assert queued == [([Path("queued.png")], True)]

    imported = []
    window.root = SimpleNamespace(after_idle=lambda callback: callback(), withdraw=lambda: withdrawn.append(True))
    window._is_hiding_to_pet = False
    window._pending_pet_drop_queue = [([Path("queued.png")], True)]
    window._mode_for_dropped_paths = lambda paths: "text"
    window._ensure_drop_recognition_mode = lambda mode, *, keep_root_hidden=False: None
    window._import_dropped_images_then_start = lambda paths, *, keep_root_hidden, auto_start: imported.append(
        (paths, keep_root_hidden, auto_start)
    )

    window._is_recognizing = False
    window._complete_pet_drop_recognition(success=True)

    assert window._pending_pet_drop_queue == []
    assert imported == [([Path("queued.png")], True, True)]


def test_large_dropped_image_import_is_chunked_before_starting_recognition():
    class _RootStub:
        def __init__(self):
            self.scheduled = []

        def after(self, delay, callback):
            self.scheduled.append((delay, callback))
            return f"after-{len(self.scheduled)}"

        def after_cancel(self, _after_id):
            return None

    window = MainWindow.__new__(MainWindow)
    window.root = _RootStub()
    window.DROP_IMPORT_CHUNK_SIZE = 2
    window._drop_import_after_id = None
    window._drop_keep_root_hidden = False
    window._is_recognizing = False
    window.batch_image_infos = []
    window.batch_image_paths = []
    window.image_path = None
    window.status_var = _StringVarStub()
    window._floating_pet = SimpleNamespace(clear_assistant_panel=lambda: None, set_state=lambda _state: None)
    window._mode_for_dropped_paths = lambda paths: "text"
    window._ensure_drop_recognition_mode = lambda mode, *, keep_root_hidden=False: setattr(window, "recognition_mode", mode)
    window._pet_drop_recognition_active = False
    window._pending_pet_drop_queue = []
    chunks = []
    started = []

    def accept(paths, *, append):
        chunks.append((list(paths), append))
        for path in paths:
            window.batch_image_infos.append((path, 10, 10))
            window.batch_image_paths.append(path)
        if window.image_path is None:
            window.image_path = paths[0]

    window._accept_images = accept
    window.start_recognition = lambda: started.append(True)

    paths = [Path(f"image-{index}.png") for index in range(5)]
    window._import_dropped_images_then_start(paths, keep_root_hidden=False, auto_start=True)

    assert chunks == [([paths[0], paths[1]], True)]
    assert started == []

    while window.root.scheduled:
        _delay, callback = window.root.scheduled.pop(0)
        callback()

    assert chunks == [
        ([paths[0], paths[1]], True),
        ([paths[2], paths[3]], True),
        ([paths[4]], True),
    ]
    assert started == [True]
    assert window._pet_drop_recognition_active is True


def test_pet_drop_completion_sets_done_state_and_shows_bubble():
    class _PetStub:
        def __init__(self):
            self.states = []
            self.completion_count = 0

        def set_state(self, state):
            self.states.append(state)

        def show_completion_message(self):
            self.completion_count += 1

    window = MainWindow.__new__(MainWindow)
    window._floating_pet = _PetStub()
    window._pet_drop_recognition_active = True

    window._show_pet_drop_completion()

    assert window._pet_drop_recognition_active is False
    assert window._floating_pet.states == ["done"]
    assert window._floating_pet.completion_count == 1


def test_root_drag_drop_toggles_floating_pet_drop_target(monkeypatch):
    class _RootStub:
        def __init__(self):
            self.registered = []
            self.bindings = []
            self.unregistered = False

        def update_idletasks(self):
            return None

        def drop_target_register(self, *dndtypes):
            self.registered.append(dndtypes)

        def dnd_bind(self, sequence=None, func=None, add=None):
            self.bindings.append((sequence, func, add))

        def drop_target_unregister(self):
            self.unregistered = True

    class _PetStub:
        def __init__(self):
            self.enabled_values = []

        def set_drag_drop_enabled(self, enabled):
            self.enabled_values.append(enabled)

    monkeypatch.setattr("src.gui.main_window.DND_FILES", "DND_Files")
    window = MainWindow.__new__(MainWindow)
    window.root = _RootStub()
    window._floating_pet = _PetStub()
    window._on_image_drop = lambda _event: "copy"

    window._enable_drag_drop()
    window._enable_drag_drop()
    window._disable_drag_drop()

    assert window.root.registered == [("DND_Files",)]
    assert window.root.bindings[0][:2] == ("<<DropEnter>>", window._accept_image_drop)
    assert window.root.bindings[1][:2] == ("<<DropPosition>>", window._accept_image_drop)
    assert window.root.bindings[2][:2] == ("<<Drop>>", window._on_image_drop)
    assert window._floating_pet.enabled_values == [True, True, False]
    assert window.root.unregistered is True

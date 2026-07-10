"""OCR 桌面工具主窗口。"""

from collections.abc import Callable
import json
import multiprocessing as mp
import queue
import tempfile
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import unquote, urlparse
from uuid import uuid4

from PIL import Image, ImageGrab, ImageOps, ImageTk

try:
    from tkinterdnd2 import COPY, DND_FILES
except ImportError:
    COPY = "copy"
    DND_FILES = None

from src.gui.floating_pet import FloatingDinoPet
from src.gui.history_search_window import open_history_search_window
from src.gui.main_window_floating_pet import MainWindowFloatingPetMixin
from src.gui.main_window_state import (
    DEEP_MODE_LABEL,
    FAST_MODE_LABEL,
    PREPROCESS_STEP_LABELS,
    PREPROCESS_STEP_ORDER,
    ImageEditState,
)
from src.gui.main_window_ui_utils import Tooltip as _Tooltip, draw_result_action_icon as _draw_result_action_icon
from src.gui.mini_game_window import MiniPixelGameWindow
from src.gui.window_utils import create_independent_window
from src.gui.pixel_theme import (
    GRID,
    INK,
    MUTED,
    PANEL,
    PAPER,
    CutCornerButton,
    PixelBorderFrame,
    PixelKeyPanel,
    PixelProcessRail,
    PixelScene,
    PixelScrollbar,
    configure_pixel_theme,
    draw_pixel_box,
    draw_pixel_dino,
)
from src.history_manager import HistoryManager
from src.image_utils import detect_upload_type, render_pdf_pages, validate_upload_path
from src.models.ocr_result import OcrResult
from src.ocr_engine import OcrEngine, OcrExecutionResult, OcrMode, OcrRequest, PreprocessConfig
from src.region_selector import RegionSelector, build_preview_transform
from src.services.batch_export import build_merged_batch_text, build_separate_txt_names
from src.services.batch_process import run_batch_process
from src.storage_manager import OCRStorageManager
from src.task_queue import OCRTask, OCRTaskQueue, TaskQueue, TaskStatus


class MainWindow(MainWindowFloatingPetMixin):
    """负责选图、后台识别和结果展示。"""

    IMAGE_TYPES = [("图片文件", "*.jpg *.jpeg *.png *.bmp")]
    DOCUMENT_TYPES = [("图片或 PDF 文档", "*.jpg *.jpeg *.png *.bmp *.pdf")]
    PREVIEW_SOURCE_MAX_SIZE = (1600, 1200)
    DROP_IMPORT_CHUNK_SIZE = 40
    FLOATING_PET_DROP_GUARD_SECONDS = 2.5
    UI_FONT_CANDIDATES = (
        "Microsoft YaHei UI",
        "Microsoft YaHei",
        "PingFang SC",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "Segoe UI",
    )

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("本地 OCR 图片快速识别")
        self._size_window(874, 564, min_width=640, min_height=480)

        self.recognition_mode: OcrMode | None = None
        self.image_path: Path | None = None
        self.batch_image_paths: list[Path] = []
        self.batch_image_infos: list[tuple[Path, int, int]] = []
        self.image_regions: list[tuple[int, int, int, int] | None] = []
        self.image_edit_states: list[ImageEditState] = []
        self.preprocess_step_order: list[str] = list(PREPROCESS_STEP_ORDER)
        self.preview_image_index = 0
        self.current_result: OcrResult | None = None
        self.current_record_id: str | None = None
        self.current_batch_tasks: list[OCRTask] = []
        self._batch_tasks_by_mode: dict[OcrMode, list[OCRTask]] = {"text": [], "document": []}
        self._single_result_by_mode: dict[OcrMode, dict[str, object]] = {}
        self._batch_progress_queue: queue.Queue[tuple[int, int, OCRTask]] = queue.Queue()
        self._batch_process = None
        self._batch_process_queue = None
        self._batch_process_dead_polls = 0
        self.preview_source: Image.Image | None = None
        self.preview_original_size: tuple[int, int] | None = None
        self.preview_photo: ImageTk.PhotoImage | None = None
        self.preview_pdf_pages: list[Image.Image] = []
        self.preview_pdf_photos: list[ImageTk.PhotoImage | None] = []
        self.preview_pdf_render_specs: list[tuple[Image.Image, int, int, int, int]] = []
        self.preview_pdf_page_positions: list[tuple[int, int, int, int]] = []
        self.thumbnail_photos: list[ImageTk.PhotoImage] = []
        self._thumbnail_photo_cache: dict[Path, ImageTk.PhotoImage] = {}
        self._thumbnail_failed_paths: set[Path] = set()
        self._preview_source_cache: dict[Path, Image.Image] = {}
        self._preview_original_size_cache: dict[Path, tuple[int, int]] = {}
        self._thumbnail_card_bounds: list[tuple[int, int, int, int]] = []
        self._thumbnail_drag_index: int | None = None
        self._thumbnail_drag_after_id: str | None = None
        self._thumbnail_drag_active = False
        self._preview_after_id: str | None = None
        self._thumbnail_resize_after_id: str | None = None
        self._thumbnail_generation_after_id: str | None = None
        self._preview_layout_after_id: str | None = None
        self._pdf_preview_after_id: str | None = None
        self._pdf_preview_render_after_id: str | None = None
        self._workspace_sash_after_id: str | None = None
        self._preview_vertical_sash_after_id: str | None = None
        self._drop_after_id: str | None = None
        self._drop_import_after_id: str | None = None
        self._copy_feedback_after_id: str | None = None
        self._mode_toast_window: tk.Toplevel | None = None
        self._mode_toast_after_id: str | None = None
        self._mode_toast_fade_after_id: str | None = None
        self._start_scene_shortcut_sequences: tuple[str, ...] = ()
        self._temporary_image_paths: set[Path] = set()
        self._temporary_directory = tempfile.TemporaryDirectory(prefix="project6_ocr_")
        self._is_recognizing = False
        self._last_click_region: str | None = None
        self.ui_font_family = self._pick_ui_font_family()
        self.ui_style = configure_pixel_theme(self.root, self.ui_font_family)
        self.ocr_engine: OcrEngine | None = None
        self.task_queue: TaskQueue[object] | None = None
        self.current_task_id: int | None = None
        self._recognizing_single_index: int | None = None
        self.current_recognition_region: tuple[int, int, int, int] | None = None
        self.region_selector = RegionSelector()
        self.selected_region: tuple[int, int, int, int] | None = None
        self.preview_transform = None
        self.history_manager = HistoryManager()
        self.storage_manager = OCRStorageManager()
        self._floating_pet = FloatingDinoPet(
            self.root,
            self.restore_from_pet,
            drop_command=self._on_image_drop,
            drop_started_command=self._mark_floating_pet_drop_started,
            dnd_files_type=DND_FILES,
            drop_accept_action=COPY,
            mode_choice_command=self._start_pending_drop_with_mode,
        )
        self._is_quitting = False
        self._is_hiding_to_pet = False
        self._is_restoring_from_pet = False
        self._minimize_after_id: str | None = None
        self._mini_pixel_game_window: MiniPixelGameWindow | None = None
        self._pending_pet_drop_paths: list[Path] = []
        self._pending_pet_drop_keep_root_hidden = False
        self._pet_drop_recognition_active = False
        self._drop_keep_root_hidden = False
        self._root_drop_enabled = False
        self._floating_pet_drop_guard_until = 0.0
        self._floating_pet_drop_signature: tuple[str, ...] | None = None

        self.path_var = tk.StringVar(value="尚未选择图片")
        self.preview_choice_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="就绪")
        self.mode_switch_var = tk.StringVar(value=FAST_MODE_LABEL)
        self.image_index_var = tk.StringVar(value="当前图片：0 / 0")
        self.saved_status_var = tk.StringVar(value="最近保存：无")
        self.copy_feedback_var = tk.StringVar(value="")
        self.display_mode_var = tk.StringVar(value="全文拼接")
        self._configure_fonts()
        self._configure_result_icon_style()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.bind("<Unmap>", self._on_root_unmap, add="+")
        self._build_start_screen()

    def open_mini_pixel_game_window(self) -> None:
        if self._mini_pixel_game_window is None:
            self._mini_pixel_game_window = MiniPixelGameWindow(self.root)
        self._mini_pixel_game_window.show()

    def _build_start_screen(self) -> None:
        """Show the OCR mode choice screen before entering the workspace."""

        self.root.title("本地 OCR - 选择识别方式")
        self._unbind_image_paste()
        container = ttk.Frame(self.root, style="App.TFrame")
        container.pack(fill=tk.BOTH, expand=True)
        scene = PixelScene(container)
        scene.place(x=0, y=0, relwidth=1, relheight=1)

        brand = ttk.Frame(container, style="App.TFrame")
        brand.place(relx=0.04, rely=0.06)
        ttk.Label(
            brand,
            text="404 Found OCR",
            style="Title.TLabel",
            font=(self.ui_font_family, 32, "bold"),
        ).pack(anchor=tk.W)
        ttk.Label(
            brand,
            text="把图片，跑成文字。",
            style="Eyebrow.TLabel",
            font=(self.ui_font_family, 13, "bold"),
        ).pack(anchor=tk.W, pady=(5, 0))

        mode_note = ttk.Label(
            container,
            text="HOVER TO PREVIEW  /  选择一种识别方式",
            style="Eyebrow.TLabel",
        )
        mode_note.place(relx=0.60, rely=0.095)

        text_card = PixelBorderFrame(container, padding=18)
        text_card.place(relx=0.60, rely=0.16, relwidth=0.36, relheight=0.25)
        text_card.columnconfigure(0, weight=1)
        ttk.Label(text_card, text="01", style="PanelMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(text_card, text=FAST_MODE_LABEL, style="CardTitle.TLabel").grid(row=1, column=0, sticky="w", pady=(5, 5))
        ttk.Label(
            text_card,
            text="截图 / 图片 / 快速提取\n轻量模型 · CPU 更快",
            style="PanelMuted.TLabel",
            justify=tk.LEFT,
        ).grid(row=2, column=0, sticky="w")
        default_button = CutCornerButton(
            text_card,
            text="开始使用",
            command=lambda: self._select_mode("text"),
            variant="primary",
            font_family=self.ui_font_family,
            outer_background=PANEL,
            min_width=104,
            min_height=36,
        )
        default_button.grid(row=0, column=1, rowspan=3, sticky="e", padx=(14, 0))

        document_card = PixelBorderFrame(container, padding=18)
        document_card.place(relx=0.60, rely=0.46, relwidth=0.36, relheight=0.25)
        document_card.columnconfigure(0, weight=1)
        ttk.Label(document_card, text="02", style="PanelMuted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(document_card, text=DEEP_MODE_LABEL, style="CardTitle.TLabel").grid(row=1, column=0, sticky="w", pady=(5, 5))
        ttk.Label(
            document_card,
            text="标题 / 段落 / 表格\n完整模型 · 复杂文档",
            style="PanelMuted.TLabel",
            justify=tk.LEFT,
        ).grid(row=2, column=0, sticky="w")
        document_button = CutCornerButton(
            document_card,
            text="开始使用",
            command=lambda: self._select_mode("document"),
            variant="primary",
            font_family=self.ui_font_family,
            outer_background=PANEL,
            min_width=104,
            min_height=36,
        )
        document_button.grid(row=0, column=1, rowspan=3, sticky="e", padx=(14, 0))

        history_button = CutCornerButton(
            container,
            text="历史查询",
            command=self.open_history_search_window,
            variant="default",
            font_family=self.ui_font_family,
            outer_background=PAPER,
            min_width=104,
            min_height=38,
        )
        history_button.place(relx=0.96, rely=0.90, anchor="se")

        def set_manual_drive_lock(locked: bool) -> None:
            scene.set_manual_drive(locked)
            if locked:
                scene.set_mode("idle")

        key_panel = PixelKeyPanel(
            container,
            boost_command=scene.boost,
            jump_command=scene.manual_jump,
            on_lock_change=set_manual_drive_lock,
            font_family=self.ui_font_family,
            outer_background=PAPER,
        )
        key_panel.place(relx=0.96, rely=0.90, x=-120, anchor="se")
        key_hint = tk.Label(
            container,
            text="J加速 K跳跃 长按锁定",
            background=PAPER,
            foreground=MUTED,
            font=(self.ui_font_family, 9, "bold"),
            anchor=tk.CENTER,
        )
        key_hint.place(relx=0.96, rely=0.90, x=-197, y=8, anchor="n", width=154, height=18)

        footer_note = ttk.Frame(container, style="App.TFrame")
        footer_note.place(relx=0.04, rely=0.88)
        ttk.Label(
            footer_note,
            text="LOCAL FIRST  ·  IMAGE IN / TEXT OUT",
            style="Eyebrow.TLabel",
        ).pack(anchor=tk.W)
        ttk.Label(
            footer_note,
            text="小恐龙在本地完成思考，图片与文字不会离开你的设备。",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(4, 0))

        self._bind_mode_preview(
            scene,
            text_card,
            document_card,
            default_button,
            document_button,
            key_panel,
        )
        self._bind_start_scene_shortcuts(scene, key_panel)
        self._enable_drag_drop()

    def _bind_mode_preview(
        self,
        scene: PixelScene,
        text_card: tk.Widget,
        document_card: tk.Widget,
        text_button: tk.Widget,
        document_button: tk.Widget,
        key_panel: PixelKeyPanel,
    ) -> None:
        """Drive the mascot from pointer position and keyboard focus."""

        targets = ((text_card, "fast"), (document_card, "jump"))

        def pointer_inside(widget: tk.Widget) -> bool:
            pointer_x, pointer_y = self.root.winfo_pointerxy()
            left = widget.winfo_rootx()
            top = widget.winfo_rooty()
            return (
                left <= pointer_x < left + widget.winfo_width()
                and top <= pointer_y < top + widget.winfo_height()
            )

        def auto_controls_blocked() -> bool:
            blocked = key_panel.is_locked()
            scene.set_manual_drive(blocked)
            return blocked

        def pointer_mode() -> str | None:
            if auto_controls_blocked():
                return None
            for card, mode in targets:
                if pointer_inside(card):
                    return mode
            return "idle"

        def set_auto_mode(mode: str) -> None:
            if not auto_controls_blocked():
                scene.set_mode(mode)

        def sync_from_pointer(_event: tk.Event | None = None) -> None:
            def apply_pointer_mode() -> None:
                if scene.winfo_exists():
                    mode = pointer_mode()
                    if mode is not None:
                        scene.set_mode(mode)

            self.root.after(18, apply_pointer_mode)

        def enter_key_panel(_event: tk.Event | None = None) -> None:
            if scene.winfo_exists():
                scene.set_manual_drive(key_panel.is_locked())

        def descendants(widget: tk.Widget) -> list[tk.Widget]:
            children = [widget]
            for child in widget.winfo_children():
                children.extend(descendants(child))
            return children

        for card, mode in targets:
            for widget in descendants(card):
                widget.bind("<Enter>", lambda _event, value=mode: set_auto_mode(value), add="+")
                widget.bind("<Leave>", sync_from_pointer, add="+")

        for widget in descendants(key_panel):
            widget.bind("<Enter>", enter_key_panel, add="+")
            widget.bind("<Leave>", sync_from_pointer, add="+")

        text_button.bind("<FocusIn>", lambda _event: set_auto_mode("fast"), add="+")
        document_button.bind("<FocusIn>", lambda _event: set_auto_mode("jump"), add="+")
        text_button.bind("<FocusOut>", sync_from_pointer, add="+")
        document_button.bind("<FocusOut>", sync_from_pointer, add="+")

    def _bind_start_scene_shortcuts(self, scene: PixelScene, key_panel: PixelKeyPanel) -> None:
        self._unbind_start_scene_shortcuts()

        def boost(_event: tk.Event) -> str:
            if scene.winfo_exists() and key_panel.is_locked():
                scene.boost()
            return "break"

        def jump(_event: tk.Event) -> str:
            if scene.winfo_exists() and key_panel.is_locked():
                scene.manual_jump()
            return "break"

        bindings = (
            ("<KeyPress-j>", boost),
            ("<KeyPress-J>", boost),
            ("<KeyPress-k>", jump),
            ("<KeyPress-K>", jump),
        )
        self._start_scene_shortcut_sequences = tuple(sequence for sequence, _handler in bindings)
        for sequence, handler in bindings:
            self.root.bind(sequence, handler)

    def _unbind_start_scene_shortcuts(self) -> None:
        for sequence in self._start_scene_shortcut_sequences:
            self.root.unbind(sequence)
        self._start_scene_shortcut_sequences = ()

    def _select_mode(self, mode: OcrMode) -> None:
        """Create the OCR services and enter the recognition workspace."""

        self._clear_root()
        self.recognition_mode = mode
        self.mode_switch_var.set(DEEP_MODE_LABEL if mode == "document" else FAST_MODE_LABEL)
        self.ocr_engine = OcrEngine()
        self.task_queue = TaskQueue()
        mode_name = DEEP_MODE_LABEL if mode == "document" else FAST_MODE_LABEL
        self.root.title(f"本地 OCR - {mode_name}")
        self._size_window(1310, 819, min_width=900, min_height=620)
        self.status_var.set(
            "深度识别就绪（CPU 推理可能需要较长时间）"
            if mode == "document"
            else "快速识别就绪"
        )
        self._build_ui()
        self._sync_mode_labels()

    def _sync_mode_labels(self) -> None:
        """根据识别模式切换导入与识别按钮文案。"""

        is_document_mode = self._active_recognition_mode() == "document"
        if hasattr(self, "choose_button"):
            self.choose_button.configure(text="＋ 添加文档" if is_document_mode else "＋ 添加图片")
        if hasattr(self, "recognize_button"):
            self.recognize_button.configure(text="▶ 识别文档" if is_document_mode else "▶ 识别整图")

    def _clear_root(self) -> None:
        self._unbind_start_scene_shortcuts()
        self._cancel_widget_callbacks(self.root)
        for child in self.root.winfo_children():
            if self._should_preserve_root_child(child):
                continue
            try:
                child.destroy()
            except tk.TclError:
                pass

    def _should_preserve_root_child(self, child: tk.Misc) -> bool:
        floating_pet = getattr(self, "_floating_pet", None)
        if floating_pet is not None and child is getattr(floating_pet, "window", None):
            return True
        mini_window = getattr(self, "_mini_pixel_game_window", None)
        return mini_window is not None and child is getattr(mini_window, "window", None)

    def _cancel_widget_callbacks(self, widget: tk.Misc) -> None:
        """Cancel widget-owned animation callbacks before replacing a screen."""

        for child in widget.winfo_children():
            if self._should_preserve_root_child(child):
                continue
            self._cancel_widget_callbacks(child)
        animation_id = getattr(widget, "_animation_id", None)
        if animation_id is None:
            return
        try:
            widget.after_cancel(animation_id)
        except tk.TclError:
            pass
        try:
            widget._animation_id = None
        except AttributeError:
            pass

    def _cancel_pending_ui_callbacks(self) -> None:
        for attribute in (
            "_minimize_after_id",
            "_thumbnail_drag_after_id",
            "_preview_after_id",
            "_thumbnail_resize_after_id",
            "_thumbnail_generation_after_id",
            "_preview_layout_after_id",
            "_pdf_preview_after_id",
            "_pdf_preview_render_after_id",
            "_workspace_sash_after_id",
            "_preview_vertical_sash_after_id",
            "_drop_after_id",
            "_drop_import_after_id",
            "_copy_feedback_after_id",
            "_mode_toast_after_id",
            "_mode_toast_fade_after_id",
        ):
            after_id = getattr(self, attribute, None)
            if after_id is None:
                continue
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
            setattr(self, attribute, None)
        self._hide_mode_toast()

    def _cancel_after_callback(self, attribute: str) -> None:
        after_id = getattr(self, attribute, None)
        if after_id is None:
            return
        try:
            self.root.after_cancel(after_id)
        except tk.TclError:
            pass
        setattr(self, attribute, None)

    def _size_window(
        self,
        target_width: int,
        target_height: int,
        *,
        min_width: int,
        min_height: int,
    ) -> None:
        """Fit the window to smaller laptop displays without platform assumptions."""

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        width = min(target_width, max(640, screen_width - 64))
        height = min(target_height, max(520, screen_height - 96))
        x = max(0, (screen_width - width) // 2)
        y = max(0, (screen_height - height) // 3)
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.root.minsize(min(min_width, width), min(min_height, height))

    def _set_dino_state(self, state: str) -> None:
        """Update the visual process rail without coupling it to OCR logic."""

        floating_pet = getattr(self, "_floating_pet", None)
        if floating_pet is not None:
            floating_pet.set_state(state)
        process_rail = getattr(self, "process_rail", None)
        try:
            exists = process_rail is not None and process_rail.winfo_exists()
        except tk.TclError:
            return
        if exists:
            process_rail.set_state(state)

    def _configure_dino_run(self, total: int, completed: int = 0) -> None:
        """Tell the process rail what OCR run it is animating."""

        process_rail = getattr(self, "process_rail", None)
        try:
            exists = process_rail is not None and process_rail.winfo_exists()
        except tk.TclError:
            return
        if exists:
            process_rail.configure_run(self._active_recognition_mode(), total, completed)

    def _update_dino_progress(self, completed: int, total: int) -> None:
        """Advance the process rail from existing coarse OCR progress events."""

        process_rail = getattr(self, "process_rail", None)
        try:
            exists = process_rail is not None and process_rail.winfo_exists()
        except tk.TclError:
            return
        if exists:
            process_rail.update_run_progress(completed, total)

    def _active_recognition_mode(self) -> OcrMode:
        return "document" if getattr(self, "recognition_mode", None) == "document" else "text"

    @staticmethod
    def _recognition_mode_name(mode: OcrMode | None) -> str:
        return DEEP_MODE_LABEL if mode == "document" else FAST_MODE_LABEL

    def _ensure_mode_result_storage(self) -> None:
        if not hasattr(self, "_batch_tasks_by_mode"):
            self._batch_tasks_by_mode = {"text": [], "document": []}
        else:
            self._batch_tasks_by_mode.setdefault("text", [])
            self._batch_tasks_by_mode.setdefault("document", [])
        if not hasattr(self, "_single_result_by_mode"):
            self._single_result_by_mode = {}

    def _mark_batch_tasks_mode(
        self,
        tasks: list[OCRTask],
        mode: OcrMode,
        *,
        only_missing: bool = False,
    ) -> None:
        for task in tasks:
            if only_missing and task.extra.get("recognition_mode") in {"text", "document"}:
                continue
            task.extra["recognition_mode"] = mode

    def _remember_current_batch_tasks_for_mode(self) -> None:
        self._ensure_mode_result_storage()
        mode = self._active_recognition_mode()
        self._mark_batch_tasks_mode(self.current_batch_tasks, mode, only_missing=True)
        self._batch_tasks_by_mode[mode] = self.current_batch_tasks

    def _remember_current_single_result_for_mode(self) -> None:
        self._ensure_mode_result_storage()
        mode = self._active_recognition_mode()
        if self.current_result is None:
            self._single_result_by_mode.pop(mode, None)
            return
        self._single_result_by_mode[mode] = {
            "result": self.current_result,
            "record_id": self.current_record_id,
            "region": self.current_recognition_region,
        }

    def _ensure_image_edit_states(self) -> None:
        if not hasattr(self, "image_edit_states"):
            self.image_edit_states = []
        while len(self.image_edit_states) < len(self.batch_image_infos):
            self.image_edit_states.append(ImageEditState())
        if len(self.image_edit_states) > len(self.batch_image_infos):
            del self.image_edit_states[len(self.batch_image_infos) :]

    def _current_image_edit_state(self) -> ImageEditState:
        self._ensure_image_edit_states()
        if not self.image_edit_states:
            return ImageEditState()
        index = max(0, min(getattr(self, "preview_image_index", 0), len(self.image_edit_states) - 1))
        return self.image_edit_states[index]

    def _edit_state_for_index(self, index: int) -> ImageEditState:
        self._ensure_image_edit_states()
        if 0 <= index < len(self.image_edit_states):
            return self.image_edit_states[index]
        return ImageEditState()

    def _activate_mode_result_state(self, mode: OcrMode) -> None:
        self._ensure_mode_result_storage()
        self.current_batch_tasks = self._batch_tasks_by_mode.get(mode, [])
        self._mark_batch_tasks_mode(self.current_batch_tasks, mode, only_missing=True)
        cached_result = self._single_result_by_mode.get(mode)
        result = cached_result.get("result") if cached_result is not None else None
        self.current_result = result if isinstance(result, OcrResult) else None
        self.current_record_id = (
            str(cached_result.get("record_id"))
            if cached_result is not None and cached_result.get("record_id") is not None
            else None
        )
        region = cached_result.get("region") if cached_result is not None else None
        self.current_recognition_region = region if isinstance(region, tuple) else None

    def _refresh_dino_for_active_mode(self) -> None:
        if getattr(self, "image_path", None) is None:
            self._set_dino_state("idle")
            return
        if getattr(self, "_is_recognizing", False):
            self._set_dino_state("working")
            return
        if self._active_mode_has_visible_result():
            self._configure_dino_run(1, 1)
            self._set_dino_state("done")
            return
        self._set_dino_state("ready")

    def _active_mode_has_visible_result(self) -> bool:
        if len(self.batch_image_infos) > 1:
            if not (0 <= self.preview_image_index < len(self.current_batch_tasks)):
                return False
            task = self.current_batch_tasks[self.preview_image_index]
            if not self._task_belongs_to_active_mode(task):
                return False
            return task.status == OCRTaskQueue.FINISHED and not task.extra.get("result_cleared")
        return self.current_result is not None

    def _task_belongs_to_active_mode(self, task: OCRTask) -> bool:
        task_mode = task.extra.get("recognition_mode")
        if task_mode in {"text", "document"}:
            return task_mode == self._active_recognition_mode()
        return self._active_recognition_mode() == "text"

    def _switch_recognition_mode(self, _event: tk.Event | None = None) -> None:
        """Switch the OCR mode used by the next recognition request."""

        if self._is_recognizing:
            return

        self._remember_current_batch_tasks_for_mode()
        self._remember_current_single_result_for_mode()
        previous_mode = self._active_recognition_mode()
        selected_mode: OcrMode = "text" if self.recognition_mode == "document" else "document"
        removed_documents = 0
        if previous_mode == "document" and selected_mode == "text":
            removed_documents = self._clear_document_uploads_for_mode_switch()
        self.recognition_mode = selected_mode
        self._activate_mode_result_state(selected_mode)
        mode_name = self._recognition_mode_name(selected_mode)
        self.mode_switch_var.set(mode_name)
        self._sync_mode_switch_button()
        self._sync_mode_labels()
        self.root.title(f"本地 OCR - {mode_name}")
        display_text = self._render_current_result_text()
        self._sync_result_actions(display_text)
        if removed_documents:
            self.status_var.set(f"已切换到{mode_name}；已从任务列表清空 {removed_documents} 个 PDF 文档")
        elif len(self.batch_image_infos) > 1:
            self._update_current_batch_status()
        elif display_text:
            self.status_var.set(f"已切换到{mode_name}；当前模式已有识别结果")
        else:
            self.status_var.set(f"已切换到{mode_name}；当前图片尚未用该模式识别")
        self._refresh_dino_for_active_mode()
        self._show_mode_toast("识别模式已切换", mode_name)

    def _sync_mode_switch_button(self) -> None:
        mode_button = getattr(self, "mode_switch_box", None)
        if mode_button is not None:
            mode_button.configure(text=self.mode_switch_var.get())

    def _sync_mode_labels(self) -> None:
        """根据识别模式切换导入与识别按钮文案。"""

        is_document_mode = self._active_recognition_mode() == "document"
        choose_button = getattr(self, "choose_button", None)
        if choose_button is not None:
            choose_button.configure(text="＋ 添加文档" if is_document_mode else "＋ 添加图片")
        recognize_button = getattr(self, "recognize_button", None)
        if recognize_button is not None:
            recognize_button.configure(text="▶ 识别文档" if is_document_mode else "▶ 识别整图")

    def _show_mode_toast(self, title: str, message: str) -> None:
        """Show a centered mode-change notice, then fade it out after a pause."""

        self._hide_mode_toast()
        if not self.root.winfo_exists():
            return

        window = tk.Toplevel(self.root)
        window.withdraw()
        window.wm_overrideredirect(True)
        try:
            window.attributes("-alpha", 1.0)
            window.attributes("-topmost", True)
        except tk.TclError:
            pass

        title_is_mode = title in {FAST_MODE_LABEL, DEEP_MODE_LABEL}
        title_font_size = 18 if title_is_mode else 15
        message_font_size = 10 if title_is_mode else 11
        outer = tk.Frame(window, background=INK, borderwidth=0)
        outer.pack()
        content = tk.Frame(outer, background=PANEL, padx=28, pady=18)
        content.pack(padx=2, pady=2)
        tk.Label(
            content,
            text=title,
            background=PANEL,
            foreground=INK,
            font=(self.ui_font_family, title_font_size, "bold"),
        ).pack()
        tk.Label(
            content,
            text=message,
            background=PANEL,
            foreground=MUTED,
            font=(self.ui_font_family, message_font_size, "bold"),
        ).pack(pady=(8, 0))

        self.root.update_idletasks()
        window.update_idletasks()
        width = max(1, window.winfo_reqwidth())
        height = max(1, window.winfo_reqheight())
        root_width = max(1, self.root.winfo_width())
        root_height = max(1, self.root.winfo_height())
        x = self.root.winfo_rootx() + (root_width - width) // 2
        y = self.root.winfo_rooty() + (root_height - height) // 2
        window.wm_geometry(f"+{max(0, x)}+{max(0, y)}")
        window.deiconify()
        window.lift()

        self._mode_toast_window = window
        self._mode_toast_after_id = self.root.after(5000, self._fade_mode_toast)

    def _fade_mode_toast(self, alpha: float = 1.0) -> None:
        window = self._mode_toast_window
        self._mode_toast_after_id = None
        if window is None or not window.winfo_exists():
            self._hide_mode_toast()
            return

        next_alpha = alpha - 0.08
        if next_alpha <= 0:
            self._hide_mode_toast()
            return

        try:
            window.attributes("-alpha", next_alpha)
        except tk.TclError:
            self._hide_mode_toast()
            return
        self._mode_toast_fade_after_id = self.root.after(
            34,
            lambda value=next_alpha: self._fade_mode_toast(value),
        )

    def _hide_mode_toast(self) -> None:
        for attribute in ("_mode_toast_after_id", "_mode_toast_fade_after_id"):
            after_id = getattr(self, attribute, None)
            if after_id is not None:
                try:
                    self.root.after_cancel(after_id)
                except tk.TclError:
                    pass
                setattr(self, attribute, None)
        window = getattr(self, "_mode_toast_window", None)
        if window is not None:
            try:
                if window.winfo_exists():
                    window.destroy()
            except tk.TclError:
                pass
            self._mode_toast_window = None

    def _create_resize_pane(self, master: tk.Misc, *, orient: str) -> tk.PanedWindow:
        """Create a flat native splitter for the workspace."""

        cursor = "sb_h_double_arrow" if orient == tk.HORIZONTAL else "sb_v_double_arrow"
        options = {
            "orient": orient,
            "background": PAPER,
            "borderwidth": 0,
            "relief": tk.FLAT,
            "sashwidth": 14 if orient == tk.HORIZONTAL else 12,
            "sashpad": 5,
            "opaqueresize": True,
            "showhandle": False,
            "cursor": cursor,
        }
        try:
            return tk.PanedWindow(master, sashcursor=cursor, **options)
        except tk.TclError:
            return tk.PanedWindow(master, **options)

    @staticmethod
    def _pane_contains(pane: tk.PanedWindow, child: tk.Widget) -> bool:
        return str(child) in {str(item) for item in pane.panes()}

    def _schedule_default_workspace_sash(self) -> None:
        self._cancel_after_callback("_workspace_sash_after_id")
        self._workspace_sash_after_id = self.root.after(50, self._set_default_workspace_sash)

    def _set_default_workspace_sash(self) -> None:
        self._workspace_sash_after_id = None
        pane = getattr(self, "workspace_pane", None)
        if self._workspace_sash_initialized or pane is None or not pane.winfo_exists():
            return
        if len(pane.panes()) < 2:
            return

        pane.update_idletasks()
        width = pane.winfo_width()
        if width <= 1:
            self._schedule_default_workspace_sash()
            return

        left_min = 360
        right_min = 300
        if width > left_min + right_min:
            left_width = min(max(left_min, int(width * 0.58)), width - right_min)
        else:
            left_width = max(260, int(width * 0.55))
        try:
            pane.sash_place(0, left_width, 0)
        except tk.TclError:
            return
        self._workspace_sash_initialized = True

    def _schedule_default_preview_vertical_sash(self) -> None:
        self._cancel_after_callback("_preview_vertical_sash_after_id")
        self._preview_vertical_sash_after_id = self.root.after(50, self._set_default_preview_vertical_sash)

    def _set_default_preview_vertical_sash(self) -> None:
        self._preview_vertical_sash_after_id = None
        pane = getattr(self, "preview_vertical_pane", None)
        if self._preview_vertical_sash_initialized or pane is None or not pane.winfo_exists():
            return
        if len(pane.panes()) < 2:
            return

        pane.update_idletasks()
        height = pane.winfo_height()
        if height <= 1:
            self._schedule_default_preview_vertical_sash()
            return

        top_min = 180
        bottom_min = 150
        if height > top_min + bottom_min:
            top_height = min(max(top_min, height - 172), height - bottom_min)
        else:
            top_height = max(120, int(height * 0.62))
        try:
            pane.sash_place(0, 0, top_height)
        except tk.TclError:
            return
        self._preview_vertical_sash_initialized = True

    def _set_preview_navigation_visible(self, visible: bool) -> None:
        pane = getattr(self, "preview_vertical_pane", None)
        navigation = getattr(self, "preview_navigation_frame", None)
        if pane is None or navigation is None or not pane.winfo_exists():
            return

        is_visible = self._pane_contains(pane, navigation)
        if visible and not is_visible:
            pane.add(navigation, minsize=150, sticky="nsew")
            self._preview_vertical_sash_initialized = False
            self._schedule_default_preview_vertical_sash()
        elif not visible and is_visible:
            pane.forget(navigation)
            self._preview_vertical_sash_initialized = False
            self._cancel_after_callback("_preview_vertical_sash_after_id")

    def _on_preview_controls_resize(self, _event: tk.Event) -> None:
        return

    def _on_thumbnail_resize(self, _event: tk.Event) -> None:
        if self._thumbnail_resize_after_id is not None:
            self.root.after_cancel(self._thumbnail_resize_after_id)
        self._thumbnail_resize_after_id = self.root.after(60, self._render_thumbnail_strip_after_resize)

    def _render_thumbnail_strip_after_resize(self) -> None:
        self._thumbnail_resize_after_id = None
        self._render_thumbnail_strip()

    def _on_left_workspace_resize(self, _event: tk.Event | None = None) -> None:
        if self._preview_layout_after_id is not None:
            self.root.after_cancel(self._preview_layout_after_id)
        self._preview_layout_after_id = self.root.after(40, self._sync_left_workspace_layout)

    def _sync_left_workspace_layout(self) -> None:
        self._preview_layout_after_id = None
        preview_pane = getattr(self, "preview_vertical_pane", None)
        if preview_pane is None or not preview_pane.winfo_exists():
            return

        preview_pane.update_idletasks()
        pane_width = max(1, preview_pane.winfo_width())
        for child_name in ("preview_canvas_frame", "preview_navigation_frame"):
            child = getattr(self, child_name, None)
            if child is None or not child.winfo_exists():
                continue
            if self._pane_contains(preview_pane, child):
                try:
                    preview_pane.paneconfigure(child, width=pane_width)
                except tk.TclError:
                    pass
            try:
                child.configure(width=pane_width)
            except tk.TclError:
                pass

        if hasattr(self, "thumbnail_canvas") and self.thumbnail_canvas.winfo_exists():
            self._render_thumbnail_strip()
        if hasattr(self, "preview_canvas") and self.preview_canvas.winfo_exists():
            self._on_preview_resize(None)

    def _build_ui(self) -> None:
        self._last_click_region = None
        self._workspace_sash_initialized = False
        self._preview_vertical_sash_initialized = False
        container = ttk.Frame(self.root, padding=(20, 16), style="App.TFrame")
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        header = ttk.Frame(container, padding=(4, 5), style="App.TFrame")
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(2, weight=1)
        self.back_button = ttk.Button(
            header,
            text="←",
            width=3,
            command=self._return_to_start,
            style="Flat.Pixel.TButton",
            takefocus=True,
        )
        self.back_button.grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(
            header,
            text="PIXEL VISION",
            style="TLabel",
            font=(self.ui_font_family, 14, "bold"),
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(header, text="本地 OCR 工作台", style="Muted.TLabel").grid(
            row=0, column=2, sticky="w", padx=(18, 0)
        )
        mode_switch = ttk.Frame(header, style="App.TFrame")
        mode_switch.grid(row=0, column=3, sticky="e")
        ttk.Label(mode_switch, text="识别模式", style="Muted.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        self.mode_switch_box = CutCornerButton(
            mode_switch,
            text=self.mode_switch_var.get(),
            command=self._switch_recognition_mode,
            variant="default",
            font_family=self.ui_font_family,
            outer_background=PAPER,
            min_width=112,
            min_height=38,
        )
        self.mode_switch_box.pack(side=tk.LEFT)
        _Tooltip(self.mode_switch_box, "点击切换快速识别 / 深度识别")
        tk.Frame(container, height=1, background=GRID).grid(
            row=0, column=0, sticky="sew"
        )

        toolbar = ttk.Frame(container, padding=(0, 12), style="App.TFrame")
        toolbar.grid(row=1, column=0, sticky="ew")
        toolbar.columnconfigure(1, weight=1)
        import_group = ttk.Frame(toolbar, style="App.TFrame")
        import_group.grid(row=0, column=0, sticky="w")
        toolbar_button_width = 104
        toolbar_button_height = 36
        self.choose_button = CutCornerButton(
            import_group,
            text="＋ 添加图片",
            command=self.choose_image,
            variant="default",
            font_family=self.ui_font_family,
            outer_background=PAPER,
            min_width=toolbar_button_width,
            min_height=toolbar_button_height,
        )
        self.choose_button.pack(side=tk.LEFT)
        self.choose_multi_button = self.choose_button
        self.recognize_region_button = CutCornerButton(
            import_group,
            text="识别选区",
            command=self._recognize_selected_region,
            variant="default",
            font_family=self.ui_font_family,
            outer_background=PAPER,
            min_width=toolbar_button_width,
            min_height=toolbar_button_height,
        )
        self.recognize_region_button.pack(side=tk.LEFT, padx=(6, 0))
        self.clear_region_button = CutCornerButton(
            import_group,
            text="清除选区",
            command=self._clear_selected_region,
            variant="default",
            font_family=self.ui_font_family,
            outer_background=PAPER,
            min_width=toolbar_button_width,
            min_height=toolbar_button_height,
        )
        self.clear_region_button.pack(side=tk.LEFT, padx=(6, 0))
        self.recognize_button = CutCornerButton(
            import_group,
            text="▶ 识别整图",
            command=self.start_recognition,
            variant="primary",
            font_family=self.ui_font_family,
            outer_background=PAPER,
            min_height=toolbar_button_height,
        )
        self.recognize_button.pack(side=tk.LEFT, padx=(10, 0))
        self.grayscale_var = tk.BooleanVar(value=False)
        self.binarize_var = tk.BooleanVar(value=False)
        self.denoise_var = tk.BooleanVar(value=False)

        secondary_group = ttk.Frame(toolbar, style="App.TFrame")
        secondary_group.grid(row=0, column=1, sticky="e")
        self.preprocess_button = ttk.Button(
            secondary_group,
            text="预处理",
            command=self.open_preprocess_settings,
            style="Flat.Pixel.TButton",
        )
        self.preprocess_button.pack(side=tk.LEFT)
        self.history_search_button = ttk.Button(
            secondary_group,
            text="历史查询",
            command=self.open_history_search_window,
            style="Flat.Pixel.TButton",
        )
        self.history_search_button.pack(side=tk.LEFT, padx=(6, 0))
        self.mini_game_button = ttk.Button(
            secondary_group,
            text="小恐龙窗",
            command=self.open_mini_pixel_game_window,
            style="Flat.Pixel.TButton",
        )
        self.mini_game_button.pack(side=tk.LEFT, padx=(6, 0))

        self.process_rail = PixelProcessRail(
            container,
            self.ui_font_family,
            status_var=self.status_var,
            image_var=self.image_index_var,
            saved_var=self.saved_status_var,
        )
        self.process_rail.grid(row=2, column=0, sticky="ew", pady=(0, 12))

        self.workspace_pane = self._create_resize_pane(container, orient=tk.HORIZONTAL)
        self.workspace_pane.grid(row=3, column=0, sticky="nsew")
        self.workspace_pane.bind("<B1-Motion>", self._on_left_workspace_resize, add="+")
        self.workspace_pane.bind("<ButtonRelease-1>", self._on_left_workspace_resize, add="+")

        self.preview_frame = PixelBorderFrame(self.workspace_pane, padding=12)
        preview_frame = self.preview_frame
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(2, weight=1)
        preview_frame.bind("<Configure>", self._on_left_workspace_resize, add="+")
        preview_header = ttk.Frame(preview_frame, style="Panel.TFrame")
        preview_header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        preview_header.columnconfigure(0, weight=1)
        ttk.Label(preview_header, text="图片", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(
            preview_header,
            text="拖拽框选区域 · Enter 识别 · Delete 删除",
            style="PanelMuted.TLabel",
        ).grid(row=0, column=1, sticky="e")
        tk.Frame(preview_frame, height=1, background=GRID).grid(row=1, column=0, sticky="ew", pady=(0, 10))

        self.preview_vertical_pane = self._create_resize_pane(preview_frame, orient=tk.VERTICAL)
        self.preview_vertical_pane.grid(row=2, column=0, sticky="nsew")

        self.preview_canvas_frame = PixelBorderFrame(self.preview_vertical_pane, padding=6, background=PAPER)
        preview_canvas_frame = self.preview_canvas_frame
        preview_canvas_frame.columnconfigure(0, weight=1)
        preview_canvas_frame.rowconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(
            preview_canvas_frame,
            background=PAPER,
            highlightthickness=0,
            cursor="crosshair",
            yscrollincrement=1,
        )
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_canvas.bind("<Configure>", self._on_preview_resize)
        self.preview_canvas.bind("<MouseWheel>", self._on_preview_wheel, add="+")
        self.preview_canvas.bind("<Button-4>", self._on_preview_wheel, add="+")
        self.preview_canvas.bind("<Button-5>", self._on_preview_wheel, add="+")
        self.preview_canvas.bind("<ButtonPress-2>", self._on_preview_pan_press, add="+")
        self.preview_canvas.bind("<B2-Motion>", self._on_preview_pan_drag, add="+")
        self.preview_canvas.bind("<ButtonPress-1>", self._on_region_press)
        self.preview_canvas.bind("<B1-Motion>", self._on_region_drag)
        self.preview_canvas.bind("<ButtonRelease-1>", self._on_region_release)

        # TkinterDnD 可用时，整个窗口都可以接收拖拽图片。
        self._enable_drag_drop()
        self._bind_image_paste()
        self._bind_workspace_shortcuts()

        self._result_toolbar_icons: dict[str, tuple[ImageTk.PhotoImage, ImageTk.PhotoImage, ImageTk.PhotoImage]] = {}
        for name in ("copy", "export", "clear", "view", "save", "rotate", "mirror", "mirror_vertical"):
            normal = ImageTk.PhotoImage(
                _draw_result_action_icon(name, "#454545"),
                master=self.root,
            )
            active = ImageTk.PhotoImage(
                _draw_result_action_icon(name, INK, background="#f7f6f1", border="#c8c6bd", shadow="#e3e1da"),
                master=self.root,
            )
            disabled = ImageTk.PhotoImage(
                _draw_result_action_icon(
                    name,
                    "#8d8c86",
                    background="#f2f1ec",
                    border="#dedcd6",
                    shadow="#efeee8",
                ),
                master=self.root,
            )
            self._result_toolbar_icons[name] = (normal, active, disabled)

        self.preview_navigation_frame = ttk.Frame(self.preview_vertical_pane, style="Panel.TFrame")
        self.preview_navigation_frame.columnconfigure(0, weight=1)
        self.preview_navigation_frame.rowconfigure(1, weight=1)

        self.preview_controls = ttk.Frame(self.preview_navigation_frame, style="Panel.TFrame")
        self.preview_controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.preview_controls.columnconfigure(1, weight=1)
        self.preview_controls.rowconfigure(0, weight=1)
        self.preview_prev_button = ttk.Button(
            self.preview_controls,
            text="← 上一张",
            command=self._preview_previous_image,
            state=tk.DISABLED,
            style="Quiet.Pixel.TButton",
        )
        self.preview_prev_button.grid(row=0, column=0, sticky="w")
        self.preview_edit_controls = ttk.Frame(self.preview_controls, style="Panel.TFrame")
        self.preview_edit_controls.grid(row=0, column=1, padx=8)
        self.preview_edit_controls.columnconfigure(0, weight=1)
        self.preview_edit_controls.columnconfigure(4, weight=1)
        self.preview_edit_controls.rowconfigure(0, weight=1)
        self.preview_rotate_button = ttk.Button(
            self.preview_edit_controls,
            image=(
                self._result_toolbar_icons["rotate"][0],
                "disabled",
                self._result_toolbar_icons["rotate"][2],
                "active",
                self._result_toolbar_icons["rotate"][1],
            ),
            command=self._rotate_current_image,
            style="PreviewIcon.Pixel.TButton",
            takefocus=False,
        )
        self.preview_rotate_button.grid(row=0, column=1, sticky="", padx=(0, 6))
        _Tooltip(self.preview_rotate_button, "旋转 90°")
        self.preview_mirror_button = ttk.Button(
            self.preview_edit_controls,
            image=(
                self._result_toolbar_icons["mirror"][0],
                "disabled",
                self._result_toolbar_icons["mirror"][2],
                "active",
                self._result_toolbar_icons["mirror"][1],
            ),
            command=self._mirror_current_image,
            style="PreviewIcon.Pixel.TButton",
            takefocus=False,
        )
        self.preview_mirror_button.grid(row=0, column=2, padx=(0, 6))
        _Tooltip(self.preview_mirror_button, "水平镜像")
        self.preview_mirror_vertical_button = ttk.Button(
            self.preview_edit_controls,
            image=(
                self._result_toolbar_icons["mirror_vertical"][0],
                "disabled",
                self._result_toolbar_icons["mirror_vertical"][2],
                "active",
                self._result_toolbar_icons["mirror_vertical"][1],
            ),
            command=self._mirror_vertical_current_image,
            style="PreviewIcon.Pixel.TButton",
            takefocus=False,
        )
        self.preview_mirror_vertical_button.grid(row=0, column=3)
        _Tooltip(self.preview_mirror_vertical_button, "上下镜像")
        self.preview_controls.bind("<Configure>", self._on_preview_controls_resize, add="+")
        self.preview_next_button = ttk.Button(
            self.preview_controls,
            text="下一张 →",
            command=self._preview_next_image,
            state=tk.DISABLED,
            style="Quiet.Pixel.TButton",
        )
        self.preview_next_button.grid(row=0, column=2, sticky="e")

        self.thumbnail_frame = ttk.Frame(self.preview_navigation_frame, style="Panel.TFrame")
        self.thumbnail_frame.grid(row=1, column=0, sticky="nsew")
        self.thumbnail_frame.columnconfigure(0, weight=1)
        self.thumbnail_frame.rowconfigure(0, weight=1)
        thumbnail_canvas_frame = PixelBorderFrame(self.thumbnail_frame, padding=6, background=PAPER)
        thumbnail_canvas_frame.grid(row=0, column=0, sticky="nsew")
        thumbnail_canvas_frame.columnconfigure(0, weight=1)
        thumbnail_canvas_frame.rowconfigure(0, weight=1)
        self.thumbnail_canvas = tk.Canvas(
            thumbnail_canvas_frame,
            height=92,
            background=PAPER,
            highlightthickness=0,
            cursor="hand2",
        )
        self.thumbnail_canvas.grid(row=0, column=0, sticky="nsew")
        thumbnail_scrollbar = PixelScrollbar(
            self.thumbnail_frame,
            orient=tk.HORIZONTAL,
            command=self.thumbnail_canvas.xview,
            background=PANEL,
        )
        thumbnail_scrollbar.grid(row=1, column=0, sticky="ew")
        self.thumbnail_canvas.configure(xscrollcommand=thumbnail_scrollbar.set)
        self.thumbnail_canvas.bind("<ButtonPress-1>", self._on_thumbnail_press)
        self.thumbnail_canvas.bind("<B1-Motion>", self._on_thumbnail_drag)
        self.thumbnail_canvas.bind("<ButtonRelease-1>", self._on_thumbnail_release)
        self.thumbnail_canvas.bind("<Configure>", self._on_thumbnail_resize, add="+")
        self.preview_vertical_pane.add(preview_canvas_frame, minsize=180, sticky="nsew")
        self.preview_vertical_pane.add(self.preview_navigation_frame, minsize=150, sticky="nsew")
        self.preview_controls.grid_remove()
        self.thumbnail_frame.grid_remove()
        self._set_preview_navigation_visible(False)

        result_frame = PixelBorderFrame(self.workspace_pane, padding=12)
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(2, weight=1)
        result_header = ttk.Frame(result_frame, style="Panel.TFrame")
        result_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        result_header.columnconfigure(2, weight=1)
        ttk.Label(result_header, text="识别结果", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(result_header, text="可直接编辑", style="PanelMuted.TLabel").grid(
            row=0, column=1, sticky="w", padx=(10, 0)
        )
        ttk.Label(
            result_header,
            textvariable=self.copy_feedback_var,
            anchor=tk.E,
            style="PanelMuted.TLabel",
        ).grid(row=0, column=2, sticky="e", padx=(8, 10))

        self.copy_button = ttk.Button(
            result_header,
            image=(
                self._result_toolbar_icons["copy"][0],
                "disabled",
                self._result_toolbar_icons["copy"][2],
                "active",
                self._result_toolbar_icons["copy"][1],
            ),
            command=self.copy_result_text,
            state=tk.DISABLED,
            style="ResultIcon.Pixel.TButton",
            cursor="hand2",
            takefocus=True,
        )
        self.copy_button.grid(row=0, column=3, sticky="e")
        self.export_txt_button = ttk.Button(
            result_header,
            image=(
                self._result_toolbar_icons["export"][0],
                "disabled",
                self._result_toolbar_icons["export"][2],
                "active",
                self._result_toolbar_icons["export"][1],
            ),
            command=self.export_result_txt,
            state=tk.DISABLED,
            style="ResultIcon.Pixel.TButton",
            cursor="hand2",
            takefocus=True,
        )
        self.export_txt_button.grid(row=0, column=4, sticky="e", padx=(6, 0))
        self.clear_result_button = ttk.Button(
            result_header,
            image=(
                self._result_toolbar_icons["clear"][0],
                "disabled",
                self._result_toolbar_icons["clear"][2],
                "active",
                self._result_toolbar_icons["clear"][1],
            ),
            command=self.clear_result_text,
            state=tk.DISABLED,
            style="ResultIcon.Pixel.TButton",
            cursor="hand2",
            takefocus=True,
        )
        self.clear_result_button.grid(row=0, column=5, sticky="e", padx=(6, 0))

        self.save_edit_button = ttk.Button(
            result_header,
            image=(
                self._result_toolbar_icons["save"][0],
                "disabled",
                self._result_toolbar_icons["save"][2],
                "active",
                self._result_toolbar_icons["save"][1],
            ),
            command=self.save_edited_text,
            state=tk.DISABLED,
            style="ResultIcon.Pixel.TButton",
            cursor="hand2",
            takefocus=True,
        )
        self.save_edit_button.grid(row=0, column=6, sticky="e", padx=(6, 0))

        self.view_button = ttk.Button(
            result_header,
            image=(
                self._result_toolbar_icons["view"][0],
                "disabled",
                self._result_toolbar_icons["view"][2],
                "active",
                self._result_toolbar_icons["view"][1],
            ),
            command=self._toggle_display_mode,
            style="ResultIcon.Pixel.TButton",
            cursor="hand2",
            takefocus=True,
        )
        self.view_button.grid(row=0, column=7, sticky="e", padx=(6, 0))
        self._result_toolbar_tooltips = [
            _Tooltip(self.copy_button, "复制识别结果"),
            _Tooltip(self.export_txt_button, "导出 TXT"),
            _Tooltip(self.clear_result_button, "清空识别结果"),
            _Tooltip(self.save_edit_button, "保存编辑文本"),
            _Tooltip(self.view_button, "切换结果视图"),
        ]

        tk.Frame(result_frame, height=1, background=GRID).grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10)
        )
        result_text_frame = PixelBorderFrame(result_frame, padding=6, background=PANEL)
        result_text_frame.grid(row=2, column=0, columnspan=2, sticky="nsew")
        result_text_frame.columnconfigure(0, weight=1)
        result_text_frame.rowconfigure(0, weight=1)
        self.result_text = tk.Text(
            result_text_frame,
            wrap=tk.WORD,
            font=(self.ui_font_family, 11),
            background=PANEL,
            foreground=INK,
            insertbackground=INK,
            selectbackground=INK,
            selectforeground=PANEL,
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            padx=16,
            pady=14,
            spacing1=2,
            spacing3=4,
        )
        scrollbar = PixelScrollbar(
            result_text_frame,
            orient=tk.VERTICAL,
            command=self.result_text.yview,
            background=PANEL,
        )
        self.result_text.configure(yscrollcommand=scrollbar.set)
        self.result_text.grid(row=0, column=0, sticky="nsew")
        self.result_text.bind("<FocusIn>", self._remember_result_text_focus)
        scrollbar.grid(row=0, column=1, sticky="ns")

        self.workspace_pane.add(preview_frame, minsize=360, sticky="nsew")
        self.workspace_pane.add(result_frame, minsize=300, sticky="nsew")
        self._schedule_default_workspace_sash()

        self._draw_preview_placeholder("DROP IMAGE HERE\n选择、拖拽或粘贴图片")
        self._render_thumbnail_strip()
        self._set_dino_state("idle")

    def choose_image(self) -> None:
        """选择一张或多张受支持的图片。"""

        selected = filedialog.askopenfilenames(
            title="添加文档" if self._active_recognition_mode() == "document" else "添加图片",
            filetypes=self.DOCUMENT_TYPES if self._active_recognition_mode() == "document" else self.IMAGE_TYPES,
        )
        if selected:
            try:
                self._accept_images([Path(item) for item in selected], append=True)
            except Exception as exc:
                messagebox.showerror("无法加载文档" if self._active_recognition_mode() == "document" else "无法加载图片", str(exc))
                self.status_var.set("文档加载失败" if self._active_recognition_mode() == "document" else "图片加载失败")

    def choose_multiple_images(self) -> None:
        """兼容旧入口：添加图片按钮已经支持单张或多张选择。"""

        self.choose_image()

    def _accept_image(
        self,
        image_path: Path,
        *,
        temporary: bool = False,
        append: bool = False,
    ) -> None:
        """统一接收选择、拖拽或剪贴板生成的图片。"""

        self._accept_images(
            [image_path],
            temporary_paths=[image_path] if temporary else None,
            append=append,
        )

    def _accept_images(
        self,
        image_paths: list[Path],
        temporary_paths: list[Path] | None = None,
        *,
        append: bool = False,
    ) -> None:
        """统一接收图片；拖拽时可追加到现有队列尾部。"""

        if not image_paths:
            raise ValueError("没有检测到文件。")

        validated_paths: list[Path] = []
        image_infos: list[tuple[Path, int, int]] = []
        for image_path in image_paths:
            path, upload_type, width, height = validate_upload_path(image_path)
            if upload_type == "document" and self._active_recognition_mode() != "document":
                self._switch_to_document_mode_for_upload()
            validated_paths.append(path)
            image_infos.append((path, width, height))

        is_appending = append and bool(self.batch_image_infos)
        if is_appending:
            self._forget_image_preview_state(validated_paths)
            self._ensure_image_edit_states()
            self.batch_image_paths.extend(validated_paths)
            self.batch_image_infos.extend(image_infos)
            self.image_regions.extend([None] * len(image_infos))
            self.image_edit_states.extend(ImageEditState() for _ in image_infos)
            self._refresh_preview_selector()
            self.status_var.set(
                f"已追加 {len(validated_paths)} 张图片到队尾；当前共 {len(self.batch_image_infos)} 张"
            )
        else:
            self.batch_image_paths = validated_paths
            self.batch_image_infos = image_infos
            self.image_regions = [None] * len(image_infos)
            self.image_edit_states = [ImageEditState() for _ in image_infos]
            self._clear_image_preview_state(cancel_generation=True)
            self.preview_image_index = 0
            self.current_result = None
            self.current_record_id = None
            self.current_batch_tasks = []
            self._batch_tasks_by_mode = {"text": [], "document": []}
            self._single_result_by_mode = {}
            self.current_recognition_region = None
            self.selected_region = None
            self.region_selector.clear()
            self.result_text.delete("1.0", tk.END)
            self._set_result_actions_enabled(False)
            self._set_copy_feedback("")
            self._refresh_preview_selector()
            first_path, first_width, first_height = image_infos[0]
            self._load_selected_image(first_path, first_width, first_height)
            if len(validated_paths) > 1:
                self._render_preview()
                self.status_var.set(f"已加入 {len(validated_paths)} 张图片；按 Enter 按队列顺序批量识别")
        self.saved_status_var.set("最近保存：未保存")

        temporary_set = {path.resolve() for path in temporary_paths or []}
        if is_appending:
            self._temporary_image_paths.update(temporary_set)
        else:
            for previous_temporary in self._temporary_image_paths - temporary_set:
                previous_temporary.unlink(missing_ok=True)
            self._temporary_image_paths = temporary_set
        self._refresh_dino_for_active_mode()

    def _switch_to_document_mode_for_upload(self) -> None:
        if self._active_recognition_mode() == "document":
            return
        self._remember_current_batch_tasks_for_mode()
        self._remember_current_single_result_for_mode()
        self.recognition_mode = "document"
        self._activate_mode_result_state("document")
        self.mode_switch_var.set(DEEP_MODE_LABEL)
        self._sync_mode_switch_button()
        self._sync_mode_labels()
        self.root.title(f"本地 OCR - {DEEP_MODE_LABEL}")
        if hasattr(self, "result_text"):
            display_text = self._render_current_result_text()
            self._sync_result_actions(display_text)
        self.status_var.set("已为您自动切换深度识别模式。")
        self._show_mode_toast(DEEP_MODE_LABEL, "已为您自动切换")

    def open_preprocess_settings(self) -> None:
        """打开轻量预处理设置窗口。"""

        if not hasattr(self, "preprocess_step_order"):
            self.preprocess_step_order = list(PREPROCESS_STEP_ORDER)

        window = create_independent_window("预处理设置", resizable=False)
        frame = ttk.Frame(window, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="勾选需要的预处理，并拖拽调整执行顺序", style="PanelMuted.TLabel").pack(
            anchor=tk.W, pady=(0, 12)
        )

        row_height = 50
        row_gap = 8
        canvas_width = 360
        canvas_height = row_height * len(PREPROCESS_STEP_ORDER) + row_gap * (len(PREPROCESS_STEP_ORDER) - 1) + 10
        drag_state: dict[str, object] = {
            "step": None,
            "offset_y": 0,
            "pointer_y": 0,
            "target_index": None,
        }
        display_tops = {step: float(index * (row_height + row_gap)) for index, step in enumerate(self.preprocess_step_order)}
        animation_state: dict[str, str | None] = {"after_id": None}
        canvas = tk.Canvas(
            frame,
            width=canvas_width,
            height=canvas_height,
            background=PANEL,
            highlightthickness=0,
            borderwidth=0,
        )
        canvas.pack(fill=tk.X, pady=(0, 14))

        def variable_for_step(step: str) -> tk.BooleanVar:
            return {
                "grayscale": self.grayscale_var,
                "binarize": self.binarize_var,
                "denoise": self.denoise_var,
            }[step]

        def row_top(index: int) -> int:
            return index * (row_height + row_gap)

        def index_from_y(y: float) -> int:
            return max(0, min(len(self.preprocess_step_order) - 1, int(y // (row_height + row_gap))))

        def draw_row(step: str, top: float, *, active: bool = False) -> None:
            left = 4
            right = canvas_width - 4
            bottom = top + row_height
            fill = "#fffdf7" if active else "#f7f6f1"
            outline = INK if active else GRID
            shadow = "#d8d6cf" if active else "#e6e4dd"
            canvas.create_rectangle(left + 3, top + 4, right + 3, bottom + 4, fill=shadow, outline="", tags="row")
            canvas.create_rectangle(left, top, right, bottom, fill=fill, outline=outline, width=2 if active else 1, tags="row")
            canvas.create_text(left + 22, top + row_height / 2, text="☰", fill=MUTED, font=(self.ui_font_family, 15, "bold"), tags="row")
            checked = variable_for_step(step).get()
            box_left = left + 52
            box_top = top + row_height / 2 - 8
            box_right = box_left + 16
            box_bottom = box_top + 16
            canvas.create_rectangle(box_left, box_top, box_right, box_bottom, fill=PANEL, outline=INK, width=1, tags="row")
            if checked:
                canvas.create_line(
                    box_left + 3,
                    box_top + 8,
                    box_left + 7,
                    box_top + 12,
                    box_right - 2,
                    box_top + 3,
                    fill=INK,
                    width=3,
                    smooth=False,
                    joinstyle=tk.ROUND,
                    capstyle=tk.ROUND,
                    tags="row",
                )
            canvas.create_text(
                left + 96,
                top + row_height / 2,
                text=PREPROCESS_STEP_LABELS[step],
                fill=INK,
                anchor=tk.W,
                font=(self.ui_font_family, 12, "bold"),
                tags="row",
            )

        def redraw() -> None:
            canvas.delete("row")
            dragged = drag_state.get("step")
            pointer_y = float(drag_state.get("pointer_y") or 0)
            offset_y = float(drag_state.get("offset_y") or 0)
            for step in self.preprocess_step_order:
                if step == dragged:
                    continue
                draw_row(step, display_tops.get(step, float(row_top(self.preprocess_step_order.index(step)))))
            if isinstance(dragged, str):
                top = max(0, min(canvas_height - row_height, pointer_y - offset_y))
                draw_row(dragged, top, active=True)

        def animate_to_order() -> None:
            if animation_state.get("after_id") is not None:
                window.after_cancel(str(animation_state["after_id"]))
                animation_state["after_id"] = None
            changed = False
            for index, step in enumerate(self.preprocess_step_order):
                target = float(row_top(index))
                current = display_tops.get(step, target)
                delta = target - current
                if abs(delta) > 0.7:
                    display_tops[step] = current + delta * 0.32
                    changed = True
                else:
                    display_tops[step] = target
            redraw()
            if changed:
                animation_state["after_id"] = window.after(16, animate_to_order)

        def commit_drag_order(target_index: int) -> None:
            dragged = drag_state.get("step")
            if not isinstance(dragged, str):
                return
            order = [step for step in self.preprocess_step_order if step != dragged]
            order.insert(target_index, dragged)
            if order != self.preprocess_step_order:
                self.preprocess_step_order = order
                animate_to_order()
            else:
                redraw()

        def toggle_at(y: float) -> None:
            index = index_from_y(y)
            step = self.preprocess_step_order[index]
            variable = variable_for_step(step)
            variable.set(not variable.get())
            redraw()

        def on_press(event: tk.Event) -> None:
            index = index_from_y(event.y)
            step = self.preprocess_step_order[index]
            if 38 <= event.x <= 82:
                toggle_at(event.y)
                drag_state["step"] = None
                return
            drag_state["step"] = step
            drag_state["offset_y"] = event.y - row_top(index)
            drag_state["pointer_y"] = event.y
            drag_state["target_index"] = index
            display_tops[step] = float(row_top(index))
            canvas.configure(cursor="fleur")
            redraw()

        def on_drag(event: tk.Event) -> None:
            dragged = drag_state.get("step")
            if not isinstance(dragged, str):
                return
            drag_state["pointer_y"] = event.y
            target_index = index_from_y(event.y)
            drag_state["target_index"] = target_index
            commit_drag_order(target_index)

        def on_release(_event: tk.Event) -> None:
            dragged = drag_state.get("step")
            target_index = drag_state.get("target_index")
            if isinstance(dragged, str) and isinstance(target_index, int):
                commit_drag_order(target_index)
                display_tops[dragged] = float(row_top(self.preprocess_step_order.index(dragged)))
            drag_state["step"] = None
            drag_state["target_index"] = None
            canvas.configure(cursor="")
            redraw()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        redraw()

        ttk.Button(frame, text="确定", command=window.destroy).pack(anchor=tk.E)
        self._center_child_window(window)
        window.deiconify()
        window.lift()

    def _center_child_window(self, window: tk.Toplevel) -> None:
        window.update_idletasks()
        root_x = self.root.winfo_rootx()
        root_y = self.root.winfo_rooty()
        root_width = self.root.winfo_width()
        root_height = self.root.winfo_height()
        width = window.winfo_width()
        height = window.winfo_height()
        x = root_x + max(0, (root_width - width) // 2)
        y = root_y + max(0, (root_height - height) // 2)
        window.geometry(f"+{x}+{y}")

    def open_history_search_window(self) -> None:
        open_history_search_window(self.root, self.ui_font_family, self.display_mode_var.get())

    def _bind_image_paste(self) -> None:
        self.root.bind("<Control-v>", self._paste_clipboard_image)
        self.root.bind("<Command-v>", self._paste_clipboard_image)

    def _unbind_image_paste(self) -> None:
        self.root.unbind("<Control-v>")
        self.root.unbind("<Command-v>")

    def _bind_workspace_shortcuts(self) -> None:
        """绑定工作区快捷键；macOS 的 Delete 通常对应 BackSpace。"""

        self.root.bind("<Return>", self._start_recognition_shortcut)
        self.root.bind("<KP_Enter>", self._start_recognition_shortcut)
        self.root.bind("<Delete>", self._delete_image_shortcut)
        self.root.bind("<BackSpace>", self._delete_image_shortcut)
        self.root.bind("<Up>", self._preview_scroll_up_shortcut)
        self.root.bind("<Down>", self._preview_scroll_down_shortcut)
        self.root.bind("<Button-1>", self._remember_click_region, add="+")

    def _unbind_workspace_shortcuts(self) -> None:
        self.root.unbind("<Return>")
        self.root.unbind("<KP_Enter>")
        self.root.unbind("<Delete>")
        self.root.unbind("<BackSpace>")
        self.root.unbind("<Up>")
        self.root.unbind("<Down>")
        self.root.unbind("<Button-1>")
        self._last_click_region = None

    def _start_recognition_shortcut(
        self, event: tk.Event | None = None
    ) -> str | None:
        """按 Enter 直接使用当前模式识别已载入的图片。"""

        if self._is_editing_result_text(event):
            return None
        if self.image_path is not None and not self._is_recognizing:
            self.start_recognition()
        return "break"

    def _delete_image_shortcut(self, event: tk.Event | None = None) -> str | None:
        """按 Delete 删除当前图片和与之关联的识别结果。"""

        if self._is_editing_result_text(event):
            return None
        if self.image_path is None:
            return "break"
        self._delete_image_at(self.preview_image_index)
        return "break"

    def _preview_scroll_up_shortcut(self, event: tk.Event | None = None) -> str | None:
        if self._is_editing_result_text(event):
            return None
        return self._scroll_preview_units(-9)

    def _preview_scroll_down_shortcut(self, event: tk.Event | None = None) -> str | None:
        if self._is_editing_result_text(event):
            return None
        return self._scroll_preview_units(9)

    def _scroll_preview_units(self, units: int) -> str | None:
        if not getattr(self, "preview_pdf_pages", []):
            return None
        self._scroll_preview_pixels(units * 96)
        self._schedule_visible_pdf_pages_render()
        return "break"

    def _is_editing_result_text(self, event: tk.Event | None) -> bool:
        """结果文本框获得焦点时，保留其原生编辑按键行为。"""

        if self._last_click_region == "image":
            return False
        if self._last_click_region == "result_text":
            return True
        if event is not None and event.widget is self.result_text:
            return True
        return self.root.focus_get() is self.result_text

    def _remember_click_region(self, event: tk.Event) -> None:
        """记录最近一次点击区域，用于区分 Delete 应删除图片还是文字。"""

        if self._is_pointer_inside_widget(event, self.result_text):
            self._last_click_region = "result_text"
        elif self._is_pointer_inside_widget(event, self.preview_canvas):
            self._last_click_region = "image"
        else:
            self._last_click_region = None

    def _remember_result_text_focus(self, _event: tk.Event) -> None:
        self._last_click_region = "result_text"

    def _is_pointer_inside_widget(self, event: tk.Event, widget: tk.Widget) -> bool:
        x = widget.winfo_rootx()
        y = widget.winfo_rooty()
        width = widget.winfo_width()
        height = widget.winfo_height()
        return x <= event.x_root < x + width and y <= event.y_root < y + height

    # ------------------------------------------------------------------
    # 拖拽支持（TkinterDnD）
    # ------------------------------------------------------------------

    def _enable_drag_drop(self) -> None:
        """在根窗口上启用文件拖拽；相比在子 Frame 上注册，根窗口在
        Windows 上拥有可靠的本地窗口句柄，能保证 OLE 拖放正常工作。"""

        if DND_FILES is None or not hasattr(self.root, "drop_target_register"):
            return
        if getattr(self, "_root_drop_enabled", False):
            self._floating_pet.set_drag_drop_enabled(True)
            return

        # 确保窗口已完全创建（Windows 上这一步很重要）。
        self.root.update_idletasks()

        try:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<DropEnter>>", self._accept_image_drop)
            self.root.dnd_bind("<<DropPosition>>", self._accept_image_drop)
            self.root.dnd_bind("<<Drop>>", self._on_image_drop)
            self._floating_pet.set_drag_drop_enabled(True)
            self._root_drop_enabled = True
        except tk.TclError as exc:
            print(f"[WARNING] 文件拖拽不可用: {exc}")

    def _disable_drag_drop(self) -> None:
        """移除根窗口上的文件拖拽支持，避免返回开始页后误触发。"""

        floating_pet = getattr(self, "_floating_pet", None)
        if floating_pet is not None:
            floating_pet.set_drag_drop_enabled(False)

        if DND_FILES is None or not hasattr(self.root, "drop_target_register"):
            return
        if not getattr(self, "_root_drop_enabled", False):
            return

        try:
            self.root.dnd_bind("<<DropEnter>>", "")
            self.root.dnd_bind("<<DropPosition>>", "")
            self.root.dnd_bind("<<Drop>>", "")
            self.root.drop_target_unregister()
        except tk.TclError:
            pass
        self._root_drop_enabled = False

    def _paste_clipboard_image(self, _event: tk.Event | None = None) -> str:
        """从系统剪贴板粘贴图片或 Windows 图片文件。"""

        try:
            if self._is_recognizing:
                self.status_var.set("正在识别，请完成后再追加图片")
                return "break"
            previous_count = len(self.batch_image_infos)
            clipboard_content = ImageGrab.grabclipboard()
            if isinstance(clipboard_content, Image.Image):
                path = Path(self._temporary_directory.name) / f"clipboard_{uuid4().hex}.png"
                image = ImageOps.exif_transpose(clipboard_content)
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGB")
                image.save(path, format="PNG")
                try:
                    self._accept_image(path, temporary=True, append=True)
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
                self.status_var.set(
                    f"已将 1 张图片粘贴到队尾；当前共 {previous_count + 1} 张"
                )
                return "break"

            if isinstance(clipboard_content, list):
                paths = [
                    Path(candidate)
                    for candidate in clipboard_content
                    if Path(candidate).suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".pdf"}
                ]
                if paths:
                    self._accept_images(paths, append=True)
                    self.status_var.set(
                        f"已将 {len(paths)} 张图片粘贴到队尾；当前共 {previous_count + len(paths)} 张"
                    )
                    return "break"

            messagebox.showinfo("无法粘贴", "剪贴板中没有可用的图片。")
        except Exception as exc:
            messagebox.showerror("无法粘贴图片", str(exc))
            self.status_var.set("剪贴板图片加载失败")
        return "break"

    def _accept_image_drop(self, _event: tk.Event) -> str:
        return COPY

    def _on_image_drop(self, event: tk.Event) -> str:
        """接收从文件管理器拖入的一张或多张图片。"""

        try:
            if self._is_recognizing:
                self.status_var.set("正在识别，请完成后再追加图片")
                return COPY
            paths = self._paths_from_drop_data(event.data)
            if not paths:
                raise ValueError("没有检测到拖入的文件。")
            if any(detect_upload_type(path) == "document" for path in paths):
                self._switch_to_document_mode_for_upload()
            from_floating_pet = bool(getattr(event, "_from_floating_pet", False))
            if from_floating_pet:
                self._remember_floating_pet_drop_paths(paths)
            elif self._is_recent_floating_pet_root_drop(paths):
                self._withdraw_root_for_pet_drop()
                return COPY
            keep_root_hidden = from_floating_pet or self._should_keep_root_hidden_for_pet_drop()
            if keep_root_hidden:
                self._withdraw_root_for_pet_drop()
            if self.recognition_mode is None:
                self._show_drop_mode_prompt(paths, keep_root_hidden=keep_root_hidden)
                return COPY
            self.status_var.set(f"正在导入 {len(paths)} 张图片……")
            if self._drop_after_id is not None:
                self.root.after_cancel(self._drop_after_id)
            self._drop_keep_root_hidden = getattr(self, "_drop_keep_root_hidden", False) or keep_root_hidden
            self._drop_after_id = self.root.after(
                80,
                lambda paths=paths: self._accept_dropped_images(paths),
            )
        except Exception as exc:
            messagebox.showerror("无法导入图片", str(exc))
            self.status_var.set("拖拽图片加载失败")
        return COPY

    def _accept_dropped_images(self, paths: list[Path]) -> None:
        """Import after the drop callback returns so temporary files are ready."""

        self._drop_after_id = None
        try:
            keep_root_hidden = getattr(self, "_drop_keep_root_hidden", False)
            if self._is_recognizing:
                self.status_var.set("正在识别，请完成后再追加图片")
                self._drop_keep_root_hidden = False
                return
            if keep_root_hidden:
                self._withdraw_root_for_pet_drop()
            self._import_dropped_images_then_start(paths, keep_root_hidden=keep_root_hidden)
        except Exception as exc:
            messagebox.showerror("无法导入图片", str(exc))
            self.status_var.set("拖拽图片加载失败")

    def _import_dropped_images_then_start(self, paths: list[Path], *, keep_root_hidden: bool) -> None:
        if not paths:
            raise ValueError("没有检测到图片。")
        if getattr(self, "_drop_import_after_id", None) is not None:
            try:
                self.root.after_cancel(self._drop_import_after_id)
            except (AttributeError, tk.TclError):
                pass
            self._drop_import_after_id = None
        previous_count = len(getattr(self, "batch_image_infos", []))
        chunk_size = max(1, self.DROP_IMPORT_CHUNK_SIZE)
        total = len(paths)
        imported = 0

        def set_status(message: str) -> None:
            status_var = getattr(self, "status_var", None)
            if status_var is not None:
                status_var.set(message)

        def finish_import() -> None:
            self._drop_import_after_id = None
            batch_image_infos = getattr(self, "batch_image_infos", [])
            added_count = len(batch_image_infos) - previous_count
            has_document = any(detect_upload_type(path) == "document" for path in paths)
            upload_name = "文档" if has_document else "图片"
            set_status(
                f"已将 {added_count} 个{upload_name}追加到队尾；当前共 {len(batch_image_infos)} 个文件"
            )
            self._drop_keep_root_hidden = False
            if keep_root_hidden:
                self.restore_from_pet()

        def fail_import(exc: Exception) -> None:
            self._drop_import_after_id = None
            self._drop_keep_root_hidden = False
            self._floating_pet.reset_mode_choice()
            messagebox.showerror("无法导入图片", str(exc))
            set_status("拖拽图片加载失败")

        def import_next_chunk() -> None:
            nonlocal imported
            self._drop_import_after_id = None
            if self._is_recognizing:
                set_status("正在识别，请完成后再追加图片")
                self._drop_keep_root_hidden = False
                self._floating_pet.reset_mode_choice()
                return
            if keep_root_hidden:
                self._withdraw_root_for_pet_drop()
            chunk = paths[imported : imported + chunk_size]
            if not chunk:
                finish_import()
                return
            try:
                self._accept_images(chunk, append=True)
            except Exception as exc:
                fail_import(exc)
                return
            imported += len(chunk)
            if imported < total:
                set_status(f"正在导入 {imported}/{total} 张图片……")
                self._schedule_drop_import_callback(10, import_next_chunk)
                return
            self._schedule_drop_import_callback(30, finish_import)

        import_next_chunk()

    def _schedule_drop_import_callback(self, delay_ms: int, callback: Callable[[], None]) -> None:
        root = getattr(self, "root", None)
        if root is None or not hasattr(root, "after"):
            callback()
            return
        try:
            self._drop_import_after_id = root.after(delay_ms, callback)
        except tk.TclError:
            self._drop_import_after_id = None
            callback()

    def _paths_from_drop_data(self, data: object) -> list[Path]:
        items = self.root.tk.splitlist(str(data or ""))
        return [self._path_from_drop_item(item) for item in items if str(item).strip()]

    @staticmethod
    def _path_from_drop_item(item: str) -> Path:
        text = item.strip()
        parsed = urlparse(text)
        if parsed.scheme == "file":
            path_text = unquote(parsed.path)
            if parsed.netloc and parsed.netloc not in {"", "localhost"}:
                path_text = f"//{parsed.netloc}{path_text}"
            elif (
                len(path_text) >= 3
                and path_text[0] == "/"
                and path_text[2] == ":"
                and path_text[1].isalpha()
            ):
                path_text = path_text[1:]
            return Path(path_text)
        return Path(text).expanduser()

    def _load_selected_image(self, image_path: Path, width: int | None = None, height: int | None = None) -> None:
        if width is None or height is None:
            path, _upload_type, width, height = validate_upload_path(image_path)
        else:
            path = image_path
        self.image_path = path
        self._update_preview_path_label(path, width, height)

        cached_preview = self._preview_source_cache.get(path)
        edit_state = self._current_image_edit_state()
        is_document = detect_upload_type(path) == "document"
        self.preview_pdf_pages = []
        self.preview_pdf_photos = []
        self.preview_pdf_page_positions = []
        if is_document:
            pages = render_pdf_pages(path, max_size=self.PREVIEW_SOURCE_MAX_SIZE)
            if not pages:
                raise ValueError("PDF 文档没有可预览页面。")
            self.preview_pdf_pages = [page.copy() for page in pages]
            self.preview_source = self.preview_pdf_pages[0].copy()
            self.preview_original_size = self.preview_source.size
            self._preview_source_cache[path] = self.preview_source.copy()
            self._preview_original_size_cache[path] = self.preview_original_size
        elif len(self.batch_image_infos) > 1 and cached_preview is not None:
            preview = self._apply_image_edit_transform(cached_preview.copy(), edit_state)
            self.preview_source = preview
            original_size = self._preview_original_size_cache.get(path, (width, height))
            self.preview_original_size = self._image_size_for_edit_state(original_size, edit_state)
        else:
            preview, original_size = self._load_preview_source(path)
            if len(self.batch_image_infos) > 1:
                self._preview_source_cache[path] = preview.copy()
                self._preview_original_size_cache[path] = original_size
            edited_preview = self._apply_image_edit_transform(preview, edit_state)
            self.preview_original_size = self._image_size_for_edit_state(original_size, edit_state)
            self.preview_source = edited_preview.copy()

        self._render_preview()
        if is_document:
            self.status_var.set(f"文档已选择：共 {len(self.preview_pdf_pages)} 页；可滚轮或上下键滚动预览，按 Enter 识别文档")
        else:
            self.status_var.set("图片已选择；按 Enter 识别整图，按 Delete 删除")
        self._update_image_index_status()

    def _load_preview_source(self, path: Path) -> tuple[Image.Image, tuple[int, int]]:
        """Load a memory-bounded preview image while preserving true image size."""

        if detect_upload_type(path) == "document":
            pages = render_pdf_pages(path, max_size=self.PREVIEW_SOURCE_MAX_SIZE)
            if not pages:
                raise ValueError("PDF 文档没有可预览页面。")
            return pages[0].copy(), pages[0].size

        with Image.open(path) as image:
            original_size = self._transposed_original_size(image)
            image.draft("RGB", self.PREVIEW_SOURCE_MAX_SIZE)
            preview = ImageOps.exif_transpose(image)
            if preview.mode not in {"RGB", "RGBA"}:
                preview = preview.convert("RGB")
            if (
                preview.size[0] > self.PREVIEW_SOURCE_MAX_SIZE[0]
                or preview.size[1] > self.PREVIEW_SOURCE_MAX_SIZE[1]
            ):
                preview.thumbnail(self.PREVIEW_SOURCE_MAX_SIZE, Image.Resampling.LANCZOS)
            return preview.copy(), original_size

    @staticmethod
    def _transposed_original_size(image: Image.Image) -> tuple[int, int]:
        width, height = image.size
        try:
            orientation = image.getexif().get(274)
        except (AttributeError, OSError, ValueError):
            orientation = None
        return (height, width) if orientation in {5, 6, 7, 8} else (width, height)

    def _clear_image_preview_state(self, *, cancel_generation: bool = False) -> None:
        if cancel_generation:
            self._cancel_after_callback("_thumbnail_generation_after_id")
        self._thumbnail_photo_cache.clear()
        self._thumbnail_failed_paths.clear()
        self._preview_source_cache.clear()
        self._preview_original_size_cache.clear()

    def _forget_image_preview_state(self, paths: list[Path] | tuple[Path, ...]) -> None:
        for path in paths:
            if hasattr(self, "_thumbnail_photo_cache"):
                self._thumbnail_photo_cache.pop(path, None)
            if hasattr(self, "_thumbnail_failed_paths"):
                self._thumbnail_failed_paths.discard(path)
            if hasattr(self, "_preview_source_cache"):
                self._preview_source_cache.pop(path, None)
            if hasattr(self, "_preview_original_size_cache"):
                self._preview_original_size_cache.pop(path, None)

    @staticmethod
    def _apply_image_edit_transform(image: Image.Image, state: ImageEditState) -> Image.Image:
        edited = image
        if state.mirrored:
            edited = ImageOps.mirror(edited)
        if state.vertical_mirrored:
            edited = ImageOps.flip(edited)
        rotation_quarters = state.rotation_quarters % 4
        if rotation_quarters:
            edited = edited.rotate(-90 * rotation_quarters, expand=True)
        return edited.copy()

    @staticmethod
    def _image_size_for_edit_state(
        image_size: tuple[int, int],
        state: ImageEditState,
    ) -> tuple[int, int]:
        width, height = image_size
        return (height, width) if state.rotation_quarters % 2 else (width, height)

    @staticmethod
    def _transform_region_for_image_edit(
        region: tuple[int, int, int, int] | None,
        image_size: tuple[int, int],
        *,
        rotate: bool = False,
        mirror: bool = False,
        mirror_vertical: bool = False,
    ) -> tuple[int, int, int, int] | None:
        """Keep a selected region attached to the same visual image area after edits."""

        if region is None:
            return None
        width, height = image_size
        if width <= 0 or height <= 0:
            return None

        left, top, right, bottom = region
        points = [
            (float(left), float(top)),
            (float(right), float(top)),
            (float(left), float(bottom)),
            (float(right), float(bottom)),
        ]

        if mirror:
            points = [(width - x, y) for x, y in points]
        if mirror_vertical:
            points = [(x, height - y) for x, y in points]
        if rotate:
            points = [(height - y, x) for x, y in points]
            width, height = height, width

        xs = [x for x, _y in points]
        ys = [y for _x, y in points]
        transformed = (
            max(0, min(int(round(min(xs))), width)),
            max(0, min(int(round(min(ys))), height)),
            max(0, min(int(round(max(xs))), width)),
            max(0, min(int(round(max(ys))), height)),
        )
        return transformed if transformed[2] > transformed[0] and transformed[3] > transformed[1] else None

    def _edit_state_for_path(self, path: Path) -> ImageEditState:
        self._ensure_image_edit_states()
        for index, known_path in enumerate(getattr(self, "batch_image_paths", [])):
            if known_path == path:
                return self._edit_state_for_index(index)
        return ImageEditState()

    def _refresh_preview_selector(self) -> None:
        """刷新缩略图导航和切换、排序按钮。"""

        values = [
            self._preview_choice_label(index, path)
            for index, (path, _width, _height) in enumerate(self.batch_image_infos)
        ]
        if hasattr(self, "preview_controls") and hasattr(self, "thumbnail_frame"):
            if values:
                self._set_preview_navigation_visible(True)
                self.preview_controls.grid()
                self.thumbnail_frame.grid()
            else:
                self.preview_controls.grid_remove()
                self.thumbnail_frame.grid_remove()
                self._set_preview_navigation_visible(False)
        if hasattr(self, "preview_prev_button"):
            self.preview_prev_button.configure(
                state=tk.NORMAL if self.preview_image_index > 0 else tk.DISABLED
            )
            self.preview_next_button.configure(
                state=tk.NORMAL if self.preview_image_index < len(values) - 1 else tk.DISABLED
            )
        self.preview_choice_var.set(values[self.preview_image_index] if values else "")
        self._render_thumbnail_strip()
        self._update_image_index_status()

    def _preview_choice_label(self, index: int, path: Path) -> str:
        """生成下拉框中显示的预览项文本。"""

        return f"{index + 1}/{len(self.batch_image_infos)} - {path.name}"

    def _update_image_index_status(self) -> None:
        total = len(self.batch_image_infos)
        if total == 0:
            self.image_index_var.set("当前图片：0 / 0")
            return
        self.image_index_var.set(f"当前图片：{self.preview_image_index + 1} / {total}")

    def _update_preview_path_label(self, path: Path, width: int, height: int) -> None:
        """保留兼容入口；界面不再显示路径和分辨率信息。"""

        return

    def _show_preview_image(self, index: int) -> None:
        """切换当前预览图，不改变批量 OCR 队列顺序。"""

        if not self.batch_image_infos:
            return
        self.preview_image_index = max(0, min(index, len(self.batch_image_infos) - 1))
        regions = getattr(self, "image_regions", [])
        self.selected_region = (
            regions[self.preview_image_index]
            if self.preview_image_index < len(regions)
            else None
        )
        if hasattr(self, "region_selector"):
            self.region_selector.clear()
        path, width, height = self.batch_image_infos[self.preview_image_index]
        self._load_selected_image(path, width, height)
        self._refresh_preview_selector()
        display_text = self._render_current_result_text()
        self._sync_result_actions(display_text)
        if len(self.batch_image_infos) > 1:
            self._update_current_batch_status()
        self._refresh_dino_for_active_mode()

    def _preview_previous_image(self) -> None:
        """预览批量队列中的上一张图片。"""

        self._show_preview_image(self.preview_image_index - 1)

    def _preview_next_image(self) -> None:
        """预览批量队列中的下一张图片。"""

        self._show_preview_image(self.preview_image_index + 1)

    def _rotate_current_image(self) -> None:
        self._edit_current_image(rotate=True)

    def _mirror_current_image(self) -> None:
        self._edit_current_image(mirror=True)

    def _mirror_vertical_current_image(self) -> None:
        self._edit_current_image(mirror_vertical=True)

    def _edit_current_image(self, *, rotate: bool = False, mirror: bool = False, mirror_vertical: bool = False) -> None:
        if self.image_path is None or not self.batch_image_infos:
            self.status_var.set("请先添加图片")
            return
        if self._is_recognizing:
            self.status_var.set("正在识别，暂时不能编辑图片")
            return

        self._ensure_image_edit_states()
        index = self.preview_image_index
        if not (0 <= index < len(self.image_edit_states)):
            return
        state = self.image_edit_states[index]
        previous_size = self.preview_original_size or (
            self.preview_source.size if self.preview_source is not None else self.batch_image_infos[index][1:]
        )
        previous_region = self.image_regions[index] if index < len(self.image_regions) else self.selected_region
        if rotate:
            state.rotation_quarters = (state.rotation_quarters + 1) % 4
        if mirror:
            state.mirrored = not state.mirrored
        if mirror_vertical:
            state.vertical_mirrored = not state.vertical_mirrored

        updated_region = self._transform_region_for_image_edit(
            previous_region,
            previous_size,
            rotate=rotate,
            mirror=mirror,
            mirror_vertical=mirror_vertical,
        )

        path = self.batch_image_infos[index][0]
        self._thumbnail_photo_cache.pop(path, None)
        self._thumbnail_failed_paths.discard(path)
        self.image_regions[index] = updated_region
        self.selected_region = updated_region
        self.region_selector.clear()
        self._invalidate_result_slot_for_image_edit(index)
        self.current_recognition_region = updated_region
        self._load_selected_image(path, *self.batch_image_infos[index][1:])
        self._refresh_preview_selector()
        self.status_var.set("图片已编辑，选区已同步变换，旧识别结果已清除；请重新识别")
        self.saved_status_var.set("最近保存：未保存")
        self._refresh_dino_for_active_mode()

    def _on_preview_choice_change(self, _event: tk.Event) -> None:
        """从下拉框切换当前预览图片。"""

        selected = self.preview_choice_var.get()
        for index, (path, _width, _height) in enumerate(self.batch_image_infos):
            if selected == self._preview_choice_label(index, path):
                self._show_preview_image(index)
                break

    def _render_thumbnail_strip(self) -> None:
        """绘制横向缩略图队列；只使用缓存或占位，不同步解码图片。"""

        if not hasattr(self, "thumbnail_canvas"):
            return

        canvas = self.thumbnail_canvas
        canvas.delete("all")
        self.thumbnail_photos = []
        self._thumbnail_card_bounds = []
        card_width, card_height, gap = 98, 76, 10
        viewport_height = max(canvas.winfo_height(), 92)
        card_y = max(9, (viewport_height - card_height) // 2)
        failed_paths = getattr(self, "_thumbnail_failed_paths", set())
        needs_thumbnail_generation = False

        if not self.batch_image_infos:
            self._cancel_after_callback("_thumbnail_generation_after_id")
            canvas.create_text(
                12,
                viewport_height // 2,
                text="导入多张图片后，这里会显示可删除、可排序的缩略图",
                anchor=tk.W,
                fill=MUTED,
                font=(self.ui_font_family, 10),
            )
            canvas.configure(scrollregion=(0, 0, 520, viewport_height))
            return

        for index, (path, _width, _height) in enumerate(self.batch_image_infos):
            x1 = 10 + index * (card_width + gap)
            y1 = card_y
            x2 = x1 + card_width
            y2 = y1 + card_height
            self._thumbnail_card_bounds.append((x1, y1, x2, y2))
            selected = index == self.preview_image_index
            draw_pixel_box(
                canvas,
                x1,
                y1,
                x2,
                y2,
                fill="#e7e5de" if selected else PANEL,
                line_color=INK if selected else GRID,
                accent_color=INK if selected else MUTED,
                width=3 if selected else 2,
                tag=f"thumbnail-card-{index}",
                pixel=4,
                show_corners=False,
            )

            photo = self._thumbnail_photo_cache.get(path)
            if photo is not None:
                self.thumbnail_photos.append(photo)
                canvas.create_image(x1 + card_width // 2, y1 + 40, image=photo)
            else:
                failed = path in failed_paths
                if not failed:
                    needs_thumbnail_generation = True
                canvas.create_text(
                    x1 + card_width // 2,
                    y1 + 40,
                    text="预览失败" if failed else "加载中",
                    fill=MUTED,
                )

            canvas.create_text(
                x2 - 13,
                y1 + 13,
                text="×",
                fill=INK,
                font=(self.ui_font_family, 12, "bold"),
            )

        content_width = 20 + len(self.batch_image_infos) * (card_width + gap)
        canvas.configure(
            scrollregion=(
                0,
                0,
                max(content_width, canvas.winfo_width()),
                max(viewport_height, card_y + card_height + 10),
            )
        )
        self._scroll_selected_thumbnail_into_view()
        if needs_thumbnail_generation:
            self._schedule_thumbnail_generation()

    def _schedule_thumbnail_generation(self) -> None:
        if getattr(self, "_thumbnail_generation_after_id", None) is not None:
            return
        if not hasattr(self, "root"):
            return
        self._thumbnail_generation_after_id = self.root.after(30, self._generate_next_thumbnail)

    def _generate_next_thumbnail(self) -> None:
        self._thumbnail_generation_after_id = None
        if not hasattr(self, "thumbnail_canvas"):
            return
        if hasattr(self.thumbnail_canvas, "winfo_exists") and not self.thumbnail_canvas.winfo_exists():
            return

        failed_paths = getattr(self, "_thumbnail_failed_paths", set())
        target_path = next(
            (
                path
                for path, _width, _height in self.batch_image_infos
                if path not in self._thumbnail_photo_cache and path not in failed_paths
            ),
            None,
        )
        if target_path is None:
            return

        try:
            self._thumbnail_photo_cache[target_path] = self._build_thumbnail_photo(target_path)
        except (OSError, ValueError):
            failed_paths.add(target_path)

        if hasattr(self, "thumbnail_canvas"):
            if hasattr(self.thumbnail_canvas, "winfo_exists") and not self.thumbnail_canvas.winfo_exists():
                return
            self._render_thumbnail_strip()

    def _build_thumbnail_photo(self, path: Path) -> ImageTk.PhotoImage:
        source = self._preview_source_cache.get(path)
        if source is None and path == self.image_path and self.preview_source is not None:
            source = self.preview_source

        if source is None:
            source, original_size = self._load_preview_source(path)
            self._preview_source_cache[path] = source.copy()
            self._preview_original_size_cache[path] = original_size

        if detect_upload_type(path) == "document":
            thumbnail = source.copy()
        else:
            thumbnail = self._apply_image_edit_transform(source.copy(), self._edit_state_for_path(path))
        thumbnail.thumbnail((78, 64), Image.Resampling.LANCZOS)
        return ImageTk.PhotoImage(thumbnail.copy())

    def _scroll_selected_thumbnail_into_view(self) -> None:
        if not self._thumbnail_card_bounds or not hasattr(self, "thumbnail_canvas"):
            return
        canvas = self.thumbnail_canvas
        canvas.update_idletasks()
        left, _top, right, _bottom = self._thumbnail_card_bounds[self.preview_image_index]
        visible_left = canvas.canvasx(0)
        visible_right = visible_left + canvas.winfo_width()
        scrollregion = canvas.cget("scrollregion").split()
        content_width = float(scrollregion[2]) if len(scrollregion) == 4 else float(right)
        if content_width <= canvas.winfo_width():
            return
        if left < visible_left:
            canvas.xview_moveto(max(0.0, left / content_width))
        elif right > visible_right:
            canvas.xview_moveto(min(1.0, (right - canvas.winfo_width()) / content_width))

    def _thumbnail_index_at(self, canvas_x: float, canvas_y: float) -> int | None:
        for index, (x1, y1, x2, y2) in enumerate(self._thumbnail_card_bounds):
            if x1 <= canvas_x <= x2 and y1 <= canvas_y <= y2:
                return index
        return None

    def _on_thumbnail_press(self, event: tk.Event) -> str:
        canvas_x = self.thumbnail_canvas.canvasx(event.x)
        canvas_y = self.thumbnail_canvas.canvasy(event.y)
        index = self._thumbnail_index_at(canvas_x, canvas_y)
        if index is None:
            return "break"

        x1, y1, x2, _y2 = self._thumbnail_card_bounds[index]
        if x2 - 27 <= canvas_x <= x2 and y1 <= canvas_y <= y1 + 27:
            self._delete_image_at(index)
            return "break"

        self._show_preview_image(index)
        self._thumbnail_drag_index = index
        self._thumbnail_drag_active = False
        if not self._is_recognizing:
            self._thumbnail_drag_after_id = self.root.after(
                180, lambda: self._activate_thumbnail_drag(index)
            )
        return "break"

    def _activate_thumbnail_drag(self, expected_index: int) -> None:
        self._thumbnail_drag_after_id = None
        if self._thumbnail_drag_index != expected_index or self._is_recognizing:
            return
        self._thumbnail_drag_active = True
        self.thumbnail_canvas.configure(cursor="fleur")
        self.status_var.set("拖动缩略图可调整识别和导出顺序")

    def _on_thumbnail_drag(self, event: tk.Event) -> str:
        if not self._thumbnail_drag_active or self._thumbnail_drag_index is None:
            return "break"
        canvas_x = self.thumbnail_canvas.canvasx(event.x)
        canvas_y = self.thumbnail_canvas.canvasy(event.y)
        target = self._thumbnail_index_at(canvas_x, canvas_y)
        if target is not None and target != self._thumbnail_drag_index:
            source = self._thumbnail_drag_index
            self._move_image(source, target)
            self._thumbnail_drag_index = target
        return "break"

    def _on_thumbnail_release(self, _event: tk.Event) -> str:
        if self._thumbnail_drag_after_id is not None:
            self.root.after_cancel(self._thumbnail_drag_after_id)
            self._thumbnail_drag_after_id = None
        moved = self._thumbnail_drag_active
        self._thumbnail_drag_index = None
        self._thumbnail_drag_active = False
        if hasattr(self, "thumbnail_canvas"):
            self.thumbnail_canvas.configure(cursor="hand2")
        if moved:
            self.status_var.set("图片顺序已更新；将按缩略图从左到右识别和导出")
        return "break"

    @staticmethod
    def _selected_index_after_move(selected: int, source: int, target: int) -> int:
        if selected == source:
            return target
        if source < selected <= target:
            return selected - 1
        if target <= selected < source:
            return selected + 1
        return selected

    def _known_batch_task_lists(self) -> list[list[OCRTask]]:
        self._ensure_mode_result_storage()
        lists: dict[int, list[OCRTask]] = {id(self.current_batch_tasks): self.current_batch_tasks}
        for tasks in self._batch_tasks_by_mode.values():
            lists[id(tasks)] = tasks
        return list(lists.values())

    def _move_batch_result_slot_for_all_modes(self, source: int, target: int) -> None:
        self._remember_current_batch_tasks_for_mode()
        for tasks in self._known_batch_task_lists():
            if len(tasks) == len(self.batch_image_infos) and 0 <= source < len(tasks) and 0 <= target < len(tasks):
                tasks.insert(target, tasks.pop(source))
        self.current_batch_tasks = self._batch_tasks_by_mode.get(
            self._active_recognition_mode(),
            self.current_batch_tasks,
        )

    def _delete_batch_result_slot_for_all_modes(self, index: int) -> None:
        self._remember_current_batch_tasks_for_mode()
        for tasks in self._known_batch_task_lists():
            if 0 <= index < len(tasks):
                del tasks[index]
        self.current_batch_tasks = self._batch_tasks_by_mode.get(
            self._active_recognition_mode(),
            self.current_batch_tasks,
        )

    def _clear_document_uploads_for_mode_switch(self) -> int:
        """Remove queued PDF documents when leaving deep recognition mode."""

        document_indices = [
            index
            for index, (path, _width, _height) in enumerate(self.batch_image_infos)
            if detect_upload_type(path) == "document"
        ]
        for index in reversed(document_indices):
            self._delete_image_at(index)
        return len(document_indices)

    def _move_image(self, source: int, target: int) -> None:
        """同步调整界面队列、实际 OCR 队列和已有结果顺序。"""

        total = len(self.batch_image_infos)
        if self._is_recognizing:
            self.status_var.set("正在识别，暂时不能调整图片顺序")
            return
        if not (0 <= source < total and 0 <= target < total) or source == target:
            return

        selected = self.preview_image_index
        self.batch_image_infos.insert(target, self.batch_image_infos.pop(source))
        self.batch_image_paths.insert(target, self.batch_image_paths.pop(source))
        self.image_regions.insert(target, self.image_regions.pop(source))
        self._ensure_image_edit_states()
        self.image_edit_states.insert(target, self.image_edit_states.pop(source))
        self._move_batch_result_slot_for_all_modes(source, target)
        self.preview_image_index = self._selected_index_after_move(selected, source, target)
        path, width, height = self.batch_image_infos[self.preview_image_index]
        self.image_path = path
        self._update_preview_path_label(path, width, height)
        self._refresh_preview_selector()
        display_text = self._render_current_result_text()
        self._sync_result_actions(display_text)
        self.status_var.set("图片顺序已更新；将按缩略图从左到右识别和导出")

    def _delete_image_at(self, index: int) -> None:
        """删除一张图片，并保持图片、OCR 结果及当前索引一致。"""

        if not (0 <= index < len(self.batch_image_infos)):
            return

        removed_path = self.batch_image_infos[index][0]
        if self._is_recognizing and detect_upload_type(removed_path) == "document":
            self.status_var.set("正在识别文档，请完成后再删除文档")
            return
        del self.batch_image_infos[index]
        del self.batch_image_paths[index]
        del self.image_regions[index]
        self._ensure_image_edit_states()
        if 0 <= index < len(self.image_edit_states):
            del self.image_edit_states[index]
        self._delete_batch_result_slot_for_all_modes(index)
        if removed_path in self._temporary_image_paths:
            removed_path.unlink(missing_ok=True)
            self._temporary_image_paths.remove(removed_path)
        self._forget_image_preview_state([removed_path])
        self.current_result = None
        self.current_recognition_region = None
        self.selected_region = None
        self.region_selector.clear()

        if not self.batch_image_infos:
            self._cancel_after_callback("_thumbnail_generation_after_id")
            if self._preview_after_id is not None:
                self.root.after_cancel(self._preview_after_id)
                self._preview_after_id = None
            self.image_path = None
            self.preview_image_index = 0
            self.preview_source = None
            self.preview_original_size = None
            self.preview_photo = None
            self.preview_pdf_pages = []
            self.preview_pdf_photos = []
            self.preview_pdf_render_specs = []
            self.preview_pdf_page_positions = []
            self.image_edit_states = []
            self.path_var.set("尚未选择图片")
            self._batch_tasks_by_mode = {"text": [], "document": []}
            self._single_result_by_mode = {}
            self.result_text.delete("1.0", tk.END)
            self._set_result_actions_enabled(False)
            self._set_copy_feedback("")
            self._refresh_preview_selector()
            self._draw_preview_placeholder("DROP IMAGE HERE\n选择、拖拽或粘贴图片")
            self.status_var.set("已删除最后一张图片")
            self.saved_status_var.set("最近保存：无")
            self._set_dino_state("idle")
            return

        if index < self.preview_image_index:
            self.preview_image_index -= 1
        elif index == self.preview_image_index:
            self.preview_image_index = min(index, len(self.batch_image_infos) - 1)
        self._show_preview_image(self.preview_image_index)
        self.status_var.set(
            f"已删除 {removed_path.name}；剩余 {len(self.batch_image_infos)} 张图片"
        )

    def start_recognition(
        self,
        *,
        use_selected_region: bool = False,
        only_current_image: bool = False,
    ) -> None:
        """启动后台线程，避免 OCR 阻塞 Tkinter 主线程。"""

        if self._is_recognizing:
            return

        if self.image_path is None:
            messagebox.showwarning("提示", "请先选择图片。")
            return

        if self.ocr_engine is None:
            messagebox.showerror("识别失败", "识别服务尚未初始化，请重置工作台后再试。")
            return

        if self.task_queue is None:
            self.task_queue = TaskQueue()

        self._ensure_mode_result_storage()
        self._remember_current_batch_tasks_for_mode()
        self._activate_mode_result_state(self._active_recognition_mode())
        batch_count = len(self.batch_image_paths)
        batch_target_indices: list[int] | None = None
        if batch_count > 1 and not only_current_image:
            self._ensure_batch_task_slots()
            batch_target_indices = self._batch_indices_to_recognize(use_selected_region)
            if not batch_target_indices:
                display_text = self._render_current_result_text()
                self._sync_result_actions(display_text)
                self._update_current_batch_status()
                self.status_var.set(
                    f"没有新增或待识别图片；当前{self._recognition_mode_name(self.recognition_mode)}结果已保留"
                )
                self._clear_pet_drop_recognition()
                return

        run_total = (
            len(batch_target_indices)
            if batch_count > 1 and not only_current_image and batch_target_indices is not None
            else 1
        )
        self._is_recognizing = True
        self._configure_dino_run(run_total, 0)
        self._set_dino_state("working")
        self.back_button.configure(state=tk.DISABLED)
        self.mode_switch_box.configure(state=tk.DISABLED)
        self.choose_button.configure(state=tk.DISABLED)
        self.preprocess_button.configure(state=tk.DISABLED)
        self.history_search_button.configure(state=tk.DISABLED)
        self.recognize_button.configure(state=tk.DISABLED)
        self.recognize_region_button.configure(state=tk.DISABLED)
        clear_region_button = getattr(self, "clear_region_button", None)
        if clear_region_button is not None:
            clear_region_button.configure(state=tk.DISABLED)
        self._refresh_preview_selector()
        self.status_var.set(
            "正在按队列批量识别：有选区的图片识别选区，未框选的图片识别整图……"
            if use_selected_region and batch_count > 1 and not only_current_image
            else "正在识别当前图片的选区……"
            if only_current_image
            else "正在解析文档（CPU 模式可能需要数分钟）……"
            if self.recognition_mode == "document"
            else (
                f"正在按队列批量识别 {batch_count} 张图片（首次运行可能需要加载模型）……"
                if batch_count > 1
                else "正在识别（首次运行可能需要加载模型）……"
            )
        )
        self.current_result = None
        self._single_result_by_mode.pop(self._active_recognition_mode(), None)
        if not only_current_image and batch_count > 1:
            assert batch_target_indices is not None
            self._reset_batch_recognition_slots(batch_target_indices)
            if len(batch_target_indices) < batch_count:
                self.status_var.set(
                    f"正在识别新增或待更新的 {len(batch_target_indices)} 张图片；"
                    f"已有 {batch_count - len(batch_target_indices)} 张结果已保留……"
                )
        elif not only_current_image:
            self.current_batch_tasks = []
        self._batch_progress_queue = queue.Queue()
        self._batch_process_dead_polls = 0
        self.current_recognition_region = self.selected_region if use_selected_region else None
        self._recognizing_single_index = self.preview_image_index if only_current_image else None
        self.result_text.delete("1.0", tk.END)
        self._set_result_actions_enabled(False)
        self._set_copy_feedback("")
        self.saved_status_var.set("最近保存：保存中")

        assert self.task_queue is not None
        assert self.ocr_engine is not None
        if batch_count > 1 and not only_current_image:
            assert batch_target_indices is not None
            self.current_task_id = None
            image_paths = [self.batch_image_paths[index] for index in batch_target_indices]
            mode = self._active_recognition_mode()
            preprocess_config = self._current_preprocess_config(batch_target_indices[0])
            preprocess_configs = [self._current_preprocess_config(index) for index in batch_target_indices]
            render_mode = self._current_render_mode()
            process_context = mp.get_context("spawn")
            self._batch_process_queue = process_context.Queue()
            regions = [
                self._recognition_region_for_batch_index(index, use_selected_region)
                for index in batch_target_indices
            ]
            self._batch_process = process_context.Process(
                target=run_batch_process,
                args=(
                    [str(path) for path in image_paths],
                    mode,
                    preprocess_config,
                    render_mode,
                    self._batch_process_queue,
                    regions,
                    list(batch_target_indices),
                    preprocess_configs,
                ),
            )
            try:
                self._batch_process.start()
            except (OSError, RuntimeError) as exc:
                self._batch_process = None
                self._finish_batch_process()
                self._set_dino_state("error")
                self._clear_pet_drop_recognition()
                self.saved_status_var.set("最近保存：失败")
                messagebox.showerror("批量识别失败", f"无法启动 OCR 独立进程：{exc}")
                return
            display_text = self._render_current_result_text()
            self._sync_result_actions(display_text)
            self._update_current_batch_status()
            self._refresh_preview_selector()
            self.root.after(50, self._poll_batch_process)
        else:
            request = OcrRequest(
                image_path=self.image_path,
                mode=self._active_recognition_mode(),
                region=self.current_recognition_region,
                preprocess_config=self._current_preprocess_config(self.preview_image_index),
            )
            self.current_task_id = self.task_queue.submit(lambda: self.ocr_engine.recognize(request))
            self.root.after(100, self._poll_result)

    def _poll_result(self) -> None:
        if self.task_queue is None:
            return
        self._drain_batch_progress()
        task_result = self.task_queue.poll_result()
        if task_result is None:
            self.root.after(100, self._poll_result)
            return
        if self.current_task_id is not None and task_result.task_id != self.current_task_id:
            self.root.after(100, self._poll_result)
            return

        target_index = self._recognizing_single_index
        self._recognizing_single_index = None
        self._is_recognizing = False
        self.back_button.configure(state=tk.NORMAL)
        self.mode_switch_box.configure(state=tk.NORMAL)
        self.choose_button.configure(state=tk.NORMAL)
        self.preprocess_button.configure(state=tk.NORMAL)
        self.history_search_button.configure(state=tk.NORMAL)
        self.recognize_button.configure(state=tk.NORMAL)
        self.recognize_region_button.configure(state=tk.NORMAL)
        self.clear_region_button.configure(state=tk.NORMAL)
        self._refresh_preview_selector()
        if task_result.status == TaskStatus.SUCCESS and task_result.value is not None:
            execution = task_result.value
            if isinstance(execution, list):
                self._update_dino_progress(len(execution), max(1, len(execution)))
                self._set_dino_state("done")
                self._handle_batch_result(execution)
                self._show_pet_drop_completion()
                return
            self._update_dino_progress(1, 1)
            self._set_dino_state("done")
            result = execution.ocr_result
            assert isinstance(result, OcrResult)
            if target_index is not None:
                self._store_selected_region_result(target_index, execution)
                return
            self.current_result = result
            display_text = self._render_current_result_text()
            self._sync_result_actions(display_text)
            self._set_copy_feedback("")
            summary = "；".join(step.description for step in execution.steps) or "未启用额外预处理"
            self.history_manager.add_entry(
                result.image_path,
                display_text,
                region=self.current_recognition_region,
                preprocess_summary=summary,
                elapsed_seconds=result.elapsed_seconds + execution.preprocess_seconds,
            )
            self.current_record_id = self._save_recognition_record(
                self.image_path or result.image_path,
                result.render_text("plain").strip() or display_text,
                layout_text=result.render_text("layout").strip() or display_text,
                ocr_blocks=self._ocr_blocks_to_dicts(result),
                recognition_mode=self._active_recognition_mode(),
                region=self.current_recognition_region,
                image_index=self.preview_image_index,
            )
            self._remember_current_single_result_for_mode()
            self.status_var.set(
                f"识别完成：{len(result.blocks)} 个文本块，预处理 {execution.preprocess_seconds:.2f} 秒，OCR {result.elapsed_seconds:.2f} 秒"
            )
            self._show_pet_drop_completion()
        else:
            self._set_dino_state("error")
            self._clear_pet_drop_recognition()
            self.current_result = None
            if target_index is not None:
                self._store_selected_region_error(target_index, str(task_result.error))
            self.status_var.set("识别失败")
            self._set_result_actions_enabled(False)
            self.saved_status_var.set("最近保存：失败")
            self._set_copy_feedback("")
            messagebox.showerror("识别失败", str(task_result.error))

    def _poll_batch_process(self) -> None:
        """轮询独立 OCR 进程；界面事件循环始终留在主进程。"""

        if self._batch_process_queue is None:
            return

        terminal_message: tuple[str, object] | None = None
        while True:
            try:
                message = self._batch_process_queue.get_nowait()
            except queue.Empty:
                break
            except (EOFError, OSError) as exc:
                terminal_message = ("error", str(exc))
                break

            kind = message[0]
            if kind == "progress":
                _kind, completed, total, task = message
                self._handle_batch_progress(completed, total, task)
            elif kind == "complete":
                terminal_message = ("complete", message[1])
            elif kind == "error":
                terminal_message = ("error", message[1])

        if terminal_message is not None:
            kind, payload = terminal_message
            self._finish_batch_process()
            if kind == "complete":
                self._handle_batch_result(list(self.current_batch_tasks))
                self._show_pet_drop_completion()
            else:
                self._set_dino_state("error")
                self._clear_pet_drop_recognition()
                display_text = self._render_current_result_text()
                self._sync_result_actions(display_text)
                self.status_var.set(
                    f"批量识别中断：已完成 {len(self.current_batch_tasks)}/{len(self.batch_image_infos)} 张"
                )
                self.saved_status_var.set("最近保存：失败")
                messagebox.showerror("批量识别失败", str(payload))
            return

        process = self._batch_process
        if process is not None and not process.is_alive():
            self._batch_process_dead_polls += 1
            if self._batch_process_dead_polls >= 10:
                exit_code = process.exitcode
                self._finish_batch_process()
                self._set_dino_state("error")
                self._clear_pet_drop_recognition()
                self.status_var.set("批量识别进程异常退出")
                self.saved_status_var.set("最近保存：失败")
                messagebox.showerror("批量识别失败", f"OCR 进程异常退出（代码 {exit_code}）。")
                return
        else:
            self._batch_process_dead_polls = 0

        self.root.after(50, self._poll_batch_process)

    def _finish_batch_process(self) -> None:
        """回收批量进程并恢复识别工作区控件。"""

        process = self._batch_process
        if process is not None:
            process.join(timeout=0.2)
        process_queue = self._batch_process_queue
        if process_queue is not None:
            process_queue.close()
        self._batch_process = None
        self._batch_process_queue = None
        self._batch_process_dead_polls = 0
        self._is_recognizing = False
        self._set_dino_state("done")
        self.back_button.configure(state=tk.NORMAL)
        self.mode_switch_box.configure(state=tk.NORMAL)
        self.choose_button.configure(state=tk.NORMAL)
        self.preprocess_button.configure(state=tk.NORMAL)
        self.history_search_button.configure(state=tk.NORMAL)
        self.recognize_button.configure(state=tk.NORMAL)
        self.recognize_region_button.configure(state=tk.NORMAL)
        self.clear_region_button.configure(state=tk.NORMAL)
        self._refresh_preview_selector()

    def _terminate_batch_process(self) -> None:
        """关闭窗口时终止仍在执行的批量 OCR 子进程。"""

        process = self._batch_process
        if process is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=1.0)
        process_queue = self._batch_process_queue
        if process_queue is not None:
            process_queue.close()
        self._batch_process = None
        self._batch_process_queue = None

    def _enqueue_batch_progress(self, completed: int, total: int, task: OCRTask) -> None:
        """由 OCR 工作线程把单张完成事件放入线程安全队列。"""

        self._batch_progress_queue.put((completed, total, task))

    def _drain_batch_progress(self) -> None:
        """在 Tkinter 主线程中消费逐张完成事件并立即刷新界面。"""

        while True:
            try:
                completed, total, task = self._batch_progress_queue.get_nowait()
            except queue.Empty:
                return
            self._handle_batch_progress(completed, total, task)

    def _handle_batch_progress(self, completed: int, total: int, task: OCRTask) -> None:
        """接收一张图片的 OCR 结果，不等待其余批量任务。"""

        task.extra.setdefault("recognition_mode", self._active_recognition_mode())
        task_index = self._current_index_for_task(task)
        if task_index is None:
            return
        if task_index < len(self.current_batch_tasks):
            self.current_batch_tasks[task_index] = task
        else:
            while len(self.current_batch_tasks) <= task_index and len(self.current_batch_tasks) < len(self.batch_image_infos):
                path = self.batch_image_infos[len(self.current_batch_tasks)][0]
                self.current_batch_tasks.append(OCRTask(image_path=str(path), status=OCRTaskQueue.WAITING))
            if task_index < len(self.current_batch_tasks):
                self.current_batch_tasks[task_index] = task

        self._update_dino_progress(completed, total)
        self._record_finished_batch_task(task)
        display_text = self._render_current_result_text()
        self._sync_result_actions(display_text)
        self._update_current_batch_status()

    def _current_index_for_task(self, task: OCRTask) -> int | None:
        """识别期间用户可能删除图片；按路径把完成任务映射回当前队列。"""

        source_index = task.extra.get("source_index")
        paths = getattr(self, "batch_image_paths", [item[0] for item in getattr(self, "batch_image_infos", [])])
        if isinstance(source_index, int) and source_index < len(paths):
            if str(paths[source_index]) == task.image_path:
                return source_index
        for index, path in enumerate(paths):
            if str(path) == task.image_path:
                return index
        return None

    def _record_finished_batch_task(self, task: OCRTask) -> None:
        """逐张写入历史和存储，并用标记避免最终汇总时重复保存。"""

        if task.status != OCRTaskQueue.FINISHED or task.extra.get("gui_recorded"):
            return
        self.history_manager.add_entry(
            task.image_path,
            task.result_text,
            region=task.extra.get("region"),
            preprocess_summary=str(task.extra.get("preprocess_summary", "")),
            elapsed_seconds=float(task.extra.get("elapsed_seconds", 0.0)),
        )
        layout_text = task.result_text
        result = task.extra.get("ocr_result")
        ocr_blocks = None
        if isinstance(result, OcrResult):
            layout_text = result.render_text("layout").strip() or task.result_text
            ocr_blocks = self._ocr_blocks_to_dicts(result)
        record_id = self._save_recognition_record(
            task.image_path,
            task.result_text,
            layout_text=layout_text,
            ocr_blocks=ocr_blocks,
            recognition_mode=str(task.extra.get("recognition_mode") or self._active_recognition_mode()),
            region=task.extra.get("region"),
        )
        if record_id:
            task.extra["record_id"] = record_id
        task.extra["gui_recorded"] = True

    def _ensure_batch_task_slots(self) -> None:
        """为多图中的逐张选区识别补齐与图片队列对齐的结果槽。"""

        self._remember_current_batch_tasks_for_mode()
        mode = self._active_recognition_mode()
        while len(self.current_batch_tasks) < len(self.batch_image_infos):
            path = self.batch_image_infos[len(self.current_batch_tasks)][0]
            task = OCRTask(image_path=str(path), status=OCRTaskQueue.WAITING)
            task.extra["recognition_mode"] = mode
            self.current_batch_tasks.append(task)
        self._mark_batch_tasks_mode(self.current_batch_tasks, mode, only_missing=True)

    def _batch_indices_to_recognize(self, use_selected_region: bool) -> list[int]:
        """返回本次批量 OCR 真正需要处理的图片索引。"""

        return [
            index
            for index in range(len(self.batch_image_infos))
            if not self._batch_task_can_be_reused(index, use_selected_region)
        ]

    def _batch_task_can_be_reused(self, index: int, use_selected_region: bool) -> bool:
        """已有结果只在图片、状态、识别模式和识别范围都匹配时复用。"""

        if not (0 <= index < len(self.batch_image_infos)):
            return False
        if index >= len(self.current_batch_tasks):
            return False

        path = self.batch_image_infos[index][0]
        task = self.current_batch_tasks[index]
        if task.image_path != str(path):
            return False
        if task.status != OCRTaskQueue.FINISHED:
            return False
        if task.extra.get("result_cleared"):
            return False
        if not self._task_belongs_to_active_mode(task):
            return False

        expected_region = self._recognition_region_for_batch_index(index, use_selected_region)
        return task.extra.get("region") == expected_region

    def _recognition_region_for_batch_index(
        self,
        index: int,
        use_selected_region: bool,
    ) -> tuple[int, int, int, int] | None:
        if not use_selected_region:
            return None
        regions = getattr(self, "image_regions", [])
        return regions[index] if 0 <= index < len(regions) else None

    def _reset_batch_recognition_slots(self, indices: list[int]) -> None:
        """清空本次将重新识别的槽位，避免显示旧结果。"""

        for index in indices:
            if not (0 <= index < len(self.batch_image_infos)):
                continue
            path = self.batch_image_infos[index][0]
            self.current_batch_tasks[index] = OCRTask(
                image_path=str(path),
                status=OCRTaskQueue.WAITING,
            )
            self.current_batch_tasks[index].extra["recognition_mode"] = self._active_recognition_mode()

    def _invalidate_result_slot_for_image_edit(self, index: int) -> None:
        """图片内容编辑后，清理该图在各识别模式下的旧结果。"""

        self._ensure_mode_result_storage()
        path = self.batch_image_infos[index][0] if 0 <= index < len(self.batch_image_infos) else None
        for tasks in self._known_batch_task_lists():
            if 0 <= index < len(tasks):
                task_path = str(path) if path is not None else tasks[index].image_path
                mode = tasks[index].extra.get("recognition_mode")
                replacement = OCRTask(image_path=task_path, status=OCRTaskQueue.WAITING)
                if mode in {"text", "document"}:
                    replacement.extra["recognition_mode"] = mode
                tasks[index] = replacement
        self._single_result_by_mode.clear()
        self.current_result = None
        self.current_record_id = None
        self.current_recognition_region = None
        if hasattr(self, "result_text"):
            self.result_text.delete("1.0", tk.END)
        if hasattr(self, "copy_feedback_var"):
            self._set_copy_feedback("")
        if hasattr(self, "copy_button"):
            self._set_result_actions_enabled(False)

    def _store_selected_region_result(self, index: int, execution: OcrExecutionResult) -> None:
        """把当前图片的选区结果写回对应缩略图，而不触碰其他图片。"""

        if not (0 <= index < len(self.batch_image_infos)):
            return
        path = self.batch_image_infos[index][0]
        if index < len(self.current_batch_tasks) and self.current_batch_tasks[index].image_path != str(path):
            return
        result = execution.ocr_result
        assert isinstance(result, OcrResult)
        text = result.render_text(self._current_render_mode()).strip()
        summary = "；".join(step.description for step in execution.steps) or "未启用额外预处理"
        task = OCRTask(
            image_path=str(self.batch_image_infos[index][0]),
            status=OCRTaskQueue.FINISHED,
            result_text=text or "（未识别到文字）",
        )
        task.extra.update(
            {
                "ocr_result": result,
                "region": self.current_recognition_region,
                "preprocess_summary": summary,
                "elapsed_seconds": result.elapsed_seconds + execution.preprocess_seconds,
                "source_index": index,
                "recognition_mode": self._active_recognition_mode(),
            }
        )
        self._ensure_batch_task_slots()
        self.current_batch_tasks[index] = task
        self._record_finished_batch_task(task)
        display_text = self._render_current_result_text()
        self._sync_result_actions(display_text)
        self._set_copy_feedback("")
        self._update_current_batch_status()

    def _store_selected_region_error(self, index: int, error: str) -> None:
        """把多图中的单张选区识别失败记录到对应结果槽。"""

        if not (0 <= index < len(self.batch_image_infos)):
            return
        task = OCRTask(
            image_path=str(self.batch_image_infos[index][0]),
            status=OCRTaskQueue.FAILED,
            error_message=error,
        )
        task.extra["region"] = self.current_recognition_region
        task.extra["recognition_mode"] = self._active_recognition_mode()
        self._ensure_batch_task_slots()
        self.current_batch_tasks[index] = task
        display_text = self._render_current_result_text()
        self._sync_result_actions(display_text)
        self._update_current_batch_status()

    def _handle_batch_result(self, tasks: list[OCRTask]) -> None:
        """展示批量队列识别结果，并记录成功任务历史。"""

        finished = [task for task in tasks if task.status == OCRTaskQueue.FINISHED]
        failed = [task for task in tasks if task.status == OCRTaskQueue.FAILED]
        self._mark_batch_tasks_mode(tasks, self._active_recognition_mode(), only_missing=True)
        for task in tasks:
            self._record_finished_batch_task(task)

        self.current_result = None
        self.current_batch_tasks = tasks
        self._remember_current_batch_tasks_for_mode()
        display_text = self._render_current_result_text()
        self._sync_result_actions(display_text)
        self._set_copy_feedback("")
        self._update_current_batch_status()
        if not finished:
            self.saved_status_var.set("最近保存：失败")
        if failed:
            messagebox.showwarning(
                "批量识别完成",
                f"有 {len(failed)} 张图片识别失败，请切换到对应图片查看流程状态条。",
            )

    def _return_to_start(self) -> None:
        """Release current services and return to the OCR mode choice screen."""

        self._terminate_batch_process()
        self._cancel_pending_ui_callbacks()
        if self.ocr_engine is not None:
            self.ocr_engine.close()
        if self.task_queue is not None:
            self.task_queue.shutdown()
        self._unbind_image_paste()
        self._unbind_workspace_shortcuts()
        self._disable_drag_drop()
        mini_game_window = getattr(self, "_mini_pixel_game_window", None)
        if mini_game_window is not None:
            mini_game_window.destroy()
            self._mini_pixel_game_window = None
        self._clear_temporary_images()

        self.ocr_engine = None
        self.task_queue = None
        self.current_task_id = None
        self._is_recognizing = False
        self.recognition_mode = None
        self._pending_pet_drop_paths = []
        self._pet_drop_recognition_active = False
        self._floating_pet.clear_assistant_panel()
        self.image_path = None
        self.batch_image_paths = []
        self.batch_image_infos = []
        self.image_regions = []
        self.preview_image_index = 0
        self.current_result = None
        self.current_record_id = None
        self.current_batch_tasks = []
        self._batch_tasks_by_mode = {"text": [], "document": []}
        self._single_result_by_mode = {}
        self.current_recognition_region = None
        self._recognizing_single_index = None
        self.selected_region = None
        self.region_selector.clear()
        self.preview_source = None
        self.preview_original_size = None
        self.preview_photo = None
        self.thumbnail_photos = []
        self._thumbnail_photo_cache.clear()
        self._thumbnail_failed_paths.clear()
        self._preview_source_cache.clear()
        self._preview_original_size_cache.clear()
        self.path_var.set("尚未选择图片")
        self.status_var.set("就绪")
        self.mode_switch_var.set(FAST_MODE_LABEL)
        self.image_index_var.set("当前图片：0 / 0")
        self.saved_status_var.set("最近保存：无")
        self.copy_feedback_var.set("")
        self._clear_root()
        self._size_window(960, 620, min_width=760, min_height=520)
        self._build_start_screen()

    def _clear_temporary_images(self) -> None:
        for path in self._temporary_image_paths:
            path.unlink(missing_ok=True)
        self._temporary_image_paths.clear()

    def _on_close(self) -> None:
        """关闭窗口时释放模型和剪贴板临时图片。"""

        if self._is_quitting:
            return
        self._is_quitting = True
        self._cancel_after_callback("_minimize_after_id")
        self._floating_pet.destroy()
        mini_game_window = getattr(self, "_mini_pixel_game_window", None)
        if mini_game_window is not None:
            mini_game_window.destroy()
        self._terminate_batch_process()
        self._cancel_pending_ui_callbacks()
        self._cancel_widget_callbacks(self.root)
        if self.ocr_engine is not None:
            self.ocr_engine.close()
        if self.task_queue is not None:
            self.task_queue.shutdown()
        self._clear_temporary_images()
        self._temporary_directory.cleanup()
        self.root.destroy()

    def copy_result_text(self) -> None:
        """复制当前识别结果，并给出明确反馈。"""

        text = self.result_text.get("1.0", tk.END).strip()
        if not text:
            self._set_copy_feedback("当前没有可复制内容。")
            return

        self._copy_to_clipboard(text, "复制成功。")

    def save_edited_text(self) -> None:
        """保存当前用户编辑后的文本，不覆盖 OCR 原文。"""

        record_id = ""
        if self.current_batch_tasks and 0 <= self.preview_image_index < len(self.current_batch_tasks):
            record_id = str(self.current_batch_tasks[self.preview_image_index].extra.get("record_id") or "")
        if not record_id:
            record_id = self.current_record_id or ""
        if not record_id:
            self._set_copy_feedback("当前结果尚未保存记录。")
            return

        text = self.result_text.get("1.0", tk.END).strip()
        try:
            self.storage_manager.update_edited_text(record_id, text)
        except Exception as exc:  # noqa: BLE001 - GUI should keep edited text visible if save fails.
            self.saved_status_var.set("最近保存：失败")
            messagebox.showerror("保存失败", str(exc))
            return
        self.saved_status_var.set("最近保存：已保存编辑文本")
        self._set_copy_feedback("编辑文本已保存。")

    def export_result_txt(self) -> None:
        """把当前结果导出为 TXT。"""

        if self._is_recognizing and len(self.batch_image_infos) > 1:
            messagebox.showinfo("批量识别进行中", "全部图片识别完成后即可批量导出 TXT。")
            return

        if len(self.current_batch_tasks) > 1:
            export_mode = self._ask_batch_export_mode()
            if export_mode == "separate":
                self._export_batch_as_separate_txt()
            elif export_mode == "merged":
                self._export_batch_as_merged_txt()
            return

        text = self.result_text.get("1.0", tk.END).strip()
        if not text:
            self._set_copy_feedback("当前没有可导出内容。")
            return

        output_path = filedialog.asksaveasfilename(
            title="导出TXT",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt")],
        )
        if not output_path:
            return
        try:
            Path(output_path).write_text(text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc))
            return
        self._set_copy_feedback("TXT 已导出。")

    def _ask_batch_export_mode(self) -> str | None:
        """让用户明确选择批量 TXT 的导出方式。"""

        selection: dict[str, str | None] = {"mode": None}
        window = create_independent_window("选择 TXT 导出方式", resizable=False)

        frame = ttk.Frame(window, padding=18)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(
            frame,
            text=f"当前共有 {len(self.current_batch_tasks)} 张图片，请选择导出方式：",
        ).pack(anchor=tk.W, pady=(0, 14))

        def choose(mode: str | None) -> None:
            selection["mode"] = mode
            window.destroy()

        ttk.Button(
            frame,
            text=f"分别导出 {len(self.current_batch_tasks)} 个 TXT",
            command=lambda: choose("separate"),
        ).pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            frame,
            text="合并导出为 1 个 TXT",
            command=lambda: choose("merged"),
        ).pack(fill=tk.X, pady=(0, 8))
        ttk.Button(frame, text="取消", command=lambda: choose(None)).pack(fill=tk.X)

        window.protocol("WM_DELETE_WINDOW", lambda: choose(None))
        self._center_child_window(window)
        window.deiconify()
        window.lift()
        window.wait_window()
        return selection["mode"]

    def _batch_export_entries(self) -> list[tuple[Path, str]]:
        """按图片导入顺序返回适用于导出的路径和文本。"""

        return [
            (Path(task.image_path), self._render_batch_task_text(task))
            for task in self.current_batch_tasks
        ]

    def _export_batch_as_separate_txt(self) -> None:
        """在用户选择的目录中为每张图片写入一个 TXT。"""

        output_directory = filedialog.askdirectory(title="选择分别导出 TXT 的文件夹")
        if not output_directory:
            return

        entries = self._batch_export_entries()
        filenames = build_separate_txt_names([image_path for image_path, _text in entries])
        output_paths = [Path(output_directory) / filename for filename in filenames]
        existing_count = sum(path.exists() for path in output_paths)
        if existing_count and not messagebox.askyesno(
            "确认覆盖",
            f"目标文件夹中已有 {existing_count} 个同名 TXT，是否覆盖？",
        ):
            return

        try:
            for output_path, (_image_path, text) in zip(output_paths, entries, strict=True):
                output_path.write_text(text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc))
            return
        self._set_copy_feedback(f"已分别导出 {len(output_paths)} 个 TXT。")

    def _export_batch_as_merged_txt(self) -> None:
        """把全部图片的文本按队列顺序写入一个 TXT。"""

        output_path = filedialog.asksaveasfilename(
            title="合并导出全部 TXT",
            initialfile="批量识别结果.txt",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt")],
        )
        if not output_path:
            return

        text = build_merged_batch_text(self._batch_export_entries())
        try:
            Path(output_path).write_text(text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("导出失败", str(exc))
            return
        self._set_copy_feedback("全部结果已合并导出。")

    def clear_result_text(self) -> None:
        """清空右侧识别结果。"""

        if self._clear_current_batch_result():
            return

        self.current_result = None
        self.current_record_id = None
        self.current_recognition_region = None
        self._ensure_mode_result_storage()
        self._single_result_by_mode.pop(self._active_recognition_mode(), None)
        self.result_text.delete("1.0", tk.END)
        self._set_result_actions_enabled(False)
        self._set_copy_feedback("")
        self.status_var.set("已清空识别结果")

    def _clear_current_batch_result(self) -> bool:
        """批量模式下只清空当前预览图片对应的 OCR 文本。"""

        if not self.current_batch_tasks:
            return False
        if not (0 <= self.preview_image_index < len(self.current_batch_tasks)):
            return False

        task = self.current_batch_tasks[self.preview_image_index]
        if not self._task_belongs_to_active_mode(task):
            return False
        task.status = OCRTaskQueue.FINISHED
        task.result_text = ""
        task.error_message = ""
        task.extra.pop("ocr_result", None)
        task.extra.pop("record_id", None)
        task.extra["result_cleared"] = True
        self.current_result = None
        self.current_record_id = None
        self.current_recognition_region = None
        self.result_text.delete("1.0", tk.END)
        display_text = self._render_current_result_text()
        self._sync_result_actions(display_text)
        self._set_copy_feedback("")
        self.status_var.set("已清空当前图片的识别结果")
        return True

    def _toggle_display_mode(self) -> None:
        """Switch between compact text and approximate original layout."""

        next_mode = "按原位置排版" if self.display_mode_var.get() == "全文拼接" else "全文拼接"
        self.display_mode_var.set(next_mode)
        self._on_display_mode_change()
        self.status_var.set(f"已切换到{next_mode}")
        self._show_mode_toast("显示方式已切换", next_mode)

    def _on_display_mode_change(self, _event: tk.Event | None = None) -> None:
        display_text = self._render_current_result_text()
        self._sync_result_actions(display_text)

    def _render_current_result_text(self) -> str:
        self.result_text.delete("1.0", tk.END)
        showing_batch = bool(self.current_batch_tasks) or (
            len(self.batch_image_infos) > 1 and self._is_recognizing
        )
        if showing_batch:
            if self.preview_image_index < len(self.current_batch_tasks):
                display_text = self._render_batch_task_text(
                    self.current_batch_tasks[self.preview_image_index]
                )
            else:
                display_text = ""
            if display_text:
                self.result_text.insert("1.0", display_text)
            return display_text

        if self.current_result is None:
            return ""

        display_text = self.current_result.render_text(self._current_render_mode()).strip()
        if not display_text:
            display_text = "（未识别到文字）"
        self.result_text.insert("1.0", display_text)
        return display_text

    def _render_batch_task_text(self, task: OCRTask) -> str:
        """按当前显示方式渲染一张批量图片的识别结果。"""

        if not self._task_belongs_to_active_mode(task):
            return ""
        if task.status == OCRTaskQueue.FAILED:
            return ""

        result = task.extra.get("ocr_result")
        if isinstance(result, OcrResult):
            text = result.render_text(self._current_render_mode()).strip()
        else:
            text = task.result_text.strip()
        return text

    def _update_current_batch_status(self) -> None:
        """只在流程状态条显示当前批量图片的识别状态。"""

        total = len(self.batch_image_infos)
        if total <= 1:
            return

        completed = sum(
            self._task_belongs_to_active_mode(task)
            and task.status in {OCRTaskQueue.FINISHED, OCRTaskQueue.FAILED}
            for task in self.current_batch_tasks
        )
        current = self.preview_image_index
        if current >= len(self.current_batch_tasks) or self.current_batch_tasks[current].status not in {
            OCRTaskQueue.FINISHED,
            OCRTaskQueue.FAILED,
        } or not self._task_belongs_to_active_mode(self.current_batch_tasks[current]):
            state = "等待识别" if self._is_recognizing else "尚未识别"
        else:
            task = self.current_batch_tasks[current]
            if task.status == OCRTaskQueue.FAILED:
                error = " ".join(task.error_message.split())
                if len(error) > 60:
                    error = f"{error[:60]}…"
                state = f"识别失败：{error}" if error else "识别失败"
            elif self._render_batch_task_text(task):
                state = "识别完成"
            else:
                state = "识别完成（未检测到文字）"

        self.status_var.set(
            f"当前图片 {current + 1}/{total}：{state}；批量进度 {completed}/{total}"
        )

    def _sync_result_actions(self, display_text: str) -> None:
        """根据当前图片是否已有结果，更新复制、导出和清空按钮。"""

        enabled = bool(display_text)
        self._set_result_actions_enabled(enabled)
        if self.current_batch_tasks or (
            len(self.batch_image_infos) > 1 and self._is_recognizing
        ):
            batch_complete = len(self.current_batch_tasks) == len(self.batch_image_infos) and all(
                task.status in {OCRTaskQueue.FINISHED, OCRTaskQueue.FAILED}
                for task in self.current_batch_tasks
            )
            self.export_txt_button.configure(
                state=tk.NORMAL if batch_complete and not self._is_recognizing else tk.DISABLED
            )
            self.clear_result_button.configure(
                state=tk.NORMAL if enabled and not self._is_recognizing else tk.DISABLED
            )

    def _current_render_mode(self) -> str:
        return "layout" if self.display_mode_var.get() == "按原位置排版" else "plain"

    def _copy_to_clipboard(self, text: str, feedback: str) -> None:
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update_idletasks()
        self._set_copy_feedback(feedback)

    def _set_copy_feedback(self, message: str) -> None:
        if self._copy_feedback_after_id is not None:
            self.root.after_cancel(self._copy_feedback_after_id)
            self._copy_feedback_after_id = None

        self.copy_feedback_var.set(message)
        if message:
            self._copy_feedback_after_id = self.root.after(2500, self._clear_copy_feedback)

    def _clear_copy_feedback(self) -> None:
        self._copy_feedback_after_id = None
        self.copy_feedback_var.set("")

    def _current_preprocess_config(self, image_index: int | None = None) -> PreprocessConfig:
        """从界面开关生成预处理配置。"""

        use_grayscale = self.grayscale_var.get() if hasattr(self, "grayscale_var") else False
        use_binarize = self.binarize_var.get() if hasattr(self, "binarize_var") else False
        use_denoise = self.denoise_var.get() if hasattr(self, "denoise_var") else False
        if not hasattr(self, "preprocess_step_order"):
            self.preprocess_step_order = list(PREPROCESS_STEP_ORDER)
        edit_state = self._edit_state_for_index(image_index) if image_index is not None else self._current_image_edit_state()
        return PreprocessConfig(
            enable_grayscale=use_grayscale,
            binarize_mode="adaptive" if use_binarize else "none",
            denoise_mode="median" if use_denoise else "none",
            step_order=tuple(self.preprocess_step_order),
            rotation_quarters=edit_state.rotation_quarters,
            mirror_horizontal=edit_state.mirrored,
            mirror_vertical=edit_state.vertical_mirrored,
        )

    def _set_result_actions_enabled(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self.copy_button.configure(state=state)
        self.export_txt_button.configure(state=state)
        self.clear_result_button.configure(state=state)
        if hasattr(self, "save_edit_button"):
            self.save_edit_button.configure(state=state)

    @staticmethod
    def _ocr_blocks_to_dicts(result: OcrResult) -> list[dict[str, object]]:
        return [
            {
                "text": block.text,
                "confidence": block.confidence,
                "box": block.box,
            }
            for block in result.blocks
        ]

    def _save_recognition_record(
        self,
        image_path: str | Path,
        text: str,
        *,
        layout_text: str | None = None,
        ocr_blocks: list[dict[str, object]] | None = None,
        recognition_mode: str | None = None,
        region: tuple[int, int, int, int] | None = None,
        image_index: int | None = None,
    ) -> str | None:
        """保存 OCR 结果，并更新底部保存状态。"""

        try:
            edit_state = (
                self._edit_state_for_index(image_index)
                if image_index is not None
                else self._edit_state_for_path(Path(image_path))
            )
            record = self.storage_manager.save_record(
                image_path,
                text,
                layout_text=layout_text,
                ocr_blocks=ocr_blocks,
                recognition_mode=recognition_mode or self._active_recognition_mode(),
                region=region,
                rotation_quarters=edit_state.rotation_quarters,
                mirror_horizontal=edit_state.mirrored,
                mirror_vertical=edit_state.vertical_mirrored,
            )
        except Exception as exc:  # noqa: BLE001 - GUI should keep OCR result visible if save fails.
            self.saved_status_var.set("最近保存：失败")
            print(f"[WARNING] OCR 结果保存失败: {exc}")
            return None
        self.saved_status_var.set("最近保存：已保存")
        record_id = str(record.get("record_id", "")).strip()
        return record_id or None

    def _clear_selected_region(self) -> None:
        """清除当前框选区域。"""

        self.selected_region = None
        if 0 <= self.preview_image_index < len(self.image_regions):
            self.image_regions[self.preview_image_index] = None
        self.region_selector.clear()
        self._render_preview()
        self.status_var.set("已清除识别区域")

    def _recognize_selected_region(self) -> None:
        """多图时批量识别各自选区；未框选的图片默认识别整图。"""

        if self.image_path is None:
            messagebox.showwarning("提示", "请先选择图片。")
            return
        if self._active_recognition_mode() == "document" and self.image_path is not None and detect_upload_type(self.image_path) == "document":
            messagebox.showwarning("提示", "PDF 文档不支持框选识别，请使用“识别文档”。")
            return
        if len(self.batch_image_infos) == 1 and self.selected_region is None:
            messagebox.showwarning("提示", "请先在图片预览区拖拽框选一个区域。")
            return
        if self._active_recognition_mode() == "document" and self.image_path is not None and detect_upload_type(self.image_path) == "document":
            self.start_recognition(use_selected_region=False)
            return
        self.start_recognition(use_selected_region=True)

    def _on_region_press(self, event: tk.Event) -> None:
        if self.preview_source is None:
            self._draw_preview_placeholder("DROP IMAGE HERE\n选择、拖拽或粘贴图片")
            return
        if getattr(self, "preview_pdf_pages", []):
            return
        self.region_selector.begin(event.x, event.y)

    def _draw_selection_rectangle(self, x1: int, y1: int, x2: int, y2: int) -> None:
        """Draw a precise dashed selection rectangle with local contrast colors."""

        self.preview_canvas.delete("selection")
        left, right = sorted((int(round(x1)), int(round(x2))))
        top, bottom = sorted((int(round(y1)), int(round(y2))))
        if right - left < 2 or bottom - top < 2:
            return

        dash = 10
        gap = 5
        self._draw_selection_edge(left, top, right, top, horizontal=True, dash=dash, gap=gap)
        self._draw_selection_edge(left, bottom, right, bottom, horizontal=True, dash=dash, gap=gap)
        self._draw_selection_edge(left, top, left, bottom, horizontal=False, dash=dash, gap=gap)
        self._draw_selection_edge(right, top, right, bottom, horizontal=False, dash=dash, gap=gap)

    def _draw_selection_edge(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        *,
        horizontal: bool,
        dash: int,
        gap: int,
    ) -> None:
        length = abs((x2 - x1) if horizontal else (y2 - y1))
        if length <= 0:
            return

        position = 0
        while position < length:
            segment_end = min(length, position + dash)
            if horizontal:
                start_x = x1 + position
                end_x = x1 + segment_end
                midpoint_x = (start_x + end_x) / 2
                color = self._selection_outline_color(midpoint_x, y1)
                self.preview_canvas.create_line(
                    start_x,
                    y1,
                    end_x,
                    y1,
                    fill=color,
                    width=2,
                    tags="selection",
                )
            else:
                start_y = y1 + position
                end_y = y1 + segment_end
                midpoint_y = (start_y + end_y) / 2
                color = self._selection_outline_color(x1, midpoint_y)
                self.preview_canvas.create_line(
                    x1,
                    start_y,
                    x1,
                    end_y,
                    fill=color,
                    width=2,
                    tags="selection",
                )
            position += dash + gap

    def _selection_outline_color(self, canvas_x: float, canvas_y: float) -> str:
        """Choose an ink or warm-paper line color from the image under the cursor."""

        luminance = self._preview_luminance_at(canvas_x, canvas_y)
        if luminance is None:
            return INK
        return PAPER if luminance < 132 else INK

    def _preview_luminance_at(self, canvas_x: float, canvas_y: float) -> float | None:
        if self.preview_source is None or self.preview_transform is None:
            return None
        transform = self.preview_transform
        if not (
            transform.offset_x <= canvas_x <= transform.offset_x + transform.preview_width
            and transform.offset_y <= canvas_y <= transform.offset_y + transform.preview_height
        ):
            return None

        original_width, original_height = self.preview_original_size or self.preview_source.size
        if original_width <= 0 or original_height <= 0:
            return None
        image_x = (canvas_x - transform.offset_x) / max(transform.scale_x, 0.0001)
        image_y = (canvas_y - transform.offset_y) / max(transform.scale_y, 0.0001)
        source_x = int(image_x * self.preview_source.width / original_width)
        source_y = int(image_y * self.preview_source.height / original_height)
        source_x = max(0, min(source_x, self.preview_source.width - 1))
        source_y = max(0, min(source_y, self.preview_source.height - 1))
        pixel = self.preview_source.getpixel((source_x, source_y))
        if isinstance(pixel, int):
            red = green = blue = pixel
        else:
            red, green, blue = pixel[:3]
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    def _on_region_drag(self, event: tk.Event) -> None:
        if getattr(self, "preview_pdf_pages", []):
            return
        rect = self.region_selector.update(event.x, event.y)
        if rect is None:
            return
        self._draw_selection_rectangle(*rect)

    def _on_region_release(self, event: tk.Event) -> None:
        if getattr(self, "preview_pdf_pages", []):
            return
        if self.preview_source is None or self.preview_transform is None:
            return
        try:
            self.selected_region = self.region_selector.finish(event.x, event.y, self.preview_transform)
        except ValueError as exc:
            self.status_var.set(str(exc))
            return
        if 0 <= self.preview_image_index < len(self.image_regions):
            self.image_regions[self.preview_image_index] = self.selected_region
        self._render_preview()
        self.status_var.set(f"已选择识别区域：{self.selected_region}")

    def _on_preview_resize(self, _event: tk.Event | None) -> None:
        if self._preview_after_id is not None:
            self.root.after_cancel(self._preview_after_id)
        self._preview_after_id = self.root.after(60, self._render_preview)

    def _scroll_preview_pixels(self, pixels: float) -> None:
        region = self.preview_canvas.cget("scrollregion").split()
        content_height = float(region[3]) if len(region) == 4 else float(self.preview_canvas.winfo_height())
        visible_height = max(float(self.preview_canvas.winfo_height()), 1.0)
        scrollable_height = max(content_height - visible_height, 1.0)
        top_fraction = self.preview_canvas.yview()[0]
        self.preview_canvas.yview_moveto(max(0.0, min(1.0, top_fraction + pixels / scrollable_height)))
        self._schedule_visible_pdf_pages_render()

    def _on_preview_wheel(self, event: tk.Event) -> str | None:
        if not getattr(self, "preview_pdf_pages", []):
            return None
        number = getattr(event, "num", None)
        if number == 4:
            self._scroll_preview_pixels(-120)
        elif number == 5:
            self._scroll_preview_pixels(120)
        else:
            delta = getattr(event, "delta", 0)
            if delta == 0:
                return "break"
            pixels = -delta * 2.4 if abs(delta) < 120 else -delta / 120 * 180
            self._scroll_preview_pixels(pixels)
        return "break"

    def _on_preview_pan_press(self, event: tk.Event) -> str | None:
        if not getattr(self, "preview_pdf_pages", []):
            return None
        self.preview_canvas.scan_mark(event.x, event.y)
        return "break"

    def _on_preview_pan_drag(self, event: tk.Event) -> str | None:
        if not getattr(self, "preview_pdf_pages", []):
            return None
        self.preview_canvas.scan_dragto(event.x, event.y, gain=1)
        self._schedule_visible_pdf_pages_render()
        return "break"

    def _render_preview(self) -> None:
        self._preview_after_id = None
        if self.preview_source is None:
            self._draw_preview_placeholder("DROP IMAGE HERE\n选择、拖拽或粘贴图片")
            return
        if getattr(self, "preview_pdf_pages", []):
            self._render_pdf_preview()
            return

        canvas_width = max(self.preview_canvas.winfo_width(), 320)
        canvas_height = max(self.preview_canvas.winfo_height(), 240)
        self.preview_transform = build_preview_transform(
            self.preview_original_size or self.preview_source.size,
            (canvas_width, canvas_height),
            padding=24,
        )

        preview = self.preview_source.copy()
        preview.thumbnail((self.preview_transform.preview_width, self.preview_transform.preview_height), Image.Resampling.LANCZOS)
        self.preview_photo = ImageTk.PhotoImage(preview)

        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(
            canvas_width // 2,
            canvas_height // 2,
            image=self.preview_photo,
            anchor=tk.CENTER,
        )
        if self.selected_region is not None and self.preview_transform is not None:
            left, top, right, bottom = self.selected_region
            x1 = self.preview_transform.offset_x + int(round(left * self.preview_transform.scale_x))
            y1 = self.preview_transform.offset_y + int(round(top * self.preview_transform.scale_y))
            x2 = self.preview_transform.offset_x + int(round(right * self.preview_transform.scale_x))
            y2 = self.preview_transform.offset_y + int(round(bottom * self.preview_transform.scale_y))
            self._draw_selection_rectangle(x1, y1, x2, y2)
        self.preview_canvas.configure(scrollregion=(0, 0, canvas_width, canvas_height))

    def _render_pdf_preview(self) -> None:
        self._cancel_after_callback("_pdf_preview_after_id")
        self._cancel_after_callback("_pdf_preview_render_after_id")
        canvas_width = max(self.preview_canvas.winfo_width(), 320)
        canvas_height = max(self.preview_canvas.winfo_height(), 240)
        self.preview_canvas.delete("all")
        self.preview_pdf_photos = [None] * len(self.preview_pdf_pages)
        self.preview_pdf_render_specs = []
        self.preview_pdf_page_positions = []
        y = 18
        max_content_width = canvas_width
        for index, page in enumerate(self.preview_pdf_pages):
            available_width = max(canvas_width - 56, 160)
            scale = min(1.0, available_width / max(page.width, 1))
            render_width = max(1, int(round(page.width * scale)))
            render_height = max(1, int(round(page.height * scale)))
            x = max(24, (canvas_width - render_width) // 2)
            self.preview_pdf_render_specs.append((page, x, y, render_width, render_height))
            self.preview_canvas.create_rectangle(
                x - 5,
                y - 5,
                x + render_width + 5,
                y + render_height + 5,
                fill="#dedcd6",
                outline="",
                tags=("pdf-page", f"pdf-page-{index}"),
            )
            self.preview_canvas.create_text(
                x + render_width // 2,
                y + render_height // 2,
                text=f"第 {index + 1} 页加载中",
                fill=MUTED,
                font=(self.ui_font_family, 10, "bold"),
                tags=("pdf-page", f"pdf-page-{index}", f"pdf-placeholder-{index}"),
            )
            self.preview_canvas.create_text(
                x + render_width,
                y + render_height + 10,
                text=f"{index + 1}/{len(self.preview_pdf_pages)}",
                anchor=tk.NE,
                fill=MUTED,
                font=(self.ui_font_family, 9, "bold"),
                tags=("pdf-page", f"pdf-page-{index}"),
            )
            self.preview_pdf_page_positions.append((x, y, x + render_width, y + render_height))
            y += render_height + 38
            max_content_width = max(max_content_width, x + render_width + 24)
        content_height = max(y, canvas_height)
        self.preview_transform = None
        self.preview_canvas.configure(scrollregion=(0, 0, max_content_width, content_height))
        self._render_visible_pdf_pages()

    def _schedule_visible_pdf_pages_render(self) -> None:
        if getattr(self, "_pdf_preview_render_after_id", None) is not None:
            self.root.after_cancel(self._pdf_preview_render_after_id)
        self._pdf_preview_render_after_id = self.root.after_idle(self._render_visible_pdf_pages)

    def _render_visible_pdf_pages(self) -> None:
        self._pdf_preview_render_after_id = None
        if not getattr(self, "preview_pdf_render_specs", []):
            return
        canvas = self.preview_canvas
        visible_top = canvas.canvasy(0)
        visible_bottom = visible_top + max(canvas.winfo_height(), 1)
        margin = 720
        for index, (page, x, y, render_width, render_height) in enumerate(self.preview_pdf_render_specs):
            page_bottom = y + render_height
            if page_bottom < visible_top - margin or y > visible_bottom + margin:
                continue
            if index < len(self.preview_pdf_photos) and self.preview_pdf_photos[index] is not None:
                continue
            render = page.copy()
            if render.size != (render_width, render_height):
                render = render.resize((render_width, render_height), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(render)
            self.preview_pdf_photos[index] = photo
            canvas.delete(f"pdf-placeholder-{index}")
            canvas.create_image(
                x,
                y,
                image=photo,
                anchor=tk.NW,
                tags=("pdf-page", f"pdf-page-{index}"),
            )

    def _draw_preview_placeholder(self, message: str) -> None:
        canvas_width = max(self.preview_canvas.winfo_width(), 320)
        canvas_height = max(self.preview_canvas.winfo_height(), 240)
        self.preview_canvas.delete("all")
        center_x = canvas_width // 2
        center_y = canvas_height // 2 - 62
        pixel = 4
        draw_pixel_dino(
            self.preview_canvas,
            center_x - 10 * pixel,
            center_y,
            pixel,
            eye_color=PAPER,
        )
        self.preview_canvas.create_text(
            canvas_width // 2,
            canvas_height // 2 + 45,
            text=message,
            fill=INK,
            width=max(canvas_width - 48, 200),
            justify=tk.CENTER,
            font=(self.ui_font_family, 11, "bold"),
        )

    def _pick_ui_font_family(self) -> str:
        available_families = set(tkfont.families(self.root))
        for family in self.UI_FONT_CANDIDATES:
            if family in available_families:
                return family
        return tkfont.nametofont("TkDefaultFont").actual("family")

    def _configure_fonts(self) -> None:
        """统一调整 Tkinter 默认字体，改善整体观感。"""

        default_font = tkfont.nametofont("TkDefaultFont")
        default_font.configure(family=self.ui_font_family, size=11)

        text_font = tkfont.nametofont("TkTextFont")
        text_font.configure(family=self.ui_font_family, size=11)

        fixed_font = tkfont.nametofont("TkFixedFont")
        fixed_font.configure(family=self.ui_font_family, size=11)

        heading_font = tkfont.nametofont("TkHeadingFont")
        heading_font.configure(family=self.ui_font_family, size=11, weight="bold")

    def _configure_result_icon_style(self) -> None:
        """Keep result toolbar icon cards free of extra native button chrome."""

        self.ui_style.configure(
            "ResultIcon.Pixel.TButton",
            background=PANEL,
            borderwidth=0,
            relief="flat",
            padding=0,
        )
        self.ui_style.map(
            "ResultIcon.Pixel.TButton",
            background=[("pressed", PANEL), ("active", PANEL), ("disabled", PANEL)],
            bordercolor=[("focus", PANEL), ("active", PANEL), ("disabled", PANEL)],
        )
        self.ui_style.configure(
            "PreviewIcon.Pixel.TButton",
            background=PANEL,
            borderwidth=0,
            relief="flat",
            padding=0,
            focuscolor=PANEL,
        )
        self.ui_style.map(
            "PreviewIcon.Pixel.TButton",
            background=[("pressed", PANEL), ("active", PANEL), ("focus", PANEL), ("disabled", PANEL)],
            bordercolor=[("focus", PANEL), ("active", PANEL), ("disabled", PANEL)],
            lightcolor=[("focus", PANEL), ("active", PANEL), ("disabled", PANEL)],
            darkcolor=[("focus", PANEL), ("active", PANEL), ("disabled", PANEL)],
        )

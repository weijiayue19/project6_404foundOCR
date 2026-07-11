"""历史 OCR 查询弹窗。"""

from __future__ import annotations

import calendar
import json
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageTk

from src.gui.history_constants import (
    DISPLAY_MODE_PLAIN,
    DISPLAY_MODE_LAYOUT,
    DISPLAY_MODE_VALUES,
    GALLERY_CARD_HEIGHT,
    GALLERY_CARD_WIDTH,
    GALLERY_PADDING,
    GALLERY_SCROLLBAR_GAP,
    MODE_FILTER_ALL,
    MODE_FILTER_VALUES,
    SORT_CUSTOM_RANGE,
    SORT_NEWEST_FIRST,
    SORT_OLDEST_FIRST,
    SORT_VALUES,
    TEXT_SOURCE_BEFORE,
    TEXT_SOURCE_VALUES,
    THUMBNAIL_SIZE,
    UPLOAD_FILTER_ALL,
    UPLOAD_FILTER_VALUES,
)
from src.gui.history_helpers import (
    build_history_day_bounds,
    format_history_date_range,
    format_history_result_count,
    history_mode_filter_value,
    history_upload_filter_value,
    select_history_detail_text,
)
from src.gui.history_preview_utils import (
    draw_region_overlay,
    fit_image,
    load_preview_image,
)
from src.gui.scroll_helpers import WheelBindingManager, scroll_canvas_by_wheel, scroll_text_by_wheel
from src.gui.pixel_theme import (
    GRID,
    INK,
    MUTED,
    PANEL,
    PAPER,
    SOFT,
    PixelBorderFrame,
    PixelScrollbar,
    CutCornerButton,
    draw_pixel_box,
    draw_pixel_dino,
)
from src.models.ocr_result import OcrResult, TextBlock
from src.search_manager import OCRSearchManager
from src.gui.window_utils import create_independent_window, focus_existing_window, show_centered_window


def open_history_search_window(
    parent: tk.Tk,
    ui_font_family: str,
    initial_display_mode: str = DISPLAY_MODE_PLAIN,
) -> tk.Toplevel:
    """打开历史查询窗口，查询逻辑委托给 OCRSearchManager。"""

    existing_window = getattr(parent, "_ocr_history_search_window", None)
    if focus_existing_window(existing_window):
        return existing_window
    window = create_independent_window("本地 OCR - 历史查询")
    setattr(parent, "_ocr_history_search_window", window)
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    width = min(1310, max(640, int(screen_width * 0.91)))
    height = min(819, max(520, int(screen_height * 0.91)))
    x = max(0, (screen_width - width) // 2)
    y = max(0, (screen_height - height) // 3)
    window.geometry(f"{width}x{height}+{x}+{y}")
    window.minsize(min(760, width), min(500, height))

    window.columnconfigure(0, weight=0, minsize=360)
    window.columnconfigure(1, weight=1)
    window.rowconfigure(1, weight=3)
    window.rowconfigure(2, weight=2)

    searcher = OCRSearchManager()
    keyword_var = tk.StringVar()
    candidates: list[dict[str, object]] = []
    gallery_photos: list[ImageTk.PhotoImage] = []
    gallery_photo_cache: dict[str, ImageTk.PhotoImage | None] = {}
    gallery_photo_failed_keys: set[str] = set()
    gallery_thumbnail_after_id: str | None = None
    gallery_render_after_id: str | None = None
    gallery_last_layout: tuple[int, int] | None = None
    gallery_scroll_idle_after_id: str | None = None
    preview_image_cache: dict[str, Image.Image | None] = {}
    gallery_bounds: list[tuple[int, int, int, int]] = []
    preview_photo: ImageTk.PhotoImage | None = None
    current_preview_image: Image.Image | None = None
    current_preview_record: dict[str, object] | None = None
    display_mode_var = tk.StringVar(
        value=initial_display_mode if initial_display_mode in DISPLAY_MODE_VALUES else DISPLAY_MODE_PLAIN
    )
    text_source_var = tk.StringVar(value=TEXT_SOURCE_BEFORE)
    upload_filter_var = tk.StringVar(value=UPLOAD_FILTER_ALL)
    sort_mode_var = tk.StringVar(value=SORT_NEWEST_FIRST)
    mode_filter_var = tk.StringVar(value=MODE_FILTER_ALL)
    result_count_var = tk.StringVar(value=format_history_result_count(0))
    date_range_start: str | None = None
    date_range_end: str | None = None
    last_regular_sort_mode = SORT_NEWEST_FIRST
    custom_range_newest_first = True
    detail_meta_var = tk.StringVar(value="选择记录后显示详情")
    current_detail_result: dict[str, object] | None = None
    selected_index = 0

    def close_window() -> None:
        wheel_manager.unbind()
        _cancel_gallery_thumbnail_generation()
        _cancel_gallery_render()
        window.withdraw()

    header = ttk.Frame(window, padding=(4, 5), style="App.TFrame")
    header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(16, 0))
    header.columnconfigure(3, weight=1)
    ttk.Button(
        header,
        text="←",
        width=3,
        command=close_window,
        style="Quiet.Pixel.TButton",
        takefocus=True,
    ).grid(row=0, column=0, sticky="w", padx=(0, 8))
    ttk.Label(
        header,
        text="HISTORY ARCHIVE",
        style="TLabel",
        font=(ui_font_family, 14, "bold"),
    ).grid(row=0, column=1, sticky="w")
    ttk.Label(header, text="本地 OCR 识别历史", style="Muted.TLabel").grid(
        row=0, column=2, sticky="w", padx=(18, 0)
    )

    search_box = PixelBorderFrame(header, padding=(10, 5), background=PANEL)
    search_box.grid(row=0, column=3, sticky="ew", padx=(18, 0))
    search_box.columnconfigure(1, weight=1)
    search_box.columnconfigure(2, weight=0)
    search_box.columnconfigure(3, weight=0)
    search_icon = tk.Canvas(
        search_box,
        width=20,
        height=20,
        background=PANEL,
        highlightthickness=0,
        borderwidth=0,
        cursor="hand2",
    )
    search_icon.grid(row=0, column=0, sticky="w", padx=(0, 4))
    search_icon.create_oval(4, 4, 13, 13, outline=MUTED, width=2)
    search_icon.create_line(12, 12, 18, 18, fill=MUTED, width=2)
    keyword_entry = ttk.Entry(
        search_box,
        textvariable=keyword_var,
        style="Search.Pixel.TEntry",
        font=(ui_font_family, 10),
    )
    keyword_entry.grid(row=0, column=1, sticky="ew", padx=(6, 8))
    upload_filter_box = ttk.Combobox(
        search_box,
        state="readonly",
        width=6,
        textvariable=upload_filter_var,
        values=UPLOAD_FILTER_VALUES,
        style="Pixel.TCombobox",
    )
    upload_filter_box.grid(row=0, column=2, sticky="e", padx=(0, 8))
    mode_filter_box = ttk.Combobox(
        search_box,
        state="readonly",
        width=10,
        textvariable=mode_filter_var,
        values=MODE_FILTER_VALUES,
        style="Pixel.TCombobox",
    )
    mode_filter_box.grid(row=0, column=3, sticky="e", padx=(0, 8))
    clear_search_button = tk.Label(
        search_box,
        text="×",
        background=PANEL,
        foreground=INK,
        cursor="hand2",
        font=(ui_font_family, 15, "bold"),
        padx=8,
    )
    clear_search_button.grid(row=0, column=4, sticky="e", padx=(4, 0))
    tk.Frame(window, height=1, background=GRID).grid(
        row=0, column=0, columnspan=2, sticky="sew", padx=18
    )

    gallery_frame = PixelBorderFrame(window, padding=GALLERY_PADDING)
    gallery_frame.grid(row=1, column=0, rowspan=2, sticky="nsew", padx=(18, 8), pady=(12, 16))
    gallery_frame.columnconfigure(0, weight=1)
    gallery_frame.rowconfigure(1, weight=1)
    gallery_header = ttk.Frame(gallery_frame, style="Panel.TFrame")
    gallery_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    gallery_header.columnconfigure(2, weight=1)
    history_title_button = CutCornerButton(
        gallery_header,
        text="历史记录",
        command=lambda: _open_history_manage_dialog(),
        variant="default",
        font_family=ui_font_family,
        outer_background=PANEL,
        min_width=92,
        min_height=34,
    )
    history_title_button.grid(row=0, column=0, sticky="w")
    ttk.Label(gallery_header, textvariable=result_count_var, style="PanelMuted.TLabel").grid(
        row=0,
        column=1,
        sticky="w",
        padx=(8, 0),
    )
    sort_mode_box = ttk.Combobox(
        gallery_header,
        state="readonly",
        width=10,
        textvariable=sort_mode_var,
        values=SORT_VALUES,
        style="Pixel.TCombobox",
    )
    sort_mode_box.grid(row=0, column=2, sticky="e")
    gallery_canvas = tk.Canvas(
        gallery_frame,
        background=PAPER,
        highlightthickness=0,
        cursor="hand2",
    )
    gallery_canvas.grid(row=1, column=0, sticky="nsew")
    gallery_scrollbar = PixelScrollbar(
        gallery_frame,
        orient=tk.VERTICAL,
        command=gallery_canvas.yview,
        background=PANEL,
        thumb_fill=SOFT,
        thumb_line=GRID,
        thumb_accent=INK,
        always_show_thumb=True,
    )
    gallery_scrollbar.grid(row=1, column=1, sticky="ns", padx=(GALLERY_SCROLLBAR_GAP, 0))
    gallery_canvas.configure(yscrollcommand=gallery_scrollbar.set)

    preview_frame = PixelBorderFrame(window, padding=12)
    preview_frame.grid(row=1, column=1, sticky="nsew", padx=(0, 18), pady=(12, 8))
    preview_frame.columnconfigure(0, weight=1)
    preview_frame.rowconfigure(1, weight=1)
    ttk.Label(preview_frame, text="文件预览", style="PanelTitle.TLabel").grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )
    preview_canvas = tk.Canvas(
        preview_frame,
        background=PANEL,
        highlightthickness=0,
        borderwidth=0,
        yscrollincrement=1,
    )
    preview_canvas.grid(row=1, column=0, sticky="nsew")
    preview_scrollbar = PixelScrollbar(
        preview_frame,
        orient=tk.VERTICAL,
        command=preview_canvas.yview,
        background=PANEL,
        always_show_thumb=True,
    )
    preview_scrollbar.grid(row=1, column=1, sticky="ns")
    preview_canvas.configure(yscrollcommand=preview_scrollbar.set)
    preview_label = ttk.Label(
        preview_canvas,
        text="选择一张历史图片查看详情",
        anchor=tk.CENTER,
        style="PanelMuted.TLabel",
    )
    preview_canvas_window = preview_canvas.create_window((0, 0), window=preview_label, anchor="nw")

    detail_frame = PixelBorderFrame(window, padding=12)
    detail_frame.grid(row=2, column=1, sticky="nsew", padx=(0, 18), pady=(0, 16))
    detail_frame.columnconfigure(0, weight=1)
    detail_frame.rowconfigure(2, weight=1)
    ttk.Label(detail_frame, text="识别文本", style="PanelTitle.TLabel").grid(
        row=0, column=0, columnspan=2, sticky="w", pady=(0, 10)
    )
    detail_toolbar = ttk.Frame(detail_frame, style="Panel.TFrame")
    detail_toolbar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
    detail_toolbar.columnconfigure(4, weight=1)
    ttk.Label(detail_toolbar, text="显示方式", style="PanelMuted.TLabel").grid(
        row=0, column=0, sticky="w", padx=(0, 6)
    )
    display_mode_box = ttk.Combobox(
        detail_toolbar,
        state="readonly",
        width=12,
        textvariable=display_mode_var,
        values=DISPLAY_MODE_VALUES,
        style="Pixel.TCombobox",
    )
    display_mode_box.grid(row=0, column=1, sticky="w")
    ttk.Label(detail_toolbar, text="文本版本", style="PanelMuted.TLabel").grid(
        row=0, column=2, sticky="w", padx=(12, 6)
    )
    text_source_box = ttk.Combobox(
        detail_toolbar,
        state="readonly",
        width=8,
        textvariable=text_source_var,
        values=TEXT_SOURCE_VALUES,
        style="Pixel.TCombobox",
    )
    text_source_box.grid(row=0, column=3, sticky="w")
    ttk.Label(
        detail_toolbar,
        textvariable=detail_meta_var,
        style="PanelMuted.TLabel",
        anchor=tk.E,
    ).grid(row=0, column=4, sticky="e", padx=(12, 0))
    detail_text_frame = PixelBorderFrame(detail_frame, padding=6, background=PANEL)
    detail_text_frame.grid(row=2, column=0, columnspan=2, sticky="nsew")
    detail_text_frame.columnconfigure(0, weight=1)
    detail_text_frame.rowconfigure(0, weight=1)
    detail_text = tk.Text(
        detail_text_frame,
        wrap=tk.WORD,
        font=(ui_font_family, 10),
        height=7,
        background=PANEL,
        foreground=INK,
        insertbackground=INK,
        selectbackground=INK,
        selectforeground=PANEL,
        relief=tk.FLAT,
        borderwidth=0,
        highlightthickness=0,
        padx=14,
        pady=12,
        spacing1=2,
        spacing3=4,
    )
    detail_text.grid(row=0, column=0, sticky="nsew")
    detail_scrollbar = PixelScrollbar(
        detail_text_frame,
        orient=tk.VERTICAL,
        command=detail_text.yview,
        background=PANEL,
    )
    detail_scrollbar.grid(row=0, column=1, sticky="ns")
    detail_text.configure(yscrollcommand=detail_scrollbar.set)

    def run_search() -> None:
        load_candidates(keyword_var.get())

    def _newest_first() -> bool:
        if sort_mode_var.get() == SORT_CUSTOM_RANGE:
            return custom_range_newest_first
        return sort_mode_var.get() != SORT_OLDEST_FIRST

    def clear_search() -> None:
        keyword_var.set("")
        load_candidates("")
        window.focus_set()

    def load_candidates(keyword: str, preserve_record_id: str | None = None) -> None:
        nonlocal candidates, selected_index, current_detail_result
        _cancel_gallery_thumbnail_generation()
        selected_index = 0
        current_detail_result = None
        detail_meta_var.set("选择记录后显示详情")
        gallery_photo_cache.clear()
        gallery_photo_failed_keys.clear()
        preview_image_cache.clear()
        detail_text.delete("1.0", tk.END)
        _set_preview_placeholder("选择一张历史图片查看详情")
        try:
            candidates = searcher.search_records(
                keyword=keyword,
                recognition_mode=history_mode_filter_value(mode_filter_var.get()),
                upload_type=history_upload_filter_value(upload_filter_var.get()),
                start_time=date_range_start,
                end_time=date_range_end,
                newest_first=_newest_first(),
            )
        except Exception as exc:  # noqa: BLE001 - GUI must surface failures to users.
            messagebox.showerror("查询失败", str(exc), parent=window)
            candidates = []
        result_count_var.set(format_history_result_count(len(candidates)))
        _render_gallery()
        if candidates:
            target_index = 0
            if preserve_record_id:
                for index, record in enumerate(candidates):
                    if str(record.get("record_id", "")) == preserve_record_id:
                        target_index = index
                        break
            select_candidate(target_index)
        else:
            if date_range_start and date_range_end:
                message = "该时间范围内没有历史图片"
            else:
                message = "还没有识别历史" if not keyword.strip() else "没有找到匹配图片"
            _set_preview_placeholder(message)
            detail_text.delete("1.0", tk.END)

    def _current_selected_record_id() -> str | None:
        if 0 <= selected_index < len(candidates):
            record_id = str(candidates[selected_index].get("record_id") or "").strip()
            return record_id or None
        return None

    def _schedule_gallery_render(delay_ms: int = 16) -> None:
        nonlocal gallery_render_after_id
        if gallery_render_after_id is not None:
            return
        gallery_render_after_id = window.after(delay_ms, _run_scheduled_gallery_render)

    def _run_scheduled_gallery_render() -> None:
        nonlocal gallery_render_after_id
        gallery_render_after_id = None
        if window.winfo_exists() and gallery_canvas.winfo_exists():
            _render_gallery()

    def _cancel_gallery_render() -> None:
        nonlocal gallery_render_after_id, gallery_scroll_idle_after_id
        for after_id in (gallery_render_after_id, gallery_scroll_idle_after_id):
            if after_id is None:
                continue
            try:
                window.after_cancel(after_id)
            except tk.TclError:
                pass
        gallery_render_after_id = None
        gallery_scroll_idle_after_id = None

    def _render_gallery() -> None:
        nonlocal gallery_last_layout
        current_yview = gallery_canvas.yview()[0]
        gallery_canvas.delete("all")
        gallery_photos.clear()
        gallery_bounds.clear()
        needs_thumbnail_generation = False
        if not candidates:
            _cancel_gallery_thumbnail_generation()
            gallery_canvas.create_text(
                18,
                66,
                anchor=tk.W,
                text="暂无历史图片" if not keyword_var.get().strip() else "没有匹配的历史图片",
                fill=MUTED,
                font=(ui_font_family, 10, "bold"),
            )
            draw_pixel_dino(gallery_canvas, 18, 18, 2, foreground=INK, eye_color=PAPER)
            gallery_canvas.configure(scrollregion=(0, 0, 360, 120))
            gallery_last_layout = (0, 360)
            return

        card_width = GALLERY_CARD_WIDTH
        card_height = GALLERY_CARD_HEIGHT
        gap = 10
        padding = GALLERY_PADDING
        canvas_width = max(gallery_canvas.winfo_width(), card_width + padding * 2 + 8)
        available_width = max(canvas_width - padding * 2, card_width)
        columns = max(1, (available_width + gap) // (card_width + gap))
        columns = min(columns, max(len(candidates), 1))
        grid_width = columns * card_width + (columns - 1) * gap
        start_x = max(padding, (canvas_width - grid_width) // 2)

        for index, item in enumerate(candidates):
            row = index // columns
            column = index % columns
            x1 = start_x + column * (card_width + gap)
            y1 = padding + row * (card_height + gap)
            x2 = x1 + card_width
            y2 = y1 + card_height
            gallery_bounds.append((x1, y1, x2, y2))
            selected = index == selected_index
            draw_pixel_box(
                gallery_canvas,
                x1,
                y1,
                x2,
                y2,
                fill=SOFT if selected else PANEL,
                line_color=INK if selected else GRID,
                accent_color=INK if selected else MUTED,
                width=3 if selected else 2,
                tag=f"history-card-{index}",
                pixel=4,
            )
            key = _gallery_record_key(index, item)
            photo = gallery_photo_cache.get(key)
            if photo is not None:
                gallery_photos.append(photo)
                gallery_canvas.create_image(x1 + card_width // 2, y1 + card_height // 2, image=photo)
            else:
                failed = key in gallery_photo_cache or key in gallery_photo_failed_keys
                if not failed:
                    needs_thumbnail_generation = True
                gallery_canvas.create_text(
                    x1 + card_width // 2,
                    y1 + card_height // 2,
                    text="NO PREVIEW / 无预览" if failed else "LOADING / 加载中",
                    fill=MUTED,
                    font=(ui_font_family, 8, "bold"),
                )

            gallery_canvas.create_line(x1 + 8, y2 - 4, x2 - 8, y2 - 4, fill=GRID)

        total_rows = (len(candidates) + columns - 1) // columns
        content_height = padding + total_rows * (card_height + gap)
        content_width = padding * 2 + grid_width
        scrollregion = (0, 0, max(content_width, canvas_width), max(content_height, gallery_canvas.winfo_height()))
        gallery_canvas.configure(scrollregion=scrollregion)
        gallery_last_layout = (columns, canvas_width)
        visible_height = max(float(gallery_canvas.winfo_height()), 1.0)
        scrollable_height = max(float(scrollregion[3]) - visible_height, 1.0)
        target_yview = min(current_yview, max(0.0, scrollable_height / float(scrollregion[3])))
        if target_yview > 0.0:
            gallery_canvas.yview_moveto(target_yview)
        if needs_thumbnail_generation:
            _schedule_gallery_thumbnail_generation()

    def _gallery_record_key(index: int, record: dict[str, object]) -> str:
        return str(record.get("record_id") or record.get("saved_image_path") or index)

    def _schedule_gallery_thumbnail_generation() -> None:
        nonlocal gallery_thumbnail_after_id
        if gallery_thumbnail_after_id is not None:
            return
        gallery_thumbnail_after_id = window.after(10, _generate_next_gallery_thumbnail)

    def _delay_gallery_thumbnail_generation() -> None:
        nonlocal gallery_thumbnail_after_id
        if gallery_thumbnail_after_id is not None:
            try:
                window.after_cancel(gallery_thumbnail_after_id)
            except tk.TclError:
                pass
        gallery_thumbnail_after_id = window.after(120, _generate_next_gallery_thumbnail)

    def _cancel_gallery_thumbnail_generation() -> None:
        nonlocal gallery_thumbnail_after_id
        if gallery_thumbnail_after_id is None:
            return
        try:
            window.after_cancel(gallery_thumbnail_after_id)
        except tk.TclError:
            pass
        gallery_thumbnail_after_id = None

    def _generate_next_gallery_thumbnail() -> None:
        nonlocal gallery_thumbnail_after_id
        gallery_thumbnail_after_id = None
        if not window.winfo_exists() or not gallery_canvas.winfo_exists():
            return

        target: tuple[int, dict[str, object], str] | None = None
        for index, item in enumerate(candidates):
            key = _gallery_record_key(index, item)
            if key not in gallery_photo_cache and key not in gallery_photo_failed_keys:
                target = (index, item, key)
                break
        if target is None:
            return

        index, item, key = target
        try:
            photo = _thumbnail_photo_for(index, item)
        except (OSError, ValueError):
            photo = None
        if photo is None:
            gallery_photo_cache[key] = None
            gallery_photo_failed_keys.add(key)
        else:
            gallery_photo_cache[key] = photo
        _schedule_gallery_render(60)
        _schedule_gallery_thumbnail_generation()

    def _thumbnail_photo_for(index: int, record: dict[str, object]) -> ImageTk.PhotoImage | None:
        key = _gallery_record_key(index, record)
        if key in gallery_photo_cache:
            return gallery_photo_cache[key]
        image = load_preview_image(record, preview_image_cache, prefer_file=False)
        if image is None:
            gallery_photo_cache[key] = None
            return None
        image = fit_image(image, THUMBNAIL_SIZE, allow_upscale=True)
        image = draw_region_overlay(image, record)
        photo = ImageTk.PhotoImage(image)
        gallery_photo_cache[key] = photo
        return photo

    def select_candidate(index: int) -> None:
        nonlocal selected_index, current_detail_result
        if not (0 <= index < len(candidates)):
            return
        selected_index = index
        _render_gallery()
        record_id = str(candidates[index].get("record_id", ""))
        try:
            full_result = searcher.get_full_result(record_id)
        except Exception as exc:  # noqa: BLE001 - GUI must surface failures to users.
            messagebox.showerror("读取失败", str(exc), parent=window)
            return
        current_detail_result = full_result
        name = str(full_result.get("image_name") or "未知图片")
        if len(name) > 32:
            name = f"{name[:29]}…"
        width = int(full_result.get("image_width", 0) or 0)
        height = int(full_result.get("image_height", 0) or 0)
        created = str(full_result.get("created_time", "")).replace("T", " ")[:16]
        size_note = f"{width}×{height}" if width and height else "尺寸未知"
        id_note = _history_id_label(full_result)
        detail_meta_var.set(f"{name}  ·  {id_note}  ·  {size_note}  ·  {created or '时间未知'}")
        _render_detail_text()
        _show_preview(full_result)

    def _history_id_label(record: dict[str, object], *, fallback: str = "ID UNKNOWN") -> str:
        record_id = str(record.get("record_id") or "").strip()
        if not record_id:
            return fallback
        return f"ID {record_id[:8].upper()}"

    def _render_detail_text() -> None:
        detail_text.delete("1.0", tk.END)
        if current_detail_result is None:
            return
        text = select_history_detail_text(
            current_detail_result,
            display_mode_var.get(),
            text_source_var.get(),
        )
        if (
            text_source_var.get() == TEXT_SOURCE_BEFORE
            and display_mode_var.get() == DISPLAY_MODE_LAYOUT
            and text == str(current_detail_result.get("recognized_text", ""))
        ):
            text = _render_layout_from_blocks(current_detail_result) or text
        detail_text.insert("1.0", text)

    def _render_layout_from_blocks(record: dict[str, object]) -> str:
        raw_blocks = record.get("ocr_blocks")
        metadata = record.get("metadata")
        if not raw_blocks and isinstance(metadata, dict):
            raw_blocks = metadata.get("ocr_blocks")
        if not raw_blocks:
            return ""
        try:
            data = json.loads(str(raw_blocks)) if isinstance(raw_blocks, str) else raw_blocks
        except json.JSONDecodeError:
            return ""
        if not isinstance(data, list):
            return ""
        blocks: list[TextBlock] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            blocks.append(
                TextBlock(
                    text=str(item.get("text", "")),
                    confidence=float(item.get("confidence", 0.0)),
                    box=item.get("box", []),
                )
            )
        if not blocks:
            return ""
        image_path = Path(str(record.get("image_path") or record.get("saved_image_path") or ""))
        return OcrResult(image_path=image_path, elapsed_seconds=0.0, blocks=blocks).render_text("layout")

    def _on_display_mode_change(_event: tk.Event | None = None) -> None:
        _render_detail_text()

    def _on_text_source_change(_event: tk.Event | None = None) -> None:
        _render_detail_text()

    def _on_gallery_click(event: tk.Event) -> str:
        x = gallery_canvas.canvasx(event.x)
        y = gallery_canvas.canvasy(event.y)
        for index, (x1, y1, x2, y2) in enumerate(gallery_bounds):
            if x1 <= x <= x2 and y1 <= y <= y2:
                select_candidate(index)
                break
        return "break"

    def _set_preview_placeholder(message: str) -> None:
        nonlocal preview_photo, current_preview_image, current_preview_record
        preview_photo = None
        current_preview_image = None
        current_preview_record = None
        preview_label.configure(image="", text=message)
        _sync_preview_scrollregion()

    def _show_preview(record: dict[str, object]) -> None:
        nonlocal current_preview_image, current_preview_record
        current_preview_record = record
        try:
            current_preview_image = load_preview_image(record, preview_image_cache, prefer_file=True)
            if current_preview_image is None:
                current_preview_image = load_preview_image(record, preview_image_cache, prefer_file=False)
        except Exception as exc:  # noqa: BLE001 - preview failure should not block text display.
            _set_preview_placeholder(f"图片预览失败：{exc}")
            return
        if current_preview_image is None:
            _set_preview_placeholder("没有可用的图片预览")
            return
        _render_preview_image()

    def _sync_preview_scrollregion(_event: tk.Event | None = None) -> None:
        canvas_width = max(preview_canvas.winfo_width(), 1)
        canvas_height = max(preview_canvas.winfo_height(), 1)
        label_width = max(preview_label.winfo_reqwidth(), canvas_width)
        label_height = max(preview_label.winfo_reqheight(), canvas_height)
        preview_canvas.itemconfigure(preview_canvas_window, width=label_width, height=label_height)
        preview_canvas.configure(scrollregion=(0, 0, label_width, label_height))

    def _render_preview_image() -> None:
        nonlocal preview_photo
        if current_preview_image is None:
            _sync_preview_scrollregion()
            return
        width = max(preview_canvas.winfo_width(), 320)
        height = max(preview_canvas.winfo_height(), 220)
        image = fit_image(current_preview_image, (max(width - 12, 1), max(height - 12, 1)), allow_upscale=True)
        if current_preview_record is not None:
            image = draw_region_overlay(image, current_preview_record)
        preview_photo = ImageTk.PhotoImage(image)
        preview_label.configure(image=preview_photo, text="")
        _sync_preview_scrollregion()

    def _open_date_range_dialog() -> bool:
        nonlocal date_range_start, date_range_end, custom_range_newest_first

        def history_date_bounds() -> tuple[date, date]:
            records = searcher.search_records(keyword="", newest_first=False)
            dates: list[date] = []
            for record in records:
                created_time = str(record.get("created_time") or "")[:10]
                if not created_time:
                    continue
                try:
                    dates.append(date.fromisoformat(created_time))
                except ValueError:
                    continue
            if not dates:
                today_value = date.today()
                return today_value, today_value
            return min(dates), max(dates)

        today = date.today()
        earliest_day, latest_day = history_date_bounds()
        if date_range_start and date_range_end:
            start_default = date.fromisoformat(date_range_start[:10])
            end_default = date.fromisoformat(date_range_end[:10])
        else:
            start_default = earliest_day
            end_default = latest_day

        dialog = getattr(window, "_ocr_date_range_window", None)
        controls: dict[str, object]
        if dialog is None or not focus_existing_window(dialog):
            dialog = create_independent_window("自定义搜索范围", resizable=False)
            setattr(window, "_ocr_date_range_window", dialog)
            controls = {}
            setattr(dialog, "_history_date_controls", controls)

            body = PixelBorderFrame(dialog, padding=14, background=PANEL)
            body.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
            ttk.Label(body, text="选择历史记录时间范围", style="PanelTitle.TLabel").grid(
                row=0,
                column=0,
                columnspan=6,
                sticky="w",
                pady=(0, 12),
            )
            years = tuple(str(year) for year in range(today.year - 10, today.year + 2))
            months = tuple(f"{month:02d}" for month in range(1, 13))

            def make_date_row(
                row: int,
                title: str,
                initial: date,
            ) -> tuple[tk.StringVar, tk.StringVar, tk.StringVar, object]:
                year_var = tk.StringVar(value=str(initial.year))
                month_var = tk.StringVar(value=f"{initial.month:02d}")
                day_var = tk.StringVar(value=f"{initial.day:02d}")
                ttk.Label(body, text=title, style="PanelMuted.TLabel").grid(row=row, column=0, sticky="w", pady=6)
                year_box = ttk.Combobox(
                    body,
                    textvariable=year_var,
                    values=years,
                    width=6,
                    state="readonly",
                    style="Pixel.TCombobox",
                )
                year_box.grid(row=row, column=1, padx=(8, 4))
                ttk.Label(body, text="年", style="PanelMuted.TLabel").grid(row=row, column=2)
                month_box = ttk.Combobox(body, textvariable=month_var, values=months, width=4, state="readonly", style="Pixel.TCombobox")
                month_box.grid(row=row, column=3, padx=(8, 4))
                ttk.Label(body, text="月", style="PanelMuted.TLabel").grid(row=row, column=4)
                day_box = ttk.Combobox(body, textvariable=day_var, width=4, state="readonly", style="Pixel.TCombobox")
                day_box.grid(row=row, column=5, padx=(8, 4))

                def refresh_days(_event: tk.Event | None = None) -> None:
                    day_count = calendar.monthrange(int(year_var.get()), int(month_var.get()))[1]
                    values = tuple(f"{day:02d}" for day in range(1, day_count + 1))
                    day_box.configure(values=values)
                    if int(day_var.get()) > day_count:
                        day_var.set(f"{day_count:02d}")

                refresh_days()
                month_box.bind("<<ComboboxSelected>>", refresh_days)
                year_box.bind("<<ComboboxSelected>>", refresh_days)
                return year_var, month_var, day_var, refresh_days

            start_vars = make_date_row(1, "开始时间", start_default)
            end_vars = make_date_row(2, "结束时间", end_default)

            range_note = tk.StringVar(value=format_history_date_range(date_range_start, date_range_end) or "选择后将按整天范围搜索")
            ttk.Label(body, textvariable=range_note, style="PanelMuted.TLabel").grid(
                row=3,
                column=0,
                columnspan=6,
                sticky="w",
                pady=(12, 0),
            )
            order_newest_first = tk.BooleanVar(value=custom_range_newest_first)
            done_var = tk.IntVar(value=0)
            controls.update({
                "start_vars": start_vars,
                "end_vars": end_vars,
                "range_note": range_note,
                "order_newest_first": order_newest_first,
                "done_var": done_var,
                "result": None,
                "earliest_day": earliest_day,
                "latest_day": latest_day,
            })

            def draw_order_option(canvas: tk.Canvas, *, selected: bool, text: str) -> None:
                canvas.delete("all")
                fill = "#fffdf7" if selected else "#f7f6f1"
                outline = INK if selected else GRID
                canvas.create_rectangle(3, 4, 113, 33, fill="#e6e4dd", outline="")
                canvas.create_rectangle(0, 0, 110, 29, fill=fill, outline=outline, width=2 if selected else 1)
                canvas.create_rectangle(10, 7, 26, 23, fill=PANEL, outline=INK, width=1)
                if selected:
                    canvas.create_line(
                        13,
                        15,
                        17,
                        20,
                        25,
                        10,
                        fill=INK,
                        width=3,
                        smooth=False,
                        joinstyle=tk.ROUND,
                        capstyle=tk.ROUND,
                    )
                canvas.create_text(38, 15, text=text, fill=INK, anchor=tk.W, font=(ui_font_family, 10, "bold"))

            order_row = ttk.Frame(body, style="Panel.TFrame")
            order_row.grid(row=4, column=0, columnspan=6, sticky="w", pady=(12, 0))
            ttk.Label(order_row, text="时间顺序", style="PanelMuted.TLabel").pack(side=tk.LEFT, padx=(0, 8))
            ascending_option = tk.Canvas(order_row, width=114, height=34, background=PANEL, highlightthickness=0, cursor="hand2")
            descending_option = tk.Canvas(order_row, width=114, height=34, background=PANEL, highlightthickness=0, cursor="hand2")
            ascending_option.pack(side=tk.LEFT, padx=(0, 8))
            descending_option.pack(side=tk.LEFT)

            def refresh_order_options() -> None:
                draw_order_option(ascending_option, selected=not order_newest_first.get(), text="递增")
                draw_order_option(descending_option, selected=order_newest_first.get(), text="递减")

            def choose_order(newest_first: bool) -> None:
                order_newest_first.set(newest_first)
                refresh_order_options()

            ascending_option.bind("<Button-1>", lambda _event: choose_order(False))
            descending_option.bind("<Button-1>", lambda _event: choose_order(True))
            refresh_order_options()

            def set_date(parts: tuple[tk.StringVar, tk.StringVar, tk.StringVar, object], value: date) -> None:
                parts[0].set(str(value.year))
                parts[1].set(f"{value.month:02d}")
                refresh_days = parts[3]
                if callable(refresh_days):
                    refresh_days()
                parts[2].set(f"{value.day:02d}")

            def read_date(parts: tuple[tk.StringVar, tk.StringVar, tk.StringVar, object]) -> date:
                return date(int(parts[0].get()), int(parts[1].get()), int(parts[2].get()))

            def finish(value: tuple[str | None, str | None] | None) -> None:
                controls["result"] = value
                dialog.withdraw()
                done_var.set(done_var.get() + 1)

            def confirm() -> None:
                nonlocal custom_range_newest_first
                try:
                    value = build_history_day_bounds(read_date(start_vars), read_date(end_vars))
                except ValueError as exc:
                    messagebox.showerror("时间范围无效", str(exc), parent=dialog)
                    return
                custom_range_newest_first = order_newest_first.get()
                finish(value)

            def clear_range() -> None:
                current_earliest = controls["earliest_day"]
                current_latest = controls["latest_day"]
                if not isinstance(current_earliest, date) or not isinstance(current_latest, date):
                    return
                set_date(start_vars, current_earliest)
                set_date(end_vars, current_latest)
                range_note.set(format_history_date_range(
                    f"{current_earliest.isoformat()}T00:00:00",
                    f"{current_latest.isoformat()}T23:59:59",
                ))

            controls["set_date"] = set_date
            controls["refresh_order_options"] = refresh_order_options

            button_row = ttk.Frame(body, style="Panel.TFrame")
            button_row.grid(row=5, column=0, columnspan=6, sticky="e", pady=(18, 0))
            CutCornerButton(
                button_row,
                text="清除范围",
                command=clear_range,
                variant="default",
                font_family=ui_font_family,
                outer_background=PANEL,
            ).pack(side=tk.LEFT, padx=(0, 8))
            CutCornerButton(
                button_row,
                text="取消",
                command=lambda: finish(None),
                variant="default",
                font_family=ui_font_family,
                outer_background=PANEL,
            ).pack(side=tk.LEFT, padx=(0, 8))
            CutCornerButton(
                button_row,
                text="确定",
                command=confirm,
                variant="primary",
                font_family=ui_font_family,
                outer_background=PANEL,
            ).pack(side=tk.LEFT)
            dialog.protocol("WM_DELETE_WINDOW", lambda: finish(None))
        else:
            controls = getattr(dialog, "_history_date_controls", {})

        controls["earliest_day"] = earliest_day
        controls["latest_day"] = latest_day
        controls["result"] = None
        done_var = controls.get("done_var")
        if isinstance(done_var, tk.IntVar):
            done_var.set(0)
        set_date = controls.get("set_date")
        start_vars = controls.get("start_vars")
        end_vars = controls.get("end_vars")
        if callable(set_date) and isinstance(start_vars, tuple) and isinstance(end_vars, tuple):
            set_date(start_vars, start_default)
            set_date(end_vars, end_default)
        range_note = controls.get("range_note")
        if isinstance(range_note, tk.StringVar):
            range_note.set(format_history_date_range(date_range_start, date_range_end) or "选择后将按整天范围搜索")
        order_newest_first = controls.get("order_newest_first")
        if isinstance(order_newest_first, tk.BooleanVar):
            order_newest_first.set(custom_range_newest_first)
        refresh_order_options = controls.get("refresh_order_options")
        if callable(refresh_order_options):
            refresh_order_options()

        show_centered_window(dialog, window)
        if isinstance(done_var, tk.IntVar):
            dialog.wait_variable(done_var)
        result_value = controls.get("result")
        if result_value is None:
            return False
        date_range_start, date_range_end = result_value
        return True

    def _on_sort_mode_change(_event: tk.Event | None = None) -> None:
        nonlocal date_range_start, date_range_end, last_regular_sort_mode
        selected = sort_mode_var.get()
        if selected == SORT_CUSTOM_RANGE:
            if _open_date_range_dialog():
                run_search()
            else:
                sort_mode_var.set(last_regular_sort_mode)
            return
        last_regular_sort_mode = selected
        date_range_start = None
        date_range_end = None
        run_search()

    def _mode_text(record: dict[str, object]) -> str:
        return "深度识别" if record.get("recognition_mode") == "document" else "快速识别"

    wheel_manager = WheelBindingManager()

    def _open_history_manage_dialog() -> None:
        existing_manage = getattr(window, "_ocr_history_manage_window", None)
        if focus_existing_window(existing_manage):
            return
        manage = create_independent_window("历史记录编辑")
        setattr(window, "_ocr_history_manage_window", manage)
        manage.columnconfigure(0, weight=1)
        manage.rowconfigure(1, weight=1)

        all_records = searcher.search_records(keyword="", newest_first=True)
        selected_ids: set[str] = set()
        edit_mode = tk.BooleanVar(value=False)
        count_var = tk.StringVar(value=format_history_result_count(len(all_records)))
        checkbox_vars: dict[str, tk.BooleanVar] = {}
        manage_thumbnail_refs: list[ImageTk.PhotoImage] = []

        header_frame = PixelBorderFrame(manage, padding=12, background=PANEL)
        header_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        header_frame.columnconfigure(1, weight=1)
        ttk.Label(header_frame, text="历史记录", style="PanelTitle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(header_frame, textvariable=count_var, style="PanelMuted.TLabel").grid(row=0, column=1, sticky="w", padx=(10, 0))
        toolbar = ttk.Frame(header_frame, style="Panel.TFrame")
        toolbar.grid(row=0, column=2, sticky="e")

        body_frame = PixelBorderFrame(manage, padding=8, background=PANEL)
        body_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        body_frame.columnconfigure(0, weight=1)
        body_frame.rowconfigure(0, weight=1)
        list_canvas = tk.Canvas(body_frame, background=PANEL, highlightthickness=0)
        list_canvas.grid(row=0, column=0, sticky="nsew")
        list_scroll = PixelScrollbar(body_frame, orient=tk.VERTICAL, command=list_canvas.yview, background=PANEL)
        list_scroll.grid(row=0, column=1, sticky="ns")
        list_canvas.configure(yscrollcommand=list_scroll.set)
        rows_frame = ttk.Frame(list_canvas, style="Panel.TFrame")
        list_window = list_canvas.create_window((0, 0), window=rows_frame, anchor="nw")

        def update_scrollregion(_event: tk.Event | None = None) -> None:
            list_canvas.configure(scrollregion=list_canvas.bbox("all"))
            list_canvas.itemconfigure(list_window, width=max(list_canvas.winfo_width(), 1))

        rows_frame.bind("<Configure>", update_scrollregion)
        list_canvas.bind("<Configure>", update_scrollregion)

        def draw_history_checkbox(master: tk.Misc, variable: tk.BooleanVar, command: object) -> tk.Canvas:
            canvas = tk.Canvas(
                master,
                width=22,
                height=22,
                background=PANEL,
                highlightthickness=0,
                borderwidth=0,
                cursor="hand2",
            )

            def redraw() -> None:
                canvas.delete("all")
                canvas.create_rectangle(3, 3, 19, 19, fill=PANEL, outline=INK, width=1)
                if variable.get():
                    canvas.create_line(
                        6,
                        12,
                        10,
                        16,
                        17,
                        6,
                        fill=INK,
                        width=3,
                        smooth=False,
                        joinstyle=tk.ROUND,
                        capstyle=tk.ROUND,
                    )

            def toggle(_event: tk.Event | None = None) -> str:
                variable.set(not variable.get())
                redraw()
                if callable(command):
                    command()
                return "break"

            canvas.bind("<Button-1>", toggle)
            canvas.bind("<space>", toggle)
            canvas.bind("<Return>", toggle)
            redraw()
            return canvas

        def refresh_toolbar() -> None:
            if edit_mode.get():
                edit_button.pack_forget()
                finish_button.pack(side=tk.LEFT, padx=(0, 6))
                select_all_button.pack(side=tk.LEFT, padx=(0, 6))
                clear_selected_button.pack(side=tk.LEFT, padx=(0, 6))
                delete_button.pack(side=tk.LEFT, padx=(0, 6))
                close_button.pack(side=tk.LEFT)
            else:
                for button in (finish_button, select_all_button, clear_selected_button, delete_button, close_button):
                    button.pack_forget()
                edit_button.pack(side=tk.LEFT)

        def refresh_rows() -> None:
            manage_thumbnail_refs.clear()
            for child in rows_frame.winfo_children():
                child.destroy()
            checkbox_vars.clear()
            if not all_records:
                ttk.Label(rows_frame, text="暂无历史记录", style="PanelMuted.TLabel").grid(row=0, column=0, sticky="w", padx=10, pady=16)
                refresh_toolbar()
                return
            for row, record in enumerate(all_records):
                record_id = str(record.get("record_id") or "")
                row_frame = ttk.Frame(rows_frame, style="Panel.TFrame", padding=(4, 7))
                row_frame.grid(row=row * 2, column=0, sticky="ew")
                row_frame.columnconfigure(2, weight=1)
                var = tk.BooleanVar(value=record_id in selected_ids)
                checkbox_vars[record_id] = var

                def update_selection(rid: str = record_id, selected_var: tk.BooleanVar = var) -> None:
                    if selected_var.get():
                        selected_ids.add(rid)
                    else:
                        selected_ids.discard(rid)
                    refresh_toolbar()

                if edit_mode.get():
                    draw_history_checkbox(row_frame, var, update_selection).grid(
                        row=0,
                        column=0,
                        sticky="w",
                        padx=(0, 8),
                    )
                preview = load_preview_image(record, preview_image_cache, prefer_file=False)
                if preview is not None:
                    thumb = fit_image(preview, (68, 48), allow_upscale=True)
                    photo = ImageTk.PhotoImage(thumb)
                    manage_thumbnail_refs.append(photo)
                    ttk.Label(row_frame, image=photo, style="Panel.TLabel").grid(row=0, column=1, sticky="w", padx=(0, 8))
                else:
                    ttk.Label(row_frame, text="无预览", style="PanelMuted.TLabel", width=8).grid(row=0, column=1, sticky="w", padx=(0, 8))
                name = str(record.get("image_name") or "未知图片")
                ttk.Label(row_frame, text=name, style="TLabel").grid(row=0, column=2, sticky="w", padx=(8, 8))
                created = str(record.get("created_time", "")).replace("T", " ")[:16]
                ttk.Label(row_frame, text=f"{_mode_text(record)} · {created or '时间未知'}", style="PanelMuted.TLabel").grid(row=0, column=3, sticky="e")
                tk.Frame(rows_frame, height=1, background=GRID).grid(row=row * 2 + 1, column=0, sticky="ew", pady=(0, 0))
            update_scrollregion()
            refresh_toolbar()

        def toggle_edit() -> None:
            edit_mode.set(not edit_mode.get())
            if not edit_mode.get():
                selected_ids.clear()
            refresh_rows()

        def select_all() -> None:
            if not edit_mode.get():
                return
            selected_ids.update(str(record.get("record_id") or "") for record in all_records if record.get("record_id"))
            refresh_rows()

        def clear_selected() -> None:
            selected_ids.clear()
            refresh_rows()

        def ask_confirm_delete() -> bool:
            decision = {"confirmed": False}
            confirm_window = create_independent_window("确认删除", resizable=False)

            body = PixelBorderFrame(confirm_window, padding=(22, 18), background=PANEL)
            body.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)
            body.columnconfigure(0, minsize=280)
            tk.Label(
                body,
                text="确定删除？",
                background=PANEL,
                foreground=INK,
                font=(ui_font_family, 15, "bold"),
                anchor=tk.CENTER,
            ).grid(row=0, column=0, sticky="ew", pady=(0, 10))
            tk.Label(
                body,
                text="若删除则无法恢复",
                background=PANEL,
                foreground=MUTED,
                font=(ui_font_family, 12, "bold"),
                anchor=tk.CENTER,
            ).grid(row=1, column=0, sticky="ew")

            def choose(confirmed: bool) -> None:
                decision["confirmed"] = confirmed
                confirm_window.destroy()

            buttons = ttk.Frame(body, style="Panel.TFrame")
            buttons.grid(row=2, column=0, sticky="e", pady=(18, 0))
            CutCornerButton(
                buttons,
                text="取消",
                command=lambda: choose(False),
                variant="default",
                font_family=ui_font_family,
                outer_background=PANEL,
            ).pack(side=tk.LEFT, padx=(0, 8))
            CutCornerButton(
                buttons,
                text="确定",
                command=lambda: choose(True),
                variant="primary",
                font_family=ui_font_family,
                outer_background=PANEL,
            ).pack(side=tk.LEFT)
            confirm_window.protocol("WM_DELETE_WINDOW", lambda: choose(False))
            show_centered_window(confirm_window, manage)
            confirm_window.wait_window()
            return decision["confirmed"]

        def delete_selected() -> None:
            nonlocal all_records
            if not selected_ids:
                messagebox.showinfo("未选中图片", "当前未选中任何图片。", parent=manage)
                return
            if not ask_confirm_delete():
                return
            previous_record_id = _current_selected_record_id()
            deleted = searcher.delete_records(list(selected_ids))
            selected_ids.clear()
            all_records = searcher.search_records(keyword="", newest_first=True)
            count_var.set(format_history_result_count(len(all_records)))
            refresh_rows()
            load_candidates(keyword_var.get(), preserve_record_id=previous_record_id)
            messagebox.showinfo("删除完成", f"已删除 {deleted} 条历史记录。", parent=manage)

        edit_button = CutCornerButton(
            toolbar,
            text="编辑",
            command=toggle_edit,
            variant="default",
            font_family=ui_font_family,
            outer_background=PANEL,
            min_width=64,
            min_height=34,
        )
        finish_button = CutCornerButton(
            toolbar,
            text="完成",
            command=toggle_edit,
            variant="default",
            font_family=ui_font_family,
            outer_background=PANEL,
            min_width=64,
            min_height=34,
        )
        select_all_button = CutCornerButton(
            toolbar,
            text="全选",
            command=select_all,
            variant="default",
            font_family=ui_font_family,
            outer_background=PANEL,
            min_width=64,
            min_height=34,
        )
        clear_selected_button = CutCornerButton(
            toolbar,
            text="取消选择",
            command=clear_selected,
            variant="default",
            font_family=ui_font_family,
            outer_background=PANEL,
            min_width=88,
            min_height=34,
        )
        delete_button = CutCornerButton(
            toolbar,
            text="删除所选",
            command=delete_selected,
            variant="primary",
            font_family=ui_font_family,
            outer_background=PANEL,
            min_width=88,
            min_height=34,
        )
        def close_manage() -> None:
            if edit_mode.get():
                edit_mode.set(False)
                selected_ids.clear()
                refresh_rows()
                return
            manage.withdraw()

        close_button = CutCornerButton(
            toolbar,
            text="关闭",
            command=close_manage,
            variant="default",
            font_family=ui_font_family,
            outer_background=PANEL,
            min_width=64,
            min_height=34,
        )
        list_canvas.bind("<Enter>", lambda _event: wheel_manager.bind(list_canvas, lambda event: scroll_canvas_by_wheel(list_canvas, event)))
        list_canvas.bind("<Leave>", wheel_manager.unbind)
        manage.bind("<Destroy>", lambda event: wheel_manager.unbind() if event.widget is manage else None, add="+")
        refresh_rows()
        manage.protocol("WM_DELETE_WINDOW", close_manage)
        manage.geometry(f"{min(746, max(int(window.winfo_width() * 0.91), 520))}x{min(564, max(int(window.winfo_height() * 0.91), 380))}")
        show_centered_window(manage, window)

    def _on_gallery_wheel(event: tk.Event) -> str:
        """支持 Windows 鼠标滚轮、macOS 触控板和 Linux Button-4/5。"""

        nonlocal gallery_scroll_idle_after_id
        if gallery_scroll_idle_after_id is not None:
            try:
                window.after_cancel(gallery_scroll_idle_after_id)
            except tk.TclError:
                pass
        _delay_gallery_thumbnail_generation()
        result = scroll_canvas_by_wheel(gallery_canvas, event)
        first, last = gallery_canvas.yview()
        if last >= 0.999:
            gallery_canvas.yview_moveto(max(0.0, 1.0 - (last - first)))
        gallery_scroll_idle_after_id = window.after(140, _resume_gallery_after_scroll)
        return result

    def _resume_gallery_after_scroll() -> None:
        nonlocal gallery_scroll_idle_after_id
        gallery_scroll_idle_after_id = None
        _schedule_gallery_render(1)
        _schedule_gallery_thumbnail_generation()

    def _on_detail_wheel(event: tk.Event) -> str:
        return scroll_text_by_wheel(detail_text, event)

    def _on_preview_wheel(event: tk.Event) -> str:
        return scroll_canvas_by_wheel(preview_canvas, event)

    def _bind_gallery_wheel(_event: tk.Event | None = None) -> None:
        wheel_manager.bind(gallery_canvas, _on_gallery_wheel)

    def _bind_detail_wheel(_event: tk.Event | None = None) -> None:
        wheel_manager.bind(detail_text, _on_detail_wheel)

    def _bind_preview_wheel(_event: tk.Event | None = None) -> None:
        wheel_manager.bind(preview_canvas, _on_preview_wheel)

    def _on_gallery_resize(_event: tk.Event) -> None:
        canvas_width = max(gallery_canvas.winfo_width(), GALLERY_CARD_WIDTH + GALLERY_PADDING * 2 + 8)
        available_width = max(canvas_width - GALLERY_PADDING * 2, GALLERY_CARD_WIDTH)
        columns = max(1, (available_width + 10) // (GALLERY_CARD_WIDTH + 10))
        columns = min(columns, max(len(candidates), 1))
        layout = (columns, canvas_width)
        if layout != gallery_last_layout:
            _schedule_gallery_render(60)

    search_icon.bind("<Button-1>", lambda _event: run_search())
    clear_search_button.bind("<Button-1>", lambda _event: clear_search())
    upload_filter_box.bind("<<ComboboxSelected>>", lambda _event: run_search())
    mode_filter_box.bind("<<ComboboxSelected>>", lambda _event: run_search())
    sort_mode_box.bind("<<ComboboxSelected>>", _on_sort_mode_change)
    display_mode_box.bind("<<ComboboxSelected>>", _on_display_mode_change)
    text_source_box.bind("<<ComboboxSelected>>", _on_text_source_change)
    preview_canvas.bind("<Configure>", lambda _event: (_render_preview_image(), _sync_preview_scrollregion()))
    preview_label.bind("<Configure>", _sync_preview_scrollregion)
    preview_canvas.bind("<Enter>", _bind_preview_wheel)
    preview_canvas.bind("<Leave>", wheel_manager.unbind)
    preview_label.bind("<Enter>", _bind_preview_wheel)
    preview_label.bind("<Leave>", wheel_manager.unbind)
    gallery_canvas.bind("<Button-1>", _on_gallery_click)
    gallery_canvas.bind("<Configure>", _on_gallery_resize)
    gallery_canvas.bind("<Enter>", _bind_gallery_wheel)
    gallery_canvas.bind("<Leave>", wheel_manager.unbind)
    detail_text.bind("<Enter>", _bind_detail_wheel)
    detail_text.bind("<Leave>", wheel_manager.unbind)
    keyword_entry.bind("<Return>", lambda _event: run_search())
    window.protocol("WM_DELETE_WINDOW", close_window)
    clear_search()
    window.deiconify()
    window.lift()
    window.focus_set()
    return window

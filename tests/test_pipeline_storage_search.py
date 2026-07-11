import sqlite3
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image

from src.database import init_database
from src.gui.history_search_window import (
    build_history_day_bounds,
    format_history_result_count,
    history_mode_filter_value,
    history_upload_filter_value,
    select_history_detail_text,
)
from src.pipeline import process_single_image
from src.search_manager import OCRSearchManager
from src.storage_manager import OCRStorageManager
from src.task_queue import OCRTaskQueue


class _FakeOcrResult:
    blocks = []

    def render_text(self, mode="plain"):
        return "Hello\n  本地OCR 123" if mode == "layout" else "Hello 本地OCR 123"


class _FakeOcrService:
    def recognize(self, image_path):
        assert Path(image_path).is_file()
        return _FakeOcrResult()


def test_pipeline_saves_record_and_searches_saved_text(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    image_path = tmp_path / "sample.png"
    array = np.full((24, 32, 3), 240, dtype=np.uint8)
    array[8:16, 10:22] = 20
    Image.fromarray(array, mode="RGB").save(image_path)

    result = process_single_image(
        image_path,
        {
            "use_grayscale": True,
            "use_binarize": True,
            "use_denoise": True,
            "crop_box": (2, 3, 30, 20),
            "save_intermediate": True,
            "save_result": True,
        },
        ocr_service=_FakeOcrService(),
    )

    assert result["success"] is True
    assert result["recognized_text"] == "Hello 本地OCR 123"
    assert result["saved_image_path"] == str(image_path.resolve())
    assert result["text_path"] == ""
    assert Path(result["processed_image_path"]).is_file()
    assert all(Path(path).is_file() for path in result["intermediate_paths"].values() if path)

    assert Path("data/ocr_records.db").is_file()
    assert not Path("data/records.json").exists()
    assert not Path("data/texts").exists()
    assert not Path("data/images").exists()
    assert not Path("outputs/history.json").exists()

    storage = OCRStorageManager()
    records = storage.load_records()
    assert records[0]["record_id"] == result["record_id"]
    assert records[0]["image_hash"]
    assert records[0]["recognized_text"] == "Hello 本地OCR 123"
    assert records[0]["layout_text"] == "Hello\n  本地OCR 123"
    assert records[0]["ocr_blocks"] == "[]"
    assert records[0]["image_name"] == "sample.png"
    assert records[0]["image_width"] == 32
    assert records[0]["image_height"] == 24
    assert records[0]["region"] == "2,3,30,20"
    assert records[0]["recognition_mode"] == "text"
    assert records[0]["upload_type"] == "image"
    assert records[0]["edited_text"] == ""
    assert records[0]["image_transform"] == '{"rotation_quarters":0,"mirror_horizontal":false,"mirror_vertical":false}'
    assert isinstance(records[0]["preview_image"], bytes)

    searcher = OCRSearchManager(storage)
    all_candidates = searcher.search("")
    assert len(all_candidates) == 1
    assert all_candidates[0]["image_name"] == "sample.png"
    assert isinstance(all_candidates[0]["preview_image"], bytes)
    candidates = searcher.search("ocr")
    assert len(candidates) == 1
    assert candidates[0]["record_id"] == result["record_id"]
    full = searcher.get_full_result(result["record_id"])
    assert full["image_path"] == result["saved_image_path"]
    assert full["recognized_text"] == "Hello 本地OCR 123"
    assert full["layout_text"] == "Hello\n  本地OCR 123"
    assert full["recognition_mode"] == "text"
    assert full["upload_type"] == "image"
    assert full["region"] == "2,3,30,20"
    assert full["edited_text"] == ""
    assert full["image_transform"] == records[0]["image_transform"]
    assert full["image_name"] == "sample.png"
    assert isinstance(full["preview_image"], bytes)

    time_filtered = storage.query_records(
        start_time=records[0]["created_time"],
        end_time=records[0]["created_time"],
    )
    assert [record["record_id"] for record in time_filtered] == [result["record_id"]]


def test_storage_migration_adds_layout_text_to_existing_database(tmp_path):
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE ocr_records (
            record_id TEXT PRIMARY KEY,
            original_image_path TEXT NOT NULL,
            saved_image_path TEXT NOT NULL,
            recognized_text TEXT NOT NULL,
            created_time TEXT NOT NULL,
            file_size INTEGER NOT NULL DEFAULT 0,
            image_hash TEXT NOT NULL DEFAULT '',
            region TEXT,
            preprocess_summary TEXT NOT NULL DEFAULT '',
            elapsed_seconds REAL NOT NULL DEFAULT 0.0
        )
        """
    )
    connection.execute(
        """
        INSERT INTO ocr_records (
            record_id, original_image_path, saved_image_path, recognized_text, created_time
        ) VALUES ('r1', 'a.png', 'a.png', 'legacy plain text', '2026-01-01T00:00:00')
        """
    )
    connection.commit()

    init_database(connection)
    connection.row_factory = sqlite3.Row
    row = connection.execute("SELECT * FROM ocr_records WHERE record_id = 'r1'").fetchone()

    assert row["recognized_text"] == "legacy plain text"
    assert row["layout_text"] == ""
    assert row["ocr_blocks"] == ""
    assert row["recognition_mode"] == "text"
    assert row["upload_type"] == "image"
    assert row["edited_text"] == ""
    assert row["image_transform"] == ""


def test_storage_separates_mode_region_and_updates_edited_text(tmp_path):
    image_path = tmp_path / "sample.png"
    Image.fromarray(np.full((20, 20, 3), 255, dtype=np.uint8), mode="RGB").save(image_path)
    storage = OCRStorageManager(data_dir=tmp_path / "data")

    text_record = storage.save_record(
        image_path,
        "text mode",
        layout_text="text layout",
        recognition_mode="text",
    )
    document_record = storage.save_record(
        image_path,
        "document mode",
        recognition_mode="document",
        upload_type="document",
    )
    region_record = storage.save_record(
        image_path,
        "region text",
        recognition_mode="text",
        region=(1, 2, 10, 12),
    )

    records = storage.load_records()
    assert len(records) == 3
    assert {record["record_id"] for record in records} == {
        text_record["record_id"],
        document_record["record_id"],
        region_record["record_id"],
    }
    assert document_record["recognition_mode"] == "document"
    assert document_record["upload_type"] == "document"
    assert region_record["upload_type"] == "image"
    assert region_record["region"] == "1,2,10,12"

    searcher = OCRSearchManager(storage)
    document_full = searcher.get_full_result(document_record["record_id"])
    assert document_full["upload_type"] == "document"

    storage.update_edited_text(text_record["record_id"], "latest edited text")
    updated = storage.get_record(text_record["record_id"])
    assert updated is not None
    assert updated["recognized_text"] == "text mode"
    assert updated["layout_text"] == "text layout"
    assert updated["edited_text"] == "latest edited text"


def test_search_records_filters_mode_time_and_deletes(tmp_path):
    image_path = tmp_path / "sample.png"
    Image.fromarray(np.full((18, 18, 3), 255, dtype=np.uint8), mode="RGB").save(image_path)
    storage = OCRStorageManager(data_dir=tmp_path / "data")
    text_record = storage.save_record(image_path, "alpha fast text", recognition_mode="text")
    document_record = storage.save_record(
        image_path,
        "alpha deep text",
        recognition_mode="document",
        upload_type="document",
    )
    old_record = storage.save_record(image_path, "old fast text", recognition_mode="text")

    connection = storage.connection
    connection.execute(
        "UPDATE ocr_records SET created_time = ? WHERE record_id = ?",
        ("2026-07-09T09:00:00", text_record["record_id"]),
    )
    connection.execute(
        "UPDATE ocr_records SET created_time = ? WHERE record_id = ?",
        ("2026-07-10T12:30:00", document_record["record_id"]),
    )
    connection.execute(
        "UPDATE ocr_records SET created_time = ? WHERE record_id = ?",
        ("2026-07-01T08:00:00", old_record["record_id"]),
    )
    connection.commit()

    searcher = OCRSearchManager(storage)
    text_results = searcher.search_records(keyword="text", recognition_mode="text", newest_first=True)
    assert [record["record_id"] for record in text_results] == [text_record["record_id"], old_record["record_id"]]

    document_type_results = searcher.search_records(keyword="text", upload_type="document", newest_first=True)
    assert [record["record_id"] for record in document_type_results] == [document_record["record_id"]]

    ranged = searcher.search_records(
        keyword="alpha",
        start_time="2026-07-10T00:00:00",
        end_time="2026-07-10T23:59:59",
        newest_first=True,
    )
    assert [record["record_id"] for record in ranged] == [document_record["record_id"]]
    assert ranged[0]["match_count"] == 1
    assert "alpha" in ranged[0]["snippet"].lower()

    deleted = searcher.delete_records([document_record["record_id"], "missing"])
    assert deleted == 1
    assert storage.get_record(document_record["record_id"]) is None
    remaining_ids = {record["record_id"] for record in storage.load_records()}
    assert remaining_ids == {text_record["record_id"], old_record["record_id"]}


def test_storage_preserves_transformed_history_preview(tmp_path):
    image_path = tmp_path / "sample.png"
    image = Image.new("RGB", (10, 20), "white")
    image.putpixel((1, 2), (255, 0, 0))
    image.save(image_path)
    storage = OCRStorageManager(data_dir=tmp_path / "data")

    record = storage.save_record(
        image_path,
        "edited image text",
        rotation_quarters=1,
        mirror_horizontal=True,
        mirror_vertical=True,
    )

    assert record["image_width"] == 20
    assert record["image_height"] == 10
    assert record["image_transform"] == '{"rotation_quarters":1,"mirror_horizontal":true,"mirror_vertical":true}'
    searcher = OCRSearchManager(storage)
    full = searcher.get_full_result(record["record_id"])
    assert full["image_width"] == 20
    assert full["image_height"] == 10
    assert full["image_transform"] == record["image_transform"]
    assert isinstance(full["preview_image"], bytes)

def test_history_detail_text_selects_mode_with_plain_fallback():
    record = {
        "recognized_text": "plain text",
        "layout_text": "line 1\n  line 2",
        "edited_text": "edited latest",
    }

    assert select_history_detail_text(record, "全文拼接") == "plain text"
    assert select_history_detail_text(record, "按原位置排版") == "line 1\n  line 2"
    assert select_history_detail_text(record, "全文拼接", "编辑后") == "edited latest"
    assert select_history_detail_text(record, "按原位置排版", "编辑后") == "edited latest"
    assert select_history_detail_text({"recognized_text": "old plain"}, "按原位置排版") == "old plain"
    assert select_history_detail_text({"recognized_text": "old plain"}, "全文拼接", "编辑后") == "old plain"
    assert select_history_detail_text(record, "unknown") == "plain text"
    assert history_mode_filter_value("全部") is None
    assert history_mode_filter_value("快速识别") == "text"
    assert history_mode_filter_value("深度识别") == "document"
    assert history_upload_filter_value("全部") is None
    assert history_upload_filter_value("图片") == "image"
    assert history_upload_filter_value("文档") == "document"
    assert build_history_day_bounds(date(2026, 7, 1), date(2026, 7, 10)) == (
        "2026-07-01T00:00:00",
        "2026-07-10T23:59:59",
    )
    assert format_history_result_count(52) == "共 52 条"


def test_task_queue_with_options_calls_pipeline(monkeypatch):
    calls = []

    def fake_process_single_image(image_path, options):
        calls.append((image_path, options))
        return {"record_id": "r1", "recognized_text": f"text:{image_path}"}

    monkeypatch.setattr("src.pipeline.process_single_image", fake_process_single_image)

    queue = OCRTaskQueue()
    queue.add_images(["a.png", "b.png"])
    tasks = queue.run_all({"use_grayscale": True})

    assert [task.image_path for task in tasks] == ["a.png", "b.png"]
    assert [task.result_text for task in tasks] == ["text:a.png", "text:b.png"]
    assert calls == [
        ("a.png", {"use_grayscale": True}),
        ("b.png", {"use_grayscale": True}),
    ]

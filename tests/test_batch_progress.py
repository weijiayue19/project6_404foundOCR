import queue
from pathlib import Path

from src.gui.main_window import MainWindow
from src.models.ocr_result import OcrResult, TextBlock
from src.ocr_engine import OcrExecutionResult
from src.task_queue import OCRTask, OCRTaskQueue


class _StringVarStub:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class _TextStub:
    def __init__(self):
        self.value = ""

    def delete(self, *_args):
        self.value = ""

    def insert(self, _index, value):
        self.value = value


def test_gui_drains_each_batch_result_without_waiting_for_whole_batch():
    window = MainWindow.__new__(MainWindow)
    window._batch_progress_queue = queue.Queue()
    window.current_batch_tasks = []
    window.status_var = _StringVarStub()
    window.batch_image_infos = [("first.png", 10, 10), ("second.png", 10, 10)]
    window.preview_image_index = 0
    window._is_recognizing = True
    window._save_recognition_record = lambda _path, _text, **_kwargs: None
    window._render_current_result_text = lambda: "当前结果"
    window._sync_result_actions = lambda _text: None

    first = OCRTask(image_path="first.png", status=OCRTaskQueue.FINISHED, result_text="一")
    window._enqueue_batch_progress(1, 2, first)
    window._drain_batch_progress()

    assert window.current_batch_tasks == [first]
    assert window.status_var.value == "当前图片 1/2：识别完成；批量进度 1/2"


def test_batch_record_id_is_saved_on_task_and_not_saved_twice():
    window = MainWindow.__new__(MainWindow)
    window.current_batch_tasks = []
    window.status_var = _StringVarStub()
    window.batch_image_infos = [("first.png", 10, 10)]
    window.preview_image_index = 0
    window._is_recognizing = False
    save_calls = []
    window._save_recognition_record = (
        lambda path, text, **kwargs: save_calls.append((path, text, kwargs)) or "abc123ef"
    )
    window._render_current_result_text = lambda: "当前结果"
    window._sync_result_actions = lambda _text: None
    window._set_copy_feedback = lambda _text: None
    window._update_current_batch_status = lambda: None

    task = OCRTask(image_path="first.png", status=OCRTaskQueue.FINISHED, result_text="一")
    window._handle_batch_progress(1, 1, task)
    window._handle_batch_result([task])

    assert save_calls == [
        (
            "first.png",
            "一",
            {
                "layout_text": "一",
                "ocr_blocks": None,
                "recognition_mode": "text",
                "region": None,
            },
        )
    ]
    assert task.extra["record_id"] == "abc123ef"
    assert task.extra["gui_recorded"] is True


def test_pending_batch_image_keeps_ocr_output_empty_and_uses_status_bar():
    window = MainWindow.__new__(MainWindow)
    window.result_text = _TextStub()
    window.current_result = None
    window.current_batch_tasks = [
        OCRTask(image_path="first.png", status=OCRTaskQueue.FINISHED, result_text="一")
    ]
    window.batch_image_infos = [("first.png", 10, 10), ("second.png", 10, 10)]
    window.preview_image_index = 1
    window._is_recognizing = True
    window.status_var = _StringVarStub()

    assert window._render_current_result_text() == ""
    assert window.result_text.value == ""
    window._update_current_batch_status()
    assert window.status_var.value == "当前图片 2/2：等待识别；批量进度 1/2"


def test_failed_and_empty_batch_results_keep_status_out_of_ocr_output():
    window = MainWindow.__new__(MainWindow)
    window.result_text = _TextStub()
    window.current_result = None
    window.batch_image_infos = [("failed.png", 10, 10), ("empty.png", 10, 10)]
    window.current_batch_tasks = [
        OCRTask(
            image_path="failed.png",
            status=OCRTaskQueue.FAILED,
            error_message="模型错误",
        ),
        OCRTask(
            image_path="empty.png",
            status=OCRTaskQueue.FINISHED,
            result_text="",
        ),
    ]
    window._is_recognizing = False
    window.status_var = _StringVarStub()

    window.preview_image_index = 0
    assert window._render_current_result_text() == ""
    window._update_current_batch_status()
    assert window.status_var.value == "当前图片 1/2：识别失败：模型错误；批量进度 2/2"

    window.preview_image_index = 1
    assert window._render_current_result_text() == ""
    window._update_current_batch_status()
    assert window.status_var.value == "当前图片 2/2：识别完成（未检测到文字）；批量进度 2/2"


def test_preview_can_switch_to_a_batch_image_that_is_still_pending():
    window = MainWindow.__new__(MainWindow)
    window.batch_image_infos = [
        (Path("first.png"), 10, 10),
        (Path("pending.png"), 20, 20),
    ]
    window.preview_image_index = 0
    loaded = []
    window._load_selected_image = lambda path, width, height: loaded.append(
        (path, width, height)
    )
    window._refresh_preview_selector = lambda: None
    window._render_current_result_text = lambda: ""
    window._sync_result_actions = lambda _text: None
    window._update_current_batch_status = lambda: None

    window._show_preview_image(1)

    assert window.preview_image_index == 1
    assert loaded == [(Path("pending.png"), 20, 20)]


def test_selected_region_result_is_written_to_its_batch_slot():
    window = MainWindow.__new__(MainWindow)
    window.batch_image_infos = [
        (Path("first.png"), 10, 10),
        (Path("second.png"), 10, 10),
    ]
    window.current_batch_tasks = []
    window.current_recognition_region = (1, 2, 8, 9)
    window._save_recognition_record = lambda _path, _text, **_kwargs: None
    window._render_current_result_text = lambda: "二区"
    window._sync_result_actions = lambda _text: None
    window._set_copy_feedback = lambda _text: None
    window._update_current_batch_status = lambda: None
    window._current_render_mode = lambda: "plain"
    result = OcrResult(
        image_path=Path("second.png"),
        elapsed_seconds=0.2,
        blocks=[TextBlock(text="二区", confidence=0.9, box=[])],
    )
    execution = OcrExecutionResult(
        ocr_result=result,
        processed_image_path=Path("processed.png"),
        steps=[],
        preprocess_seconds=0.1,
    )

    window._store_selected_region_result(1, execution)

    assert len(window.current_batch_tasks) == 2
    assert window.current_batch_tasks[0].status == OCRTaskQueue.WAITING
    assert window.current_batch_tasks[1].status == OCRTaskQueue.FINISHED
    assert window.current_batch_tasks[1].result_text == "二区"
    assert window.current_batch_tasks[1].extra["region"] == (1, 2, 8, 9)

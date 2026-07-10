import queue
import multiprocessing as mp

from src.ocr_engine import PreprocessConfig
from src.services import batch_process
from src.task_queue import OCRTask, OCRTaskQueue


def test_batch_process_worker_sends_progress_before_complete():
    closed = []

    class FakeEngine:
        def close(self):
            closed.append(True)

    def fake_run_batch(
        _engine,
        image_paths,
        _mode,
        _preprocess_config,
        _render_mode,
        on_task_complete,
        regions=None,
        source_indices=None,
    ):
        tasks = []
        for completed, path in enumerate(image_paths, start=1):
            task = OCRTask(
                image_path=str(path),
                status=OCRTaskQueue.FINISHED,
                result_text=path.stem,
            )
            if regions is not None:
                task.extra["region"] = regions[completed - 1]
            if source_indices is not None:
                task.extra["source_index"] = source_indices[completed - 1]
            tasks.append(task)
            on_task_complete(completed, len(image_paths), task)
        return tasks

    original_engine = batch_process.OcrEngine
    original_runner = batch_process.run_batch_recognition
    batch_process.OcrEngine = FakeEngine
    batch_process.run_batch_recognition = fake_run_batch
    output = queue.Queue()
    try:
        batch_process.run_batch_process(
            ["first.png", "second.png"],
            "text",
            object(),
            "plain",
            output,
        )
    finally:
        batch_process.OcrEngine = original_engine
        batch_process.run_batch_recognition = original_runner

    messages = [output.get_nowait(), output.get_nowait(), output.get_nowait()]
    assert [message[0] for message in messages] == ["progress", "progress", "complete"]
    assert [message[1] for message in messages[:2]] == [1, 2]
    assert messages[2] == ("complete", 2)
    assert closed == [True]


def test_batch_process_accepts_optional_regions():
    closed = []

    class FakeEngine:
        def close(self):
            closed.append(True)

    def fake_run_batch(
        _engine,
        image_paths,
        _mode,
        _preprocess_config,
        _render_mode,
        on_task_complete,
        regions=None,
        source_indices=None,
    ):
        tasks = []
        for completed, path in enumerate(image_paths, start=1):
            task = OCRTask(
                image_path=str(path),
                status=OCRTaskQueue.FINISHED,
                result_text=path.stem,
            )
            task.extra["region"] = regions[completed - 1]
            if source_indices is not None:
                task.extra["source_index"] = source_indices[completed - 1]
            tasks.append(task)
            on_task_complete(completed, len(image_paths), task)
        return tasks

    original_engine = batch_process.OcrEngine
    original_runner = batch_process.run_batch_recognition
    batch_process.OcrEngine = FakeEngine
    batch_process.run_batch_recognition = fake_run_batch
    output = queue.Queue()
    try:
        batch_process.run_batch_process(
            ["first.png", "second.png"],
            "text",
            object(),
            "plain",
            output,
            [(1, 2, 3, 4), None],
        )
    finally:
        batch_process.OcrEngine = original_engine
        batch_process.run_batch_recognition = original_runner

    first = output.get_nowait()
    second = output.get_nowait()
    complete = output.get_nowait()
    assert first[3].extra["region"] == (1, 2, 3, 4)
    assert second[3].extra["region"] is None
    assert complete == ("complete", 2)
    assert closed == [True]


def test_batch_process_forwards_source_indices():
    class FakeEngine:
        def close(self):
            return None

    def fake_run_batch(
        _engine,
        image_paths,
        _mode,
        _preprocess_config,
        _render_mode,
        on_task_complete,
        regions=None,
        source_indices=None,
    ):
        task = OCRTask(
            image_path=str(image_paths[0]),
            status=OCRTaskQueue.FINISHED,
            result_text="new",
        )
        task.extra["source_index"] = source_indices[0]
        on_task_complete(1, 1, task)
        return [task]

    original_engine = batch_process.OcrEngine
    original_runner = batch_process.run_batch_recognition
    batch_process.OcrEngine = FakeEngine
    batch_process.run_batch_recognition = fake_run_batch
    output = queue.Queue()
    try:
        batch_process.run_batch_process(
            ["new.png"],
            "text",
            object(),
            "plain",
            output,
            [None],
            [2],
        )
    finally:
        batch_process.OcrEngine = original_engine
        batch_process.run_batch_recognition = original_runner

    progress = output.get_nowait()
    assert progress[3].extra["source_index"] == 2


def test_spawned_batch_process_reports_each_failed_item_and_exits_cleanly():
    context = mp.get_context("spawn")
    output = context.Queue()
    process = context.Process(
        target=batch_process.run_batch_process,
        args=(
            ["missing_first.png", "missing_second.png"],
            "text",
            PreprocessConfig(),
            "plain",
            output,
        ),
    )
    process.start()

    messages = []
    while not messages or messages[-1][0] not in {"complete", "error"}:
        messages.append(output.get(timeout=10))
    process.join(timeout=10)

    assert not process.is_alive()
    assert process.exitcode == 0
    assert [message[0] for message in messages] == ["progress", "progress", "complete"]
    assert all(message[3].status == OCRTaskQueue.FAILED for message in messages[:2])


if __name__ == "__main__":
    test_spawned_batch_process_reports_each_failed_item_and_exits_cleanly()
    print("spawned batch process smoke check: passed")

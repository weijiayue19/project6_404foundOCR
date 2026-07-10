"""在独立进程中执行批量 OCR，避免阻塞 Tkinter 事件循环。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.ocr_engine import OcrEngine, PreprocessConfig
from src.services.recognition_runner import RecognitionMode, RenderMode, run_batch_recognition
from src.task_queue import OCRTask


def run_batch_process(
    image_paths: list[str],
    mode: RecognitionMode,
    preprocess_config: PreprocessConfig,
    render_mode: RenderMode,
    output_queue: Any,
    regions: list[tuple[int, int, int, int] | None] | None = None,
    source_indices: list[int] | None = None,
    preprocess_configs: list[PreprocessConfig] | None = None,
) -> None:
    """子进程入口；逐张发送 progress，结束时发送 complete 或 error。"""

    engine: OcrEngine | None = None
    try:
        engine = OcrEngine()

        def send_progress(completed: int, total: int, task: OCRTask) -> None:
            output_queue.put(("progress", completed, total, task))

        if regions is None:
            tasks = run_batch_recognition(
                engine,
                [Path(path) for path in image_paths],
                mode,
                preprocess_config,
                render_mode,
                send_progress,
                source_indices=source_indices,
                preprocess_configs=preprocess_configs,
            )
        else:
            tasks = run_batch_recognition(
                engine,
                [Path(path) for path in image_paths],
                mode,
                preprocess_config,
                render_mode,
                send_progress,
                regions,
                source_indices,
                preprocess_configs,
            )
        engine.close()
        engine = None
        output_queue.put(("complete", len(tasks)))
    except BaseException as exc:  # noqa: BLE001 - 子进程必须把错误送回 GUI。
        output_queue.put(("error", f"{type(exc).__name__}: {exc}"))
    finally:
        if engine is not None:
            try:
                engine.close()
            except Exception:  # noqa: BLE001 - 不覆盖已经发送的原始错误。
                pass

"""桌面端 OCR 任务编排。"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Literal

from src.image_utils import detect_upload_type
from src.ocr_engine import OcrEngine, OcrRequest, PreprocessConfig
from src.task_queue import OCRTask, OCRTaskQueue

RecognitionMode = Literal["text", "document"]
RenderMode = Literal["plain", "layout"]


def run_batch_recognition(
    engine: OcrEngine,
    image_paths: list[Path],
    mode: RecognitionMode,
    preprocess_config: PreprocessConfig,
    render_mode: RenderMode,
    on_task_complete: Callable[[int, int, OCRTask], None] | None = None,
    regions: list[tuple[int, int, int, int] | None] | None = None,
    source_indices: list[int] | None = None,
    preprocess_configs: list[PreprocessConfig] | None = None,
) -> list[OCRTask]:
    """用 FIFO 队列顺序识别多张图片，并逐张回传已完成任务。"""

    next_index = 0

    def process_single_image(image_path: str) -> object:
        nonlocal next_index
        task_index = next_index
        region = regions[task_index] if regions is not None and task_index < len(regions) else None
        next_index += 1
        config = (
            preprocess_configs[task_index]
            if preprocess_configs is not None and task_index < len(preprocess_configs)
            else preprocess_config
        )
        request = OcrRequest(
            image_path=Path(image_path),
            mode=mode,
            region=region,
            preprocess_config=config,
        )
        execution = engine.recognize(request)
        text = execution.ocr_result.render_text(render_mode).strip()
        preprocess_summary = "；".join(step.description for step in execution.steps) or "未启用额外预处理"
        source_index = (
            source_indices[task_index]
            if source_indices is not None and task_index < len(source_indices)
            else task_index
        )
        return (
            text or "（未识别到文字）",
            preprocess_summary,
            execution.ocr_result.elapsed_seconds + execution.preprocess_seconds,
            execution.ocr_result,
            region,
            source_index,
            mode,
            detect_upload_type(image_path),
        )

    ocr_queue = OCRTaskQueue(process_func=process_single_image)
    ocr_queue.add_images([str(path) for path in image_paths])
    tasks: list[OCRTask] = []
    total = len(image_paths)
    while not ocr_queue.is_empty():
        task = ocr_queue.run_next()
        if task is None:
            break
        _normalize_finished_task(task)
        tasks.append(task)
        if on_task_complete is not None:
            on_task_complete(len(tasks), total, task)
    return tasks


def _normalize_finished_task(task: OCRTask) -> None:
    """把队列处理函数的原始返回值整理成 GUI 可直接读取的字段。"""

    if task.status != OCRTaskQueue.FINISHED:
        return

    text, preprocess_summary, elapsed_seconds = task.result_text, "", 0.0
    raw_result = task.extra.get("raw_result")
    if isinstance(raw_result, tuple):
        text = str(raw_result[0])
        preprocess_summary = str(raw_result[1])
        elapsed_seconds = float(raw_result[2])
        if len(raw_result) > 3:
            task.extra["ocr_result"] = raw_result[3]
        if len(raw_result) > 4:
            task.extra["region"] = raw_result[4]
        if len(raw_result) > 5:
            task.extra["source_index"] = raw_result[5]
        if len(raw_result) > 6:
            task.extra["recognition_mode"] = raw_result[6]
        if len(raw_result) > 7:
            task.extra["upload_type"] = raw_result[7]
    task.result_text = text
    task.extra["preprocess_summary"] = preprocess_summary
    task.extra["elapsed_seconds"] = elapsed_seconds

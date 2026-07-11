"""后台批量任务队列。

Tkinter 主线程不适合直接运行 PaddleOCR。该模块包含两类队列：

1. ``TaskQueue``：GUI 使用的通用后台线程队列，负责把单次耗时任务放到工作线程。
2. ``OCRTaskQueue``：批量 OCR 的 FIFO 调度队列，保存批量任务状态并按图片加入顺序逐个执行。

批量 OCR 适合使用任务队列，因为一次上传多张图片时，如果同时启动多个 OCR
推理任务，很容易占满 CPU 和内存，导致桌面程序卡顿。FIFO 队列可以保证
“先加入的图片先识别”，并把资源占用控制在一次只处理一张图。

GUI 批量识别优先通过 ``src.services.recognition_runner`` / ``src.services.batch_process``
组织真实 OCR 流程；``OCRTaskQueue.run_next(options)`` 和 ``run_all(options)`` 中延迟导入
``src.pipeline.process_single_image`` 的路径保留给 CLI、demo 和既有测试兼容。
"""

from __future__ import annotations

import queue
import threading
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from itertools import count
from time import perf_counter
from typing import Any, Generic, TypeVar

T = TypeVar("T")
OcrProcessor = Callable[[str], object]


class TaskStatus(str, Enum):
    """任务状态。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"


@dataclass(slots=True)
class TaskResult(Generic[T]):
    """后台任务结果。"""

    task_id: int
    status: TaskStatus
    value: T | None = None
    error: Exception | None = None
    elapsed_seconds: float = 0.0


@dataclass(slots=True)
class _QueuedTask(Generic[T]):
    task_id: int
    func: Callable[[], T]
    created_at: float = field(default_factory=perf_counter)


class TaskQueue(Generic[T]):
    """单线程 FIFO 任务队列，适合顺序执行 OCR 批量任务。"""

    def __init__(self) -> None:
        self._tasks: queue.Queue[_QueuedTask[T] | None] = queue.Queue()
        self._results: queue.Queue[TaskResult[T]] = queue.Queue()
        self._id_counter = count(1)
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def submit(self, func: Callable[[], T]) -> int:
        """提交一个后台任务并返回任务编号。"""

        task_id = next(self._id_counter)
        self._tasks.put(_QueuedTask(task_id, func))
        return task_id

    def poll_result(self) -> TaskResult[T] | None:
        """非阻塞读取一个已完成任务结果。"""

        try:
            return self._results.get_nowait()
        except queue.Empty:
            return None

    def shutdown(self) -> None:
        """通知工作线程退出。"""

        self._tasks.put(None)

    def _run(self) -> None:
        while True:
            task = self._tasks.get()
            if task is None:
                return
            started_at = perf_counter()
            try:
                value = task.func()
            except Exception as exc:  # noqa: BLE001 - 需要把异常送回 GUI 主线程。
                self._results.put(
                    TaskResult(
                        task_id=task.task_id,
                        status=TaskStatus.ERROR,
                        error=exc,
                        elapsed_seconds=perf_counter() - started_at,
                    )
                )
            else:
                self._results.put(
                    TaskResult(
                        task_id=task.task_id,
                        status=TaskStatus.SUCCESS,
                        value=value,
                        elapsed_seconds=perf_counter() - started_at,
                    )
                )


@dataclass(slots=True)
class OCRTask:
    """一条批量 OCR 任务。

    任务本身只保存调度信息和识别结果，不直接调用 PaddleOCR。状态流转为：
    ``waiting`` -> ``running`` -> ``finished``，如果识别函数抛出异常，则为
    ``waiting`` -> ``running`` -> ``failed``。
    """

    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    image_path: str = ""
    status: str = "waiting"
    created_time: str = field(default_factory=lambda: datetime.now().replace(microsecond=0).isoformat())
    started_time: str | None = None
    finished_time: str | None = None
    result_text: str = ""
    error_message: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为便于展示、测试或 JSON 保存的字典。"""

        return {
            "task_id": self.task_id,
            "image_path": self.image_path,
            "status": self.status,
            "created_time": self.created_time,
            "started_time": self.started_time,
            "finished_time": self.finished_time,
            "result_text": self.result_text,
            "error_message": self.error_message,
            "extra": dict(self.extra),
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "OCRTask":
        """从字典恢复一条 OCR 任务。"""

        if not isinstance(data, dict):
            raise ValueError("OCR task data must be a dictionary.")

        required_fields = {"task_id", "image_path", "status", "created_time"}
        missing = sorted(required_fields - set(data))
        if missing:
            raise ValueError(f"OCR task data is missing required fields: {', '.join(missing)}")

        extra = data.get("extra", {})
        if extra is None:
            extra = {}
        if not isinstance(extra, dict):
            raise ValueError("OCR task field 'extra' must be a dictionary.")

        return OCRTask(
            task_id=str(data["task_id"]),
            image_path=str(data["image_path"]),
            status=str(data["status"]),
            created_time=str(data["created_time"]),
            started_time=data.get("started_time"),
            finished_time=data.get("finished_time"),
            result_text=str(data.get("result_text", "")),
            error_message=str(data.get("error_message", "")),
            extra=dict(extra),
        )


class OCRTaskQueue:
    """基于 FIFO 的批量 OCR 任务调度队列。

    FIFO 是 First In, First Out，即“先进先出”：最先通过 ``enqueue`` 或
    ``add_images`` 进入 ``waiting_queue`` 的图片，会最先被 ``dequeue`` 取出
    并执行识别。这里显式使用 ``collections.deque`` 作为队列数据结构，
    从队尾入队、从队头出队，而不是简单用 for 循环遍历图片路径。

    默认 OCR 函数是 ``fake_ocr``，用于单元测试和 demo。真实 GUI 批量识别
    由 ``src.services.recognition_runner`` 提供处理函数；传入 ``options`` 时
    延迟导入 ``process_single_image`` 的完整流程只作为 CLI 和旧调用兼容路径。
    """

    WAITING = "waiting"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"

    def __init__(self, process_func: OcrProcessor | None = None) -> None:
        self.waiting_queue: deque[OCRTask] = deque()
        self.all_tasks: dict[str, OCRTask] = {}
        self.finished_tasks: list[OCRTask] = []
        self.failed_tasks: list[OCRTask] = []
        self.process_func: OcrProcessor = process_func or fake_ocr

    def enqueue(self, task: OCRTask) -> None:
        """将任务加入等待队列尾部。"""

        if task.task_id in self.all_tasks:
            raise ValueError(f"Task already exists: {task.task_id}")
        if not task.image_path:
            raise ValueError("task.image_path 不能为空")

        task.status = self.WAITING
        task.started_time = None
        task.finished_time = None
        task.result_text = ""
        task.error_message = ""
        self.waiting_queue.append(task)
        self.all_tasks[task.task_id] = task

    def add_image(self, image_path: str) -> OCRTask:
        """根据单个图片路径创建任务并入队。"""

        task = OCRTask(image_path=image_path)
        self.enqueue(task)
        return task

    def add_images(self, image_paths: list[str]) -> list[OCRTask]:
        """批量添加图片路径，按传入顺序依次入队。"""

        tasks: list[OCRTask] = []
        for image_path in image_paths:
            tasks.append(self.add_image(image_path))
        return tasks

    def dequeue(self) -> OCRTask | None:
        """从队头取出最早等待的任务。"""

        if not self.waiting_queue:
            return None
        return self.waiting_queue.popleft()

    def is_empty(self) -> bool:
        """等待队列为空时返回 True。"""

        return not self.waiting_queue

    def size(self) -> int:
        """返回当前仍在等待的任务数量。"""

        return len(self.waiting_queue)

    def total_size(self) -> int:
        """返回队列管理过的总任务数量。"""

        return len(self.all_tasks)

    def get_task(self, task_id: str) -> OCRTask | None:
        """按 task_id 查找任务。"""

        return self.all_tasks.get(task_id)

    def get_all_tasks(self) -> list[OCRTask]:
        """返回所有任务，顺序与创建/入队顺序一致。"""

        return list(self.all_tasks.values())

    def get_task_statuses(self) -> list[dict[str, Any]]:
        """返回任务列表状态，便于 GUI 表格或测试断言使用。"""

        return [task.to_dict() for task in self.get_all_tasks()]

    def get_waiting_tasks(self) -> list[OCRTask]:
        """返回尚未开始的等待任务。"""

        return list(self.waiting_queue)

    def get_finished_tasks(self) -> list[OCRTask]:
        """返回识别成功的任务。"""

        return list(self.finished_tasks)

    def get_failed_tasks(self) -> list[OCRTask]:
        """返回识别失败的任务。"""

        return list(self.failed_tasks)

    def run_next(
        self,
        options: dict[str, Any] | OcrProcessor | None = None,
        process_func: OcrProcessor | None = None,
    ) -> OCRTask | None:
        """取出并执行下一个等待任务。

        任务状态流转：
        - ``waiting``：任务刚入队，尚未执行。
        - ``running``：任务已从 FIFO 队头取出，正在调用 OCR 函数。
        - ``finished``：OCR 函数正常返回，结果保存到 ``result_text``。
        - ``failed``：OCR 函数抛出异常，错误信息保存到 ``error_message``。

        传入 ``options`` 字典时，会走 ``process_single_image`` 兼容流程；GUI 批量
        识别通常通过 ``process_func`` 注入服务层处理函数。不传 options 时仍使用
        构造队列时给出的处理函数，默认是 ``fake_ocr``。
        """

        if callable(options) and process_func is None:
            process_func = options
            options = None

        task = self.dequeue()
        if task is None:
            return None

        task.status = self.RUNNING
        task.started_time = self._now_iso()
        processor = self._resolve_processor(options, process_func)
        try:
            result = processor(task.image_path)
        except Exception as exc:  # noqa: BLE001 - task queues must capture task failures.
            task.status = self.FAILED
            task.error_message = str(exc)
            task.result_text = ""
            task.finished_time = self._now_iso()
            self.failed_tasks.append(task)
        else:
            task.status = self.FINISHED
            task.extra["raw_result"] = result
            if isinstance(result, dict) and "recognized_text" in result:
                task.result_text = str(result.get("recognized_text", ""))
                task.extra["record_id"] = result.get("record_id")
            else:
                task.result_text = str(result)
            task.error_message = ""
            task.finished_time = self._now_iso()
            self.finished_tasks.append(task)
        return task

    def run_all(
        self,
        options: dict[str, Any] | OcrProcessor | None = None,
        process_func: OcrProcessor | None = None,
    ) -> list[OCRTask]:
        """按 FIFO 顺序执行所有等待任务。"""

        if callable(options) and process_func is None:
            process_func = options
            options = None

        executed_tasks: list[OCRTask] = []
        while not self.is_empty():
            task = self.run_next(options, process_func)
            if task is not None:
                executed_tasks.append(task)
        return executed_tasks

    def clear(self) -> None:
        """清空等待、成功、失败和总任务记录。"""

        self.waiting_queue.clear()
        self.all_tasks.clear()
        self.finished_tasks.clear()
        self.failed_tasks.clear()

    def summary(self) -> dict[str, int]:
        """返回按状态统计的任务数量。"""

        return {
            "total": self.total_size(),
            "waiting": self.size(),
            "finished": len(self.finished_tasks),
            "failed": len(self.failed_tasks),
        }

    @staticmethod
    def _now_iso() -> str:
        return datetime.now().replace(microsecond=0).isoformat()

    def _resolve_processor(
        self,
        options: dict[str, Any] | None,
        process_func: OcrProcessor | None,
    ) -> OcrProcessor:
        if process_func is not None:
            return process_func
        if options is not None:
            from src.pipeline import process_single_image

            return lambda image_path: process_single_image(image_path, options)
        return self.process_func


def fake_ocr(image_path: str) -> str:
    """用于单元测试和 demo 的模拟 OCR 函数。

    该函数不导入 PaddleOCR，也不读取真实图片，只根据图片路径返回模拟文本。
    如果路径中包含 ``error``，则主动抛出异常，用来演示任务失败状态。
    """

    if "error" in image_path.lower():
        raise RuntimeError(f"Fake OCR failed for {image_path}")
    return f"Fake OCR result for {image_path}"


def demo_background_queue() -> list[TaskResult[int]]:
    """独立演示：提交三个平方计算任务。"""

    tasks: TaskQueue[int] = TaskQueue()
    for number in range(3):
        tasks.submit(lambda n=number: n * n)

    results: list[TaskResult[int]] = []
    while len(results) < 3:
        result = tasks.poll_result()
        if result is not None:
            results.append(result)
    tasks.shutdown()
    return results


def demo_batch_ocr_queue() -> list[OCRTask]:
    """演示批量 OCR FIFO 队列：添加 5 张图片并按队列顺序依次识别。"""

    task_queue = OCRTaskQueue()
    task_queue.add_images(
        [
            "data/page_01.png",
            "data/page_02.png",
            "data/error_page.png",
            "data/page_03.png",
            "data/page_04.png",
        ]
    )
    return task_queue.run_all()


def demo() -> list[OCRTask]:
    """默认 demo 展示批量 OCR 任务队列。"""

    return demo_batch_ocr_queue()


if __name__ == "__main__":
    for item in demo():
        print(item.to_dict())

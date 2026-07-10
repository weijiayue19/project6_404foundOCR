from src.task_queue import OCRTaskQueue


def test_ocr_task_queue_runs_in_fifo_order_and_saves_results():
    queue = OCRTaskQueue()
    created_tasks = queue.add_images(
        [
            "image_01.png",
            "image_02.png",
            "error_image.png",
            "image_03.png",
            "image_04.png",
        ]
    )

    expected_ids = [task.task_id for task in created_tasks]
    executed_tasks = queue.run_all()

    assert [task.task_id for task in executed_tasks] == expected_ids
    assert queue.is_empty()
    assert queue.size() == 0
    assert queue.summary() == {
        "total": 5,
        "waiting": 0,
        "finished": 4,
        "failed": 1,
    }

    failed_task = queue.get_failed_tasks()[0]
    assert failed_task.status == OCRTaskQueue.FAILED
    assert failed_task.error_message

    finished_task = queue.get_finished_tasks()[0]
    assert finished_task.status == OCRTaskQueue.FINISHED
    assert finished_task.result_text.startswith("Fake OCR result for")

    statuses = queue.get_task_statuses()
    assert [task["task_id"] for task in statuses] == expected_ids

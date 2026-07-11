"""本地 OCR 命令行菜单。

本入口只提供核心流程的命令行操作，不处理 GUI。GUI 后续可以直接复用
``src.pipeline.process_single_image``、``OCRTaskQueue``、``OCRSearchManager``。
"""

from __future__ import annotations

from pathlib import Path

from src.pipeline import DEFAULT_OPTIONS, dump_result, process_single_image
from src.search_manager import OCRSearchManager
from src.task_queue import OCRTaskQueue


def main() -> None:
    """启动命令行菜单。"""

    while True:
        print("\n本地 OCR 工具")
        print("1. 单张图片 OCR")
        print("2. 批量图片 OCR")
        print("3. 查询历史 OCR 内容")
        print("4. 查看全部历史记录")
        print("5. 按时间范围查询")
        print("6. 退出")
        choice = input("请选择：").strip()

        if choice == "1":
            _single_image_ocr()
        elif choice == "2":
            _batch_ocr()
        elif choice == "3":
            _search_history()
        elif choice == "4":
            _list_history()
        elif choice == "5":
            _range_search()
        elif choice == "6":
            print("已退出。")
            return
        else:
            print("无效选项，请重新输入。")


def _single_image_ocr() -> None:
    image_path = input("图片路径：").strip().strip('"')
    try:
        result = process_single_image(image_path, _read_options())
    except Exception as exc:  # noqa: BLE001 - CLI must show clear failure.
        print(f"OCR 失败：{exc}")
        return
    print(dump_result(result))


def _batch_ocr() -> None:
    raw = input("多个图片路径（用逗号分隔）：").strip()
    image_paths = [item.strip().strip('"') for item in raw.split(",") if item.strip()]
    if not image_paths:
        print("未输入图片路径。")
        return

    queue = OCRTaskQueue()
    queue.add_images(image_paths)
    options = _read_options()
    tasks = queue.run_all(options)
    for task in tasks:
        print(f"{task.status}: {task.image_path}")
        if task.result_text:
            print(task.result_text)
        if task.error_message:
            print(task.error_message)


def _search_history() -> None:
    keyword = input("关键词：").strip()
    searcher = OCRSearchManager()
    try:
        candidates = searcher.search(keyword)
    except Exception as exc:  # noqa: BLE001
        print(f"查询失败：{exc}")
        return

    if not candidates:
        print("未找到匹配记录。")
        return

    for index, item in enumerate(candidates, start=1):
        print(f"{index}. {item['record_id']} {item['created_time']} {item['snippet']}")

    raw_index = input("输入序号查看完整结果，直接回车返回：").strip()
    if not raw_index:
        return
    try:
        selected = candidates[int(raw_index) - 1]
        full = searcher.get_full_result(selected["record_id"])
    except Exception as exc:  # noqa: BLE001
        print(f"读取完整结果失败：{exc}")
        return
    print(f"图片路径：{full['image_path']}")
    print("完整文本：")
    print(full["recognized_text"])


def _list_history() -> None:
    records = OCRSearchManager().search_records()
    if not records:
        print("暂无历史记录。")
        return
    for record in records:
        preview = str(record["snippet"]).replace("\n", " ")
        print(f"{record['created_time']} {record['record_id']} {record['saved_image_path']} {preview}")


def _range_search() -> None:
    start_time = input("开始时间（例如 2026-07-07T09:00:00）：").strip()
    end_time = input("结束时间（例如 2026-07-07T18:00:00）：").strip()
    try:
        records = OCRSearchManager().search_records(start_time=start_time, end_time=end_time)
    except Exception as exc:  # noqa: BLE001
        print(f"查询失败：{exc}")
        return
    for record in records:
        preview = str(record["snippet"]).replace("\n", " ")
        print(f"{record['created_time']} {record['record_id']} {Path(record['saved_image_path']).name} {preview}")
    if not records:
        print("该时间范围内没有记录。")


def _read_options() -> dict[str, object]:
    options = dict(DEFAULT_OPTIONS)
    crop_raw = input("裁剪框 x1,y1,x2,y2（可直接回车跳过）：").strip()
    if crop_raw:
        values = [int(item.strip()) for item in crop_raw.split(",")]
        if len(values) != 4:
            raise ValueError("裁剪框必须包含 4 个整数")
        options["crop_box"] = tuple(values)
    return options


if __name__ == "__main__":
    main()

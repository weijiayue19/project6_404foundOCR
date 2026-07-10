"""批量 OCR 文本导出的纯数据辅助函数。"""

from __future__ import annotations

from pathlib import Path


def build_separate_txt_names(image_paths: list[str | Path]) -> list[str]:
    """按图片名生成不重复、顺序稳定的 TXT 文件名。"""

    used_names: set[str] = set()
    names: list[str] = []
    for image_path in image_paths:
        stem = Path(image_path).stem or "ocr_result"
        candidate = f"{stem}.txt"
        suffix = 2
        while candidate.casefold() in used_names:
            candidate = f"{stem}_{suffix}.txt"
            suffix += 1
        used_names.add(candidate.casefold())
        names.append(candidate)
    return names


def build_merged_batch_text(entries: list[tuple[str | Path, str]]) -> str:
    """把多张图片的 OCR 文本按导入顺序合并，并保留文件名分隔。"""

    total = len(entries)
    sections = [
        f"[{index}/{total}] {Path(image_path).name}\n{text.strip()}"
        for index, (image_path, text) in enumerate(entries, start=1)
    ]
    return "\n\n".join(sections).strip()

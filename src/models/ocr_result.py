"""OCR 识别结果的数据模型。"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


@dataclass(slots=True)
class TextBlock:
    """一段识别文字及其置信度、四点坐标。"""

    text: str
    confidence: float
    box: list[list[float]]


@dataclass(slots=True)
class OcrResult:
    """单张图片的完整 OCR 结果。"""

    image_path: Path
    elapsed_seconds: float
    blocks: list[TextBlock] = field(default_factory=list)

    @property
    def text(self) -> str:
        """按检测顺序合并全部文字。"""

        return self._plain_text()

    def render_text(self, mode: Literal["plain", "layout"] = "plain") -> str:
        """按指定模式渲染识别文本。"""

        if mode == "layout":
            return self._layout_text()
        return self._plain_text()

    def _plain_text(self) -> str:
        """按识别顺序连续拼接全部文本，不保留原位置空白。"""

        texts = [block.text.strip() for block in self.blocks if block.text.strip()]
        if not texts:
            return ""
        return "".join(texts)

    def _layout_text(self) -> str:
        """根据识别框位置粗略恢复原始排版。"""

        visible_blocks = [block for block in self.blocks if block.text.strip() and block.box]
        if not visible_blocks:
            return self.text

        block_infos = [self._block_info(block) for block in visible_blocks]
        rows = self._group_rows(block_infos)
        global_left = min(info["min_x"] for info in block_infos)
        char_unit = self._char_unit(block_infos)

        lines: list[str] = []
        previous_row_bottom: float | None = None
        previous_row_height: float | None = None

        for row in rows:
            row_top = min(info["min_y"] for info in row)
            row_bottom = max(info["max_y"] for info in row)
            row_height = max(info["height"] for info in row)

            if previous_row_bottom is not None and previous_row_height is not None:
                vertical_gap = row_top - previous_row_bottom
                if vertical_gap > previous_row_height * 1.2:
                    blank_lines = max(1, int(round(vertical_gap / max(previous_row_height, 1.0))) - 1)
                    lines.extend("" for _ in range(blank_lines))

            lines.append(self._render_row(row, global_left, char_unit))
            previous_row_bottom = row_bottom
            previous_row_height = row_height

        return "\n".join(line.rstrip() for line in lines)

    @staticmethod
    def _block_info(block: TextBlock) -> dict[str, float | str]:
        xs = [point[0] for point in block.box]
        ys = [point[1] for point in block.box]
        min_x = min(xs)
        max_x = max(xs)
        min_y = min(ys)
        max_y = max(ys)
        width = max(max_x - min_x, 1.0)
        height = max(max_y - min_y, 1.0)
        text = block.text.strip()
        char_width = width / max(len(text), 1)
        return {
            "text": text,
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
            "center_y": (min_y + max_y) / 2,
            "width": width,
            "height": height,
            "char_width": max(char_width, 1.0),
        }

    @staticmethod
    def _group_rows(
        block_infos: list[dict[str, float | str]],
    ) -> list[list[dict[str, float | str]]]:
        rows: list[list[dict[str, float | str]]] = []
        current_row: list[dict[str, float | str]] = []
        current_center = 0.0
        current_height = 0.0

        for info in sorted(block_infos, key=lambda item: (float(item["center_y"]), float(item["min_x"]))):
            center_y = float(info["center_y"])
            height = float(info["height"])
            if not current_row:
                current_row = [info]
                current_center = center_y
                current_height = height
                continue

            threshold = max(current_height, height) * 0.6
            if abs(center_y - current_center) <= threshold:
                current_row.append(info)
                current_center = sum(float(item["center_y"]) for item in current_row) / len(current_row)
                current_height = sum(float(item["height"]) for item in current_row) / len(current_row)
            else:
                rows.append(sorted(current_row, key=lambda item: float(item["min_x"])))
                current_row = [info]
                current_center = center_y
                current_height = height

        if current_row:
            rows.append(sorted(current_row, key=lambda item: float(item["min_x"])))
        return rows

    @staticmethod
    def _char_unit(block_infos: list[dict[str, float | str]]) -> float:
        widths = sorted(float(info["char_width"]) for info in block_infos)
        middle = len(widths) // 2
        if len(widths) % 2 == 1:
            return max(widths[middle], 1.0)
        return max((widths[middle - 1] + widths[middle]) / 2, 1.0)

    @staticmethod
    def _render_row(
        row: list[dict[str, float | str]],
        global_left: float,
        char_unit: float,
    ) -> str:
        parts: list[str] = []
        cursor = 0
        previous_right: float | None = None
        for info in row:
            text = str(info["text"])
            target = max(0, int(round((float(info["min_x"]) - global_left) / char_unit)))
            if target > cursor:
                parts.append(" " * (target - cursor))
                cursor = target
            elif previous_right is not None:
                gap = float(info["min_x"]) - previous_right
                if gap > char_unit * 0.5:
                    parts.append(" ")
                    cursor += 1

            parts.append(text)
            cursor += len(text)
            previous_right = float(info["max_x"])

        return "".join(parts)

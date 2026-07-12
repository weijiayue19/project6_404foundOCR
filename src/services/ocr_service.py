"""PaddleOCR 3.x 轻量快速识别服务。"""

from pathlib import Path
from time import perf_counter
from typing import Any

from src.image_utils import validate_image_path
from src.models.ocr_result import OcrResult, TextBlock


class OcrService:
    """封装通用 OCR Pipeline，并统一转换识别结果。"""

    TEXT_DETECTION_MODEL_NAME = "PP-OCRv6_small_det"
    TEXT_RECOGNITION_MODEL_NAME = "PP-OCRv6_small_rec"
    USE_DOC_ORIENTATION_CLASSIFY = True
    USE_DOC_UNWARPING = False
    USE_TEXTLINE_ORIENTATION = True
    TEXT_DET_LIMIT_SIDE_LEN = 8192
    TEXT_DET_LIMIT_TYPE = "max"
    TEXT_DET_MAX_SIDE_LIMIT = 12288

    def __init__(self) -> None:
        self._pipeline: Any | None = None

    def recognize(self, image_path: str | Path) -> OcrResult:
        """识别一张图片；模型在第一次调用时加载。"""

        path = self._validate_input_path(image_path)

        started_at = perf_counter()
        pipeline = self._get_pipeline()
        predictions = self._predict(pipeline, path)

        blocks: list[TextBlock] = []
        for prediction in predictions:
            data = self._ocr_data(self._prediction_data(prediction))
            texts = data.get("rec_texts", [])
            scores = data.get("rec_scores", [])
            boxes = data.get("rec_polys", data.get("dt_polys", []))
            for index, text in enumerate(texts):
                score = float(scores[index]) if index < len(scores) else 0.0
                box = boxes[index] if index < len(boxes) else []
                blocks.append(
                    TextBlock(
                        text=str(text),
                        confidence=score,
                        box=self._to_points(box),
                    )
                )

        return OcrResult(
            image_path=path,
            elapsed_seconds=perf_counter() - started_at,
            blocks=blocks,
        )

    def _validate_input_path(self, image_path: str | Path) -> Path:
        path, _, _ = validate_image_path(image_path)
        return path

    def _predict(self, pipeline: Any, path: Path) -> Any:
        """调用轻量通用 OCR Pipeline。"""

        return pipeline.predict(
            str(path),
            use_doc_orientation_classify=self.USE_DOC_ORIENTATION_CLASSIFY,
            use_doc_unwarping=self.USE_DOC_UNWARPING,
            use_textline_orientation=self.USE_TEXTLINE_ORIENTATION,
            text_det_limit_side_len=self.TEXT_DET_LIMIT_SIDE_LEN,
            text_det_limit_type=self.TEXT_DET_LIMIT_TYPE,
        )

    def _get_pipeline(self) -> Any:
        if self._pipeline is None:
            # 延迟导入和初始化，让桌面窗口可以快速显示。
            from paddleocr import PaddleOCR

            kwargs = {
                "device": "cpu",
                "enable_mkldnn": False,
                "use_doc_orientation_classify": self.USE_DOC_ORIENTATION_CLASSIFY,
                "use_doc_unwarping": self.USE_DOC_UNWARPING,
                "use_textline_orientation": self.USE_TEXTLINE_ORIENTATION,
                "text_det_limit_side_len": self.TEXT_DET_LIMIT_SIDE_LEN,
                "text_det_limit_type": self.TEXT_DET_LIMIT_TYPE,
            }

            # In frozen builds, point directly to bundled models so PaddleX
            # never attempts to download from HuggingFace.
            import sys as _sys
            if getattr(_sys, "frozen", False):
                from src.app_paths import get_models_dir
                _m = get_models_dir()
                kwargs["text_detection_model_dir"] = str(_m / self.TEXT_DETECTION_MODEL_NAME)
                kwargs["text_recognition_model_dir"] = str(_m / self.TEXT_RECOGNITION_MODEL_NAME)
                kwargs["textline_orientation_model_dir"] = str(_m / "PP-LCNet_x1_0_textline_ori")
                kwargs["doc_orientation_classify_model_dir"] = str(_m / "PP-LCNet_x1_0_doc_ori")
            else:
                kwargs["text_detection_model_name"] = self.TEXT_DETECTION_MODEL_NAME
                kwargs["text_recognition_model_name"] = self.TEXT_RECOGNITION_MODEL_NAME

            self._pipeline = PaddleOCR(**kwargs)
            self._configure_text_detection_limits(self._pipeline)
        return self._pipeline

    def close(self) -> None:
        """切换模式时释放当前 Pipeline。"""

        if self._pipeline is not None:
            close = getattr(self._pipeline, "close", None)
            if callable(close):
                close()
            self._pipeline = None

    @classmethod
    def _configure_text_detection_limits(cls, pipeline: Any) -> None:
        """同步提高 PaddleOCR 底层文本检测的长边限制。"""

        paddlex_pipeline = getattr(pipeline, "paddlex_pipeline", None)
        if paddlex_pipeline is None:
            return

        paddlex_pipeline.text_det_limit_side_len = cls.TEXT_DET_LIMIT_SIDE_LEN
        paddlex_pipeline.text_det_limit_type = cls.TEXT_DET_LIMIT_TYPE
        paddlex_pipeline.text_det_max_side_limit = cls.TEXT_DET_MAX_SIDE_LIMIT

        text_det_model = getattr(paddlex_pipeline, "text_det_model", None)
        if text_det_model is not None:
            text_det_model.limit_side_len = cls.TEXT_DET_LIMIT_SIDE_LEN
            text_det_model.limit_type = cls.TEXT_DET_LIMIT_TYPE
            text_det_model.max_side_limit = cls.TEXT_DET_MAX_SIDE_LIMIT

            resize_op = getattr(text_det_model, "pre_tfs", {}).get("Resize")
            if resize_op is not None:
                resize_op.limit_side_len = cls.TEXT_DET_LIMIT_SIDE_LEN
                resize_op.limit_type = cls.TEXT_DET_LIMIT_TYPE
                resize_op.max_side_limit = cls.TEXT_DET_MAX_SIDE_LIMIT

    @staticmethod
    def _prediction_data(prediction: Any) -> dict[str, Any]:
        """兼容 PaddleOCR Result 对象及普通字典。"""

        if isinstance(prediction, dict):
            return prediction.get("res", prediction)
        data = getattr(prediction, "json", None)
        if callable(data):
            data = data()
        if isinstance(data, dict):
            return data.get("res", data)
        raise TypeError("无法解析 PaddleOCR 返回的识别结果")

    @staticmethod
    def _ocr_data(data: dict[str, Any]) -> dict[str, Any]:
        """返回通用 OCR 的文字结果字典。"""

        return data

    @staticmethod
    def _to_points(box: Any) -> list[list[float]]:
        """将 NumPy 坐标转换为可序列化的 Python 列表。"""

        if hasattr(box, "tolist"):
            box = box.tolist()
        return [[float(x), float(y)] for x, y in box]

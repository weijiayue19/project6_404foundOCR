"""PP-StructureV3 文档版面识别服务。"""

from pathlib import Path
from typing import Any

from src.image_utils import validate_upload_path
from src.services.ocr_service import OcrService


class DocumentService(OcrService):
    """在通用 OCR 结果之外执行版面和表格结构识别。"""

    USE_TABLE_RECOGNITION = True
    USE_FORMULA_RECOGNITION = False
    USE_CHART_RECOGNITION = False
    USE_SEAL_RECOGNITION = False
    USE_REGION_DETECTION = False

    def _validate_input_path(self, image_path: str | Path) -> Path:
        path, _upload_type, _width, _height = validate_upload_path(image_path)
        return path

    def _predict(self, pipeline: Any, path: Path) -> Any:
        return pipeline.predict(
            str(path),
            use_doc_orientation_classify=self.USE_DOC_ORIENTATION_CLASSIFY,
            use_doc_unwarping=self.USE_DOC_UNWARPING,
            use_textline_orientation=self.USE_TEXTLINE_ORIENTATION,
            use_table_recognition=self.USE_TABLE_RECOGNITION,
            use_formula_recognition=self.USE_FORMULA_RECOGNITION,
            use_chart_recognition=self.USE_CHART_RECOGNITION,
            use_seal_recognition=self.USE_SEAL_RECOGNITION,
            use_region_detection=self.USE_REGION_DETECTION,
            text_det_limit_side_len=self.TEXT_DET_LIMIT_SIDE_LEN,
            text_det_limit_type=self.TEXT_DET_LIMIT_TYPE,
        )

    def _get_pipeline(self) -> Any:
        if self._pipeline is None:
            from paddleocr import PPStructureV3

            self._pipeline = PPStructureV3(
                lang="ch",
                device="cpu",
                enable_mkldnn=False,
                use_doc_orientation_classify=self.USE_DOC_ORIENTATION_CLASSIFY,
                use_doc_unwarping=self.USE_DOC_UNWARPING,
                use_textline_orientation=self.USE_TEXTLINE_ORIENTATION,
                use_table_recognition=self.USE_TABLE_RECOGNITION,
                use_formula_recognition=self.USE_FORMULA_RECOGNITION,
                use_chart_recognition=self.USE_CHART_RECOGNITION,
                use_seal_recognition=self.USE_SEAL_RECOGNITION,
                use_region_detection=self.USE_REGION_DETECTION,
                text_det_limit_side_len=self.TEXT_DET_LIMIT_SIDE_LEN,
                text_det_limit_type=self.TEXT_DET_LIMIT_TYPE,
            )
            self._configure_text_detection_limits(self._pipeline)
        return self._pipeline

    @staticmethod
    def _ocr_data(data: dict[str, Any]) -> dict[str, Any]:
        """当前界面先读取文档结果中的全文 OCR 子结果。"""

        return data.get("overall_ocr_res", data)

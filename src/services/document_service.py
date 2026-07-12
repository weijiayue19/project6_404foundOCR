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

            kwargs = {
                "device": "cpu",
                "enable_mkldnn": False,
                "use_doc_orientation_classify": self.USE_DOC_ORIENTATION_CLASSIFY,
                "use_doc_unwarping": self.USE_DOC_UNWARPING,
                "use_textline_orientation": self.USE_TEXTLINE_ORIENTATION,
                "use_table_recognition": self.USE_TABLE_RECOGNITION,
                "use_formula_recognition": self.USE_FORMULA_RECOGNITION,
                "use_chart_recognition": self.USE_CHART_RECOGNITION,
                "use_seal_recognition": self.USE_SEAL_RECOGNITION,
                "use_region_detection": self.USE_REGION_DETECTION,
                "text_det_limit_side_len": self.TEXT_DET_LIMIT_SIDE_LEN,
                "text_det_limit_type": self.TEXT_DET_LIMIT_TYPE,
            }

            # In frozen builds, point directly to bundled models.
            import sys as _sys
            if getattr(_sys, "frozen", False):
                from src.app_paths import get_models_dir
                _m = get_models_dir()
                kwargs["text_detection_model_dir"] = str(_m / "PP-OCRv5_server_det")
                kwargs["text_recognition_model_dir"] = str(_m / "PP-OCRv5_server_rec")
                kwargs["layout_detection_model_dir"] = str(_m / "PP-DocBlockLayout")
                kwargs["table_classification_model_dir"] = str(_m / "PP-LCNet_x1_0_table_cls")
                kwargs["wired_table_structure_recognition_model_dir"] = str(_m / "SLANeXt_wired")
                kwargs["wired_table_cells_detection_model_dir"] = str(_m / "RT-DETR-L_wired_table_cell_det")
                kwargs["wireless_table_structure_recognition_model_dir"] = str(_m / "SLANet_plus")
                kwargs["wireless_table_cells_detection_model_dir"] = str(_m / "RT-DETR-L_wireless_table_cell_det")
                kwargs["textline_orientation_model_dir"] = str(_m / "PP-LCNet_x1_0_textline_ori")
                kwargs["doc_orientation_classify_model_dir"] = str(_m / "PP-LCNet_x1_0_doc_ori")
                kwargs["doc_unwarping_model_dir"] = str(_m / "UVDoc")
            else:
                kwargs["lang"] = "ch"

            self._pipeline = PPStructureV3(**kwargs)
            self._configure_text_detection_limits(self._pipeline)
        return self._pipeline

    @staticmethod
    def _ocr_data(data: dict[str, Any]) -> dict[str, Any]:
        """当前界面先读取文档结果中的全文 OCR 子结果。"""

        return data.get("overall_ocr_res", data)

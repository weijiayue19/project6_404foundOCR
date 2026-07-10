import numpy as np
from PIL import Image

from src.ocr_engine import OcrEngine, OcrRequest
from src.region_selector import crop_region, normalize_box, validate_box


def test_normalize_and_validate_box_handles_reverse_drag_and_bounds():
    assert normalize_box(8, 7, 2, 1) == (2, 1, 8, 7)
    assert validate_box((-5, 8, 12, 2), image_width=10, image_height=6) == (0, 2, 10, 6)


def test_crop_region_uses_numpy_slice_coordinates():
    image = np.arange(5 * 6, dtype=np.uint8).reshape(5, 6)

    cropped = crop_region(image, 5, 4, 2, 1)

    assert cropped.tolist() == image[1:4, 2:5].tolist()
    cropped[0, 0] = 0
    assert image[1, 2] != 0


def test_ocr_engine_region_preprocess_uses_region_crop(tmp_path):
    path = tmp_path / "sample.png"
    Image.new("RGB", (20, 10), "white").save(path)
    engine = OcrEngine()
    try:
        processed, steps = engine.preprocess(
            OcrRequest(
                image_path=path,
                region=(15, 8, 5, 2),
            )
        )
        assert processed.size == (10, 6)
        assert steps[0].name == "region"
    finally:
        engine.close()

from PIL import Image

from src.ocr_engine import OcrEngine, OcrRequest, PreprocessConfig
from src.preprocess.binarize import adaptive_mean_threshold, binarize_otsu, global_threshold, otsu_threshold
from src.preprocess.denoise import median_filter, remove_isolated_pixels
from src.preprocess.grayscale import to_grayscale_array
from src.region_selector import RegionSelector, build_preview_transform


def test_core_preprocess_algorithms(tmp_path):
    image = Image.new("RGB", (4, 2))
    pixels = image.load()
    pixels[0, 0] = (255, 0, 0)
    pixels[1, 0] = (0, 255, 0)
    pixels[2, 0] = (0, 0, 255)
    pixels[3, 0] = (255, 255, 255)

    gray = to_grayscale_array(image)
    assert gray.shape == (2, 4)
    assert gray.dtype.name == "uint8"

    binary = global_threshold(gray, 100)
    assert set(binary.ravel().tolist()) <= {0, 255}
    assert 0 <= otsu_threshold(gray) <= 255
    assert binarize_otsu(gray).shape == gray.shape
    assert adaptive_mean_threshold(gray, window_size=3).shape == gray.shape

    noisy = binary.copy()
    noisy[0, 0] = 255 - noisy[0, 0]
    assert median_filter(noisy, 3).shape == gray.shape
    assert remove_isolated_pixels(noisy).shape == gray.shape

def test_engine_preprocess_and_helpers(tmp_path):
    path = tmp_path / "sample.png"
    Image.new("RGB", (20, 10), "white").save(path)
    engine = OcrEngine()
    try:
        processed, steps = engine.preprocess(
            OcrRequest(
                image_path=path,
                region=(0, 0, 10, 10),
                preprocess_config=PreprocessConfig(
                    enable_grayscale=True,
                    binarize_mode="adaptive",
                    adaptive_window_size=3,
                    denoise_mode="median",
                ),
            )
        )
        assert processed.size == (10, 10)
        assert [step.name for step in steps][:2] == ["region", "grayscale"]
    finally:
        engine.close()

    transform = build_preview_transform((400, 200), (200, 120))
    selector = RegionSelector()
    selector.begin(20, 20)
    region = selector.finish(100, 80, transform)
    assert len(region) == 4
    assert region[2] > region[0]

def test_engine_respects_configured_preprocess_order(tmp_path):
    path = tmp_path / "order.png"
    Image.new("RGB", (12, 12), "white").save(path)
    engine = OcrEngine()
    try:
        _processed, steps = engine.preprocess(
            OcrRequest(
                image_path=path,
                preprocess_config=PreprocessConfig(
                    enable_grayscale=True,
                    binarize_mode="adaptive",
                    adaptive_window_size=3,
                    denoise_mode="median",
                    step_order=("denoise", "binarize", "grayscale"),
                ),
            )
        )
        assert [step.name for step in steps] == ["median", "adaptive", "grayscale"]
    finally:
        engine.close()


def test_binarize_without_grayscale_does_not_record_grayscale_step(tmp_path):
    path = tmp_path / "binarize.png"
    Image.new("RGB", (12, 12), "white").save(path)
    engine = OcrEngine()
    try:
        _processed, steps = engine.preprocess(
            OcrRequest(
                image_path=path,
                preprocess_config=PreprocessConfig(
                    enable_grayscale=False,
                    binarize_mode="adaptive",
                    adaptive_window_size=3,
                ),
            )
        )
        assert [step.name for step in steps] == ["adaptive"]
    finally:
        engine.close()


def test_input_transform_runs_before_region_crop(tmp_path):
    path = tmp_path / "transform.png"
    image = Image.new("RGB", (3, 2), "black")
    pixels = image.load()
    pixels[0, 0] = (255, 0, 0)
    pixels[2, 1] = (0, 255, 0)
    image.save(path)
    engine = OcrEngine()
    try:
        processed, steps = engine.preprocess(
            OcrRequest(
                image_path=path,
                region=(0, 0, 1, 1),
                preprocess_config=PreprocessConfig(rotation_quarters=1, mirror_horizontal=True),
            )
        )
        assert processed.size == (1, 1)
        assert processed.getpixel((0, 0)) == (0, 255, 0)
        assert [step.name for step in steps] == ["region"]
    finally:
        engine.close()

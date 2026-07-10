from pathlib import Path

from src.models.ocr_result import OcrResult, TextBlock
from src.ocr_engine import OcrExecutionResult, PreprocessConfig
from src.services.batch_export import build_merged_batch_text, build_separate_txt_names
from src.services.recognition_runner import run_batch_recognition


def test_build_separate_txt_names_keeps_order_and_avoids_duplicate_stems():
    names = build_separate_txt_names(
        [
            Path("/first/page.png"),
            Path("/second/page.jpg"),
            Path("/second/page_2.png"),
        ]
    )

    assert names == ["page.txt", "page_2.txt", "page_2_2.txt"]


def test_build_merged_batch_text_uses_filename_sections_in_order():
    text = build_merged_batch_text(
        [
            (Path("/images/one.png"), "第一张文字"),
            (Path("/images/two.png"), "第二张文字"),
        ]
    )

    assert text == "[1/2] one.png\n第一张文字\n\n[2/2] two.png\n第二张文字"


def test_batch_recognition_preserves_each_raw_ocr_result_for_rerendering():
    class FakeEngine:
        def recognize(self, request):
            result = OcrResult(
                image_path=request.image_path,
                elapsed_seconds=0.1,
                blocks=[
                    TextBlock(
                        text=request.image_path.stem,
                        confidence=1.0,
                        box=[[0, 0], [10, 0], [10, 10], [0, 10]],
                    )
                ],
            )
            return OcrExecutionResult(
                ocr_result=result,
                processed_image_path=request.image_path,
                steps=[],
                preprocess_seconds=0.02,
            )

    progress = []
    tasks = run_batch_recognition(
        FakeEngine(),
        [Path("first.png"), Path("second.png")],
        "text",
        PreprocessConfig(),
        "plain",
        lambda completed, total, task: progress.append(
            (completed, total, task.image_path, task.result_text)
        ),
    )

    assert [task.result_text for task in tasks] == ["first", "second"]
    assert [task.extra["ocr_result"].image_path for task in tasks] == [
        Path("first.png"),
        Path("second.png"),
    ]
    assert [task.extra["recognition_mode"] for task in tasks] == ["text", "text"]
    assert progress == [
        (1, 2, "first.png", "first"),
        (2, 2, "second.png", "second"),
    ]


def test_batch_recognition_keeps_original_source_indices_for_subset_runs():
    class FakeEngine:
        def recognize(self, request):
            result = OcrResult(
                image_path=request.image_path,
                elapsed_seconds=0.1,
                blocks=[
                    TextBlock(
                        text=request.image_path.stem,
                        confidence=1.0,
                        box=[],
                    )
                ],
            )
            return OcrExecutionResult(
                ocr_result=result,
                processed_image_path=request.image_path,
                steps=[],
                preprocess_seconds=0.02,
            )

    tasks = run_batch_recognition(
        FakeEngine(),
        [Path("new.png")],
        "text",
        PreprocessConfig(),
        "plain",
        source_indices=[2],
    )

    assert tasks[0].extra["source_index"] == 2

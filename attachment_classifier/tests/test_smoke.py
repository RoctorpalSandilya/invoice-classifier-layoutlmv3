"""Smoke tests: extraction on one file of each type, and a predict() round-trip on a saved model."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from PIL import Image

from attachment_classifier.config import SUPPORTED_EXTENSIONS, Config
from attachment_classifier.extraction import PageFeatures, extract_page

ROOT = Path(__file__).resolve().parents[2]
ATTACHMENTS = ROOT / "Attachments"
CFG = Config(cache_dir=None, docx_pdf_cache_dir=None)


def _first(pattern: str) -> Path:
    matches = sorted(ATTACHMENTS.rglob(pattern))
    if not matches:
        pytest.skip(f"No sample file matching {pattern} under {ATTACHMENTS}")
    return matches[0]


def _assert_features(f: PageFeatures) -> None:
    assert isinstance(f.image, Image.Image) and f.image.mode == "RGB"
    assert f.page_count >= 1
    assert len(f.words) == len(f.boxes)
    assert len(f.words) > 0, "expected at least one word on the first page"
    for b in f.boxes:
        assert len(b) == 4
        assert all(0 <= v <= CFG.bbox_scale for v in b)
        assert b[0] <= b[2] and b[1] <= b[3]
    assert all(isinstance(w, str) and w for w in f.words)


def test_extract_pdf_text_layer() -> None:
    path = _first("lookalike_*.pdf")
    f = extract_page(path.read_bytes(), "application/pdf", CFG)
    _assert_features(f)
    assert f.has_text_layer is True


def test_extract_jpg_ocr() -> None:
    if not CFG.tesseract_cmd:
        pytest.skip("tesseract not installed")
    path = _first("*.jpg")
    f = extract_page(path.read_bytes(), "image/jpeg", CFG)
    _assert_features(f)
    assert f.has_text_layer is False and f.page_count == 1


def test_extract_docx_via_soffice() -> None:
    if not CFG.soffice_cmd:
        pytest.skip("LibreOffice (soffice) not installed")
    path = _first("*.docx")
    f = extract_page(path.read_bytes(), SUPPORTED_EXTENSIONS[".docx"], CFG)
    _assert_features(f)
    assert f.has_text_layer is True and f.meta.get("converted_from") == "docx"


def test_unsupported_type_raises() -> None:
    from attachment_classifier.extraction import ExtractionError

    with pytest.raises(ExtractionError):
        extract_page(b"not a file", "text/plain", CFG)


def _latest_model_dir() -> Path | None:
    env = os.environ.get("AC_MODEL_DIR")
    if env and Path(env).is_dir():
        return Path(env)
    runs = sorted((ROOT / "artifacts").glob("run_*/model"))
    return runs[-1] if runs else None


def test_predict_round_trip() -> None:
    model_dir = _latest_model_dir()
    if model_dir is None:
        pytest.skip("no trained model found under ./artifacts (set AC_MODEL_DIR to override)")
    from attachment_classifier.inference import AttachmentClassifier, PredictionResult

    clf = AttachmentClassifier(model_dir, CFG)
    path = _first("lookalike_*.pdf")
    res = clf.predict(path.read_bytes(), "application/pdf")
    assert isinstance(res, PredictionResult)
    assert 0.0 <= res.prob_invoice <= 1.0
    assert res.is_invoice == (res.prob_invoice >= CFG.threshold)
    assert res.n_words > 0 and res.has_text_layer is True

    batch = clf.predict_batch([(path.read_bytes(), "application/pdf")] * 2)
    assert len(batch) == 2 and all(isinstance(r, PredictionResult) for r in batch)

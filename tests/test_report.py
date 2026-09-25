"""One-page PDF artifact contracts using synthetic research evidence."""

from copy import deepcopy
from datetime import date

import pytest
from pypdf import PdfReader

from tests.test_presentation import example
from wikipedia_interest.report import render_pdf_report


def pdf_text(path):
    reader = PdfReader(path)
    assert len(reader.pages) == 1
    return "\n".join(page.extract_text() for page in reader.pages)


def test_exact_path_signature_one_page_content_unicode_and_no_mutation(tmp_path):
    result = example(("cs", "uk"))
    result.topic.selected_candidate.article_title = "Přerušovaný půst / Переривчасте голодування"
    result.languages[0].article_title = "Přerušovaný půst"
    result.languages[1].article_title = "Переривчасте голодування"
    original = deepcopy(result)
    target = tmp_path / "chosen-name.bin"

    assert render_pdf_report(result, target) == target
    assert target.read_bytes().startswith(b"%PDF-")
    text = pdf_text(target)
    assert "Přerušovaný půst" in text
    assert "Переривчасте голодування" in text
    assert "MEASURED FACTS" in text
    assert "RESTRAINED INTERPRETATION" in text
    assert "LIMITATIONS" in text
    assert "NEXT VALIDATION" in text
    assert "not proof of market size" in text
    assert "willingness to pay" in text
    assert "commercial intent" in text
    assert result == original


def test_missing_yoy_is_unavailable_not_zero(tmp_path):
    result = example(("cs",), missing=[date(2025, 12, 15)])
    target = tmp_path / "missing-yoy.pdf"
    render_pdf_report(result, target)
    text = pdf_text(target)
    assert "Unavailable: missing or incomplete months" in text
    assert "Direction inconclusive: latest-3m YoY is unavailable." in text


@pytest.mark.parametrize("empty,partial", [(True, False), (False, True)])
def test_no_data_and_partial_data_render(tmp_path, empty, partial):
    missing = [date(2024, 2, 15)] if partial else ()
    result = example(("cs",), empty=empty, missing=missing)
    target = tmp_path / f"state-{empty}-{partial}.pdf"
    render_pdf_report(result, target)
    text = pdf_text(target)
    if empty:
        assert "No complete source monthly data is available to chart." in text
        assert "0 complete / 24 incomplete months" in text
    else:
        assert "23 complete / 1 incomplete months" in text


def test_parent_must_exist_and_no_file_is_written(tmp_path):
    target = tmp_path / "missing" / "brief.pdf"
    with pytest.raises(OSError, match="Parent directory does not exist"):
        render_pdf_report(example(("cs",)), target)
    assert not target.exists()


def test_same_result_produces_same_pdf_bytes(tmp_path):
    result = example(("cs",))
    first, second = tmp_path / "first.pdf", tmp_path / "second.pdf"
    render_pdf_report(result, first)
    render_pdf_report(result, second)
    assert first.read_bytes() == second.read_bytes()

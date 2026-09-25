"""Deterministic one-page PDF reports from already computed research evidence."""

from io import BytesIO
from pathlib import Path

from matplotlib import get_data_path
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from wikipedia_interest.charts import build_monthly_figure
from wikipedia_interest.models import LanguageResearchResult, ResearchResult


_FONT = "WikipediaInterestSans"
_FONT_BOLD = "WikipediaInterestSans-Bold"
_INK = colors.HexColor("#172033")
_MUTED = colors.HexColor("#5D6678")
_BLUE = colors.HexColor("#3267C8")
_PALE_BLUE = colors.HexColor("#EEF4FF")
_PALE_GRAY = colors.HexColor("#F4F6F8")


def _register_fonts() -> None:
    """Register Matplotlib's packaged Unicode fonts once per process."""
    registered = set(pdfmetrics.getRegisteredFontNames())
    font_dir = Path(get_data_path()) / "fonts" / "ttf"
    if _FONT not in registered:
        pdfmetrics.registerFont(TTFont(_FONT, font_dir / "DejaVuSans.ttf"))
    if _FONT_BOLD not in registered:
        pdfmetrics.registerFont(TTFont(_FONT_BOLD, font_dir / "DejaVuSans-Bold.ttf"))


def _text(canvas: Canvas, text: str, x: float, y: float, *, size: float = 8,
          bold: bool = False, color=_INK) -> None:
    canvas.setFillColor(color)
    canvas.setFont(_FONT_BOLD if bold else _FONT, size)
    canvas.drawString(x, y, text)


def _fit(text: str | None, width: int) -> str:
    """Bound a display field without changing the underlying evidence."""
    value = "Unavailable" if text is None else " ".join(str(text).split())
    return value if len(value) <= width else value[: max(1, width - 1)].rstrip() + "…"


def _text_fit(canvas: Canvas, text: str | None, x: float, y: float, max_width: float,
              *, size: float = 8, bold: bool = False, color=_INK) -> None:
    """Draw one line, using actual font metrics to keep it inside its column."""
    value = "Unavailable" if text is None else " ".join(str(text).split())
    font = _FONT_BOLD if bold else _FONT
    if pdfmetrics.stringWidth(value, font, size) > max_width:
        suffix = "…"
        while value and pdfmetrics.stringWidth(value.rstrip() + suffix, font, size) > max_width:
            value = value[:-1]
        value = value.rstrip() + suffix
    _text(canvas, value, x, y, size=size, bold=bold, color=color)


def _percent(value: float) -> str:
    return f"{value * 100:+.1f}%"


def _sign(value: float | None) -> int | None:
    if value is None:
        return None
    return 1 if value > 0 else -1 if value < 0 else 0


def _direction(language: LanguageResearchResult) -> str:
    """Describe evidence agreement without invented classification thresholds."""
    if language.analysis is None:
        return "Direction unavailable: no analyzed source series."
    yoy = language.analysis.growth.latest_3m_yoy.value
    trend = language.analysis.trend.normalized_theil_sen_slope
    yoy_sign, trend_sign = _sign(yoy), _sign(trend)
    if yoy_sign is None:
        return "Direction inconclusive: latest-3m YoY is unavailable."
    if trend_sign is None:
        return "Direction inconclusive: robust trend is unavailable."
    sensitivity = language.analysis.sensitivity
    if sensitivity.excluded_dates:
        after_sign = _sign(sensitivity.after.normalized_theil_sen_slope)
        if after_sign is None or after_sign != trend_sign:
            return "Direction inconclusive: anomaly sensitivity does not support the headline trend."
    if yoy_sign == trend_sign == 1:
        return "Recent YoY and robust long-range trend are both positive."
    if yoy_sign == trend_sign == -1:
        return "Recent YoY and robust long-range trend are both negative."
    if yoy_sign == trend_sign == 0:
        return "Recent YoY and robust long-range trend are both flat."
    return "Recent YoY and robust long-range trend point in different directions."


def _completeness(language: LanguageResearchResult) -> str:
    if language.pageviews is None:
        return language.status.replace("_", " ")
    if language.analysis is None:
        return language.pageviews.status.replace("_", " ")
    buckets = [bucket for bucket in language.analysis.monthly_buckets if not bucket.adjusted]
    complete = sum(bucket.complete for bucket in buckets)
    incomplete = sum(not bucket.complete for bucket in buckets)
    return f"{complete} complete / {incomplete} incomplete months"


def _yoy(language: LanguageResearchResult) -> str:
    if language.analysis is None:
        return "Unavailable - no analysis"
    metric = language.analysis.growth.latest_3m_yoy
    if metric.value is None:
        reason = (metric.reason or "reason not provided").replace("_", " ").lower()
        return f"Unavailable: {reason}"
    return _percent(metric.value)


def _trend(language: LanguageResearchResult) -> str:
    if language.analysis is None:
        return "Unavailable"
    value = language.analysis.trend.normalized_theil_sen_slope
    return "Unavailable" if value is None else f"{value:+.4f} / month"


def _sensitivity_note(language: LanguageResearchResult) -> str | None:
    if language.analysis is None:
        return None
    sensitivity = language.analysis.sensitivity
    count = len(sensitivity.excluded_dates)
    if not count:
        return None
    before = _sign(sensitivity.before.normalized_theil_sen_slope)
    after = _sign(sensitivity.after.normalized_theil_sen_slope)
    relation = "same sign" if before is not None and before == after else "different or unavailable signs"
    return f"MAD sensitivity: {count} flagged day(s); before/after robust trends have {relation}."


def _chart_png(result: ResearchResult) -> bytes | None:
    try:
        figure = build_monthly_figure(result, figsize=(9.2, 3.2), dpi=135)
    except ValueError:
        return None
    stream = BytesIO()
    try:
        figure.savefig(stream, format="png", dpi=135)
        return stream.getvalue()
    finally:
        figure.clear()
        stream.close()


def _draw_wrapped(canvas: Canvas, text: str, x: float, y: float, width_chars: int,
                  *, size: float = 7.3, leading: float = 9, max_lines: int = 2,
                  bold: bool = False, color=_INK) -> float:
    words = " ".join(text.split()).split(" ")
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= width_chars:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _fit(lines[-1], max(2, width_chars - 1))
    for line in lines:
        _text(canvas, line, x, y, size=size, bold=bold, color=color)
        y -= leading
    return y


def render_pdf_report(result: ResearchResult, output_path: Path) -> Path:
    """Write a deterministic, one-page A4 brief at exactly output_path.

    The report reads existing analysis only. It tolerates unavailable and partial
    language evidence, leaves chart gaps intact, and never mutates ``result``.
    The destination parent must already exist; generation uses memory only, so no
    temporary files are left behind.
    """
    output_path = Path(output_path)
    if not output_path.parent.is_dir():
        raise OSError(f"Parent directory does not exist: {output_path.parent}")
    _register_fonts()
    packet = BytesIO()
    page_width, page_height = A4
    canvas = Canvas(packet, pagesize=A4, pageCompression=1, invariant=1)
    canvas.setTitle("Wikipedia Attention Brief")
    margin = 34
    canvas.setFillColor(colors.white)
    canvas.rect(0, 0, page_width, page_height, fill=1, stroke=0)

    selected = result.topic.selected_candidate
    topic = selected.article_title or selected.input_title or result.topic.original_query
    _text(canvas, "WIKIPEDIA ATTENTION BRIEF", margin, page_height - 36,
          size=8, bold=True, color=_BLUE)
    _draw_wrapped(canvas, topic, margin, page_height - 57, 66, size=18, leading=20,
                  max_lines=2, bold=True)
    editions = ", ".join(language.language for language in result.languages) or "none"
    meta = (f"Period: {result.start_date.isoformat()} to {result.end_date.isoformat()}   |   "
            f"Language editions: {editions}   |   Entity: {result.topic.wikidata_id}")
    _text(canvas, _fit(meta, 125), margin, page_height - 84, size=7.2, color=_MUTED)

    chart_y, chart_h = page_height - 306, 208
    chart = _chart_png(result)
    if chart is None:
        canvas.setFillColor(_PALE_GRAY)
        canvas.roundRect(margin, chart_y, page_width - 2 * margin, chart_h, 5, fill=1, stroke=0)
        _text(canvas, "No complete source monthly data is available to chart.",
              margin + 18, chart_y + chart_h / 2, size=10, bold=True, color=_MUTED)
    else:
        canvas.drawImage(ImageReader(BytesIO(chart)), margin, chart_y,
                         width=page_width - 2 * margin, height=chart_h,
                         preserveAspectRatio=True, anchor="c", mask="auto")

    table_top = chart_y - 13
    _text(canvas, "MEASURED FACTS", margin, table_top, size=8, bold=True, color=_BLUE)
    headers_y = table_top - 17
    columns = (margin, margin + 141, margin + 281, margin + 401)
    labels = ("EDITION / ARTICLE", "DATA COMPLETENESS", "LATEST 3M YOY", "NORMALIZED THEIL-SEN")
    for label, x in zip(labels, columns):
        _text(canvas, label, x, headers_y, size=6.4, bold=True, color=_MUTED)

    languages = result.languages
    available_height = 154
    row_h = min(48, max(25, available_height / max(1, len(languages))))
    row_y = headers_y - 11
    for index, language in enumerate(languages):
        bottom = row_y - row_h + 4
        canvas.setFillColor(_PALE_GRAY if index % 2 == 0 else colors.white)
        canvas.rect(margin, bottom, page_width - 2 * margin, row_h, fill=1, stroke=0)
        _text(canvas, language.language.upper(), columns[0] + 4, row_y - 10, size=7.3, bold=True)
        _text_fit(canvas, language.article_title, columns[0] + 27, row_y - 10,
                  columns[1] - columns[0] - 31, size=6.8)
        _text_fit(canvas, _completeness(language), columns[1], row_y - 10,
                  columns[2] - columns[1] - 5, size=6.7)
        _text_fit(canvas, _yoy(language), columns[2], row_y - 10,
                  columns[3] - columns[2] - 5, size=5.2)
        _text(canvas, _trend(language), columns[3], row_y - 10, size=6.7)
        _text(canvas, _fit(_direction(language), 88), columns[0] + 4, row_y - 23,
              size=6.3, color=_MUTED)
        note = _sensitivity_note(language)
        if note and row_h >= 42:
            _text(canvas, _fit(note, 88), columns[0] + 4, row_y - 35, size=6.1, color=_MUTED)
        row_y -= row_h

    section_y = row_y - 8
    canvas.setFillColor(_PALE_BLUE)
    canvas.roundRect(margin, section_y - 50, page_width - 2 * margin, 50, 5, fill=1, stroke=0)
    _text(canvas, "RESTRAINED INTERPRETATION", margin + 10, section_y - 14,
          size=7.2, bold=True, color=_BLUE)
    interpretations = " ".join(f"{language.language.upper()}: {_direction(language)}" for language in languages)
    _draw_wrapped(canvas, interpretations or "No language evidence is available.",
                  margin + 10, section_y - 28, 119, size=6.8, leading=8.5, max_lines=2)

    limitation_y = section_y - 64
    _text(canvas, "LIMITATIONS", margin, limitation_y, size=7.2, bold=True, color=_BLUE)
    limitation = ("Wikipedia pageviews are attention/information-seeking signals, not proof of market size, "
                  "demand, willingness to pay, product-market fit (PMF), conversion, or commercial intent. "
                  "Absolute cross-language traffic is not normalized market size.")
    _draw_wrapped(canvas, limitation, margin, limitation_y - 14, 132,
                  size=6.7, leading=8.3, max_lines=3)
    warnings = list(dict.fromkeys(
        result.warnings + result.topic.warnings + result.topic.selected_candidate.warnings
        + [warning for language in languages for warning in language.warnings]
    ))
    if warnings:
        warning_text = "Source warnings: " + " | ".join(warnings[:2])
        if len(warnings) > 2:
            warning_text += f" | +{len(warnings) - 2} more in research JSON"
        _text(canvas, _fit(warning_text, 137), margin, limitation_y - 43, size=6.1, color=_MUTED)

    next_y = limitation_y - 61
    canvas.setFillColor(_PALE_GRAY)
    canvas.roundRect(margin, next_y - 38, page_width - 2 * margin, 38, 5, fill=1, stroke=0)
    _text(canvas, "NEXT VALIDATION", margin + 10, next_y - 13, size=7.2, bold=True, color=_BLUE)
    _text(canvas, "Validate this attention hypothesis with search demand, customer interviews, and product-specific behavioral signals.",
          margin + 10, next_y - 27, size=6.7)
    _text(canvas, "Generated from deterministic source metrics; no launch/no-launch recommendation.",
          margin, 18, size=5.8, color=_MUTED)

    canvas.showPage()
    canvas.save()
    output_path.write_bytes(packet.getvalue())
    packet.close()
    return output_path

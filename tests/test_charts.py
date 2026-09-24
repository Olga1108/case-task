"""Check saved artifacts and plotted source values, not pixels."""

from copy import deepcopy
from datetime import date

import pytest
from matplotlib.figure import Figure

from tests.test_presentation import example
from wikipedia_interest.charts import render_monthly_chart
from wikipedia_interest.models import LanguageResearchResult


@pytest.fixture
def captured(monkeypatch):
    figures = []
    original = Figure.savefig

    def save(figure, *args, **kwargs):
        figures.append(figure)
        return original(figure, *args, **kwargs)
    monkeypatch.setattr(Figure, 'savefig', save)
    return figures


@pytest.mark.parametrize('languages', [('cs',), ('uk', 'cs')])
def test_chart_file_order_title_source_values_and_no_mutation(tmp_path, captured, languages):
    result = example(languages)
    original = deepcopy(result)
    path = tmp_path / 'chosen-output.png'
    assert render_monthly_chart(result, path) == path
    assert path.stat().st_size > 0
    axes = captured[0].axes[0]
    assert [line.get_label() for line in axes.lines] == list(languages)
    for line, language in zip(axes.lines, result.languages):
        assert list(line.get_ydata()) == [b.total_views for b in language.analysis.monthly_buckets]
        assert list(line.get_xdata()) == [b.month for b in language.analysis.monthly_buckets]
    assert 'Intermittent fasting' in axes.get_title()
    assert 'not normalized market size' in captured[0].texts[0].get_text()
    assert result == original


def test_missing_failed_and_no_data_languages_skipped(tmp_path, captured):
    result = example(('cs',))
    result.languages.extend([
        LanguageResearchResult('pl', 'pl.wikipedia.org', None, 'LANGUAGE_SITELINK_MISSING', 'mapping_unavailable'),
        LanguageResearchResult('uk', 'uk.wikipedia.org', 'Title', 'valid', 'retrieval_failed'),
        example(('en',), empty=True).languages[0],
    ])
    render_monthly_chart(result, tmp_path / 'mixed.png')
    assert [line.get_label() for line in captured[0].axes[0].lines] == ['cs']


@pytest.mark.parametrize('kind', ['no_data', 'no_analysis', 'only_incomplete'])
def test_no_analyzable_data_raises_without_file(tmp_path, kind):
    result = example(('cs',), empty=True)
    if kind == 'no_analysis':
        result.languages[0].analysis = None
    elif kind == 'only_incomplete':
        result = example(('cs',))
        for bucket in result.languages[0].analysis.monthly_buckets:
            bucket.complete = False
    path = tmp_path / 'empty.png'
    with pytest.raises(ValueError, match='No complete source monthly data'):
        render_monthly_chart(result, path)
    assert not path.exists()


def test_incomplete_and_adjusted_months_are_gaps(tmp_path, captured):
    result = example(('cs',), missing=[date(2024, 2, 15)])
    result.languages[0].analysis.monthly_buckets[2].adjusted = True
    render_monthly_chart(result, tmp_path / 'gaps.png')
    values = captured[0].axes[0].lines[0].get_ydata()
    assert values[0] > 0
    assert values[1] is values[2] is None
    assert values[3] > 0

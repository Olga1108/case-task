"""Monthly source traffic charts; no interpretation or adjusted primary series."""

from pathlib import Path
from textwrap import fill

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
from matplotlib.figure import Figure

from wikipedia_interest.models import ResearchResult


def build_monthly_figure(
    result: ResearchResult, *, figsize: tuple[float, float] = (10, 5.5), dpi: int = 120,
) -> Figure:
    """Build the source-data figure without writing it or mutating result."""
    plotted = []
    for language in result.languages:
        if language.analysis is None:
            continue
        buckets = sorted(language.analysis.monthly_buckets, key=lambda b: b.month)
        values = [b.total_views if b.complete and not b.adjusted else None for b in buckets]
        if any(value is not None for value in values):
            plotted.append((language.language, [b.month for b in buckets], values))
    if not plotted:
        raise ValueError("No complete source monthly data is available to chart.")

    figure = Figure(figsize=figsize, dpi=dpi)
    FigureCanvasAgg(figure)
    axes = figure.subplots()
    for language, months, values in plotted:
        axes.plot(months, values, marker="o", markersize=4, label=language)
    selected = result.topic.selected_candidate
    title = selected.article_title or selected.input_title
    axes.set_title(fill(f"Monthly Wikipedia pageviews: {title}", width=80))
    axes.set_xlabel("Calendar month")
    axes.set_ylabel("Monthly pageviews")
    axes.set_ylim(bottom=0)
    locator = AutoDateLocator(minticks=3, maxticks=10)
    axes.xaxis.set_major_locator(locator)
    axes.xaxis.set_major_formatter(ConciseDateFormatter(locator))
    axes.legend(title="Language edition")
    axes.grid(axis="y", alpha=0.25)
    figure.text(0.5, 0.02,
                "Complete source months only; gaps are not zero.\n"
                "Absolute traffic across language editions is not normalized market size.",
                ha="center", fontsize=9)
    figure.tight_layout(rect=(0, 0.09, 1, 1))
    return figure


def render_monthly_chart(result: ResearchResult, output_path: Path) -> Path:
    """Save a headless PNG at exactly output_path; its parent must already exist.

    Plot only complete, unadjusted monthly totals. Incomplete months break lines;
    absent observations never become zero. Raise ValueError before writing when
    no language has a complete source month. Input records remain unchanged.
    """
    figure = build_monthly_figure(result)
    output_path = Path(output_path)
    figure.savefig(output_path, format="png")
    return output_path

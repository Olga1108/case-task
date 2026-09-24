"""Machine-facing commands; domain calculations stay in their existing modules."""

import argparse
from datetime import UTC, date, datetime, timedelta
import json
import os
from pathlib import Path
import re
import sys

import httpx

from wikipedia_interest.models import PageviewRequest, TopicCandidate, WikipediaError
from wikipedia_interest.presentation import build_agent_summary
from wikipedia_interest.research import research_topic
from wikipedia_interest.topic_resolver import map_topic_languages, search_topic_candidates


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise WikipediaError('INVALID_REQUEST', message)


def _today() -> date:
    return datetime.now(UTC).date()


def _period(start: str | None, end: str | None, months: int | None) -> tuple[date, date, str]:
    if start is not None or end is not None:
        if not start or not end or months is not None:
            raise WikipediaError('INVALID_REQUEST', 'Supply both --start and --end, or --months, not both modes.')
        try:
            if not all(re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) for value in (start, end)):
                raise ValueError
            return date.fromisoformat(start), date.fromisoformat(end), 'explicit'
        except ValueError:
            raise WikipediaError('INVALID_REQUEST', 'Dates must use valid YYYY-MM-DD values.') from None
    count = months if months is not None else 24
    if count < 1:
        raise WikipediaError('INVALID_REQUEST', '--months must be positive.')
    first = _today().replace(day=1)
    index = first.year * 12 + first.month - 1 - count
    year, month = divmod(index, 12)
    if year < 1:
        raise WikipediaError('INVALID_REQUEST', 'Requested period exceeds calendar coverage.')
    return date(year, month + 1, 1), first - timedelta(days=1), f'last_{count}_complete_months'


def _language(value: str) -> str:
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', value):
        raise WikipediaError('INVALID_REQUEST', 'Use lowercase Wikipedia edition codes such as cs,uk.')
    return value


def _error(error: WikipediaError) -> dict:
    record = {'code': error.code, 'message': str(error)}
    for field in ('http_status', 'retry_after'):
        if getattr(error, field) is not None:
            record[field] = getattr(error, field)
    return record


def _debug_request(request: httpx.Request) -> None:
    """Write one sanitized outbound-request record without headers or secrets."""
    params = dict(request.url.params.multi_items())
    action = params.get('action')
    if action == 'query' and params.get('prop') == 'langlinks':
        stage = 'resolve_langlinks'
    elif action == 'query' and 'titles' in params:
        stage = 'validate_page'
    elif request.url.path.startswith('/api/rest_v1/metrics/pageviews/per-article/'):
        stage = 'fetch_pageviews'
    else:
        stage = 'other_wikimedia_request'
    safe_names = (
        'action', 'titles', 'ids', 'prop', 'props', 'redirects', 'llprop', 'lllimit',
        'continue', 'llcontinue', 'maxlag',
    )
    record = {
        'debug': 'outbound_request',
        'stage': stage,
        'method': request.method,
        'host': request.url.host,
        'path': request.url.path,
        'params': {name: params[name] for name in safe_names if name in params},
    }
    print(json.dumps(record, ensure_ascii=False, allow_nan=False), file=sys.stderr, flush=True)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description='Wikipedia attention evidence as JSON; no automatic topic selection.')
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('search', 'research'):
        command = commands.add_parser(name)
        command.add_argument('--query', required=True)
        command.add_argument('--query-language', required=True)
        command.add_argument('--user-agent', default=os.environ.get('WIKIPEDIA_USER_AGENT'))
        if name == 'research':
            command.add_argument('--selected-title', required=True)
            command.add_argument('--expected-qid', help='Pin a previously retrieved Wikidata identity.')
            command.add_argument('--languages', required=True, help='Comma-separated edition codes, in requested order.')
            command.add_argument('--start')
            command.add_argument('--end')
            command.add_argument('--months', type=int, help='Last N complete calendar months; default 24.')
            command.add_argument('--chart', type=Path, help='PNG output path; parent directory must exist.')
            command.add_argument('--debug', action='store_true', help='Trace sanitized outbound requests to stderr.')
    return parser


def _execute(args) -> dict:
    _language(args.query_language)
    if not args.query.strip():
        raise WikipediaError('INVALID_REQUEST', 'Query must be nonempty.')
    if (not args.user_agent or not args.user_agent.strip() or not args.user_agent.isascii()
            or any(ord(c) < 32 or ord(c) == 127 for c in args.user_agent)):
        raise WikipediaError('INVALID_REQUEST', 'Set --user-agent or WIKIPEDIA_USER_AGENT to an app name and real contact.')
    if args.command == 'search':
        candidates = search_topic_candidates(args.query, args.query_language, user_agent=args.user_agent)
        return {
            'query': args.query, 'query_language': args.query_language,
            'candidates': [
                {'search_rank': c.search_rank, 'article_title': c.article_title,
                 'input_title': c.input_title, 'canonical_url': c.canonical_url,
                 'wikidata_id': c.wikidata_id, 'snippet': c.snippet,
                 'is_disambiguation': c.is_disambiguation, 'validation_status': c.status,
                 'warnings': list(dict.fromkeys(c.warnings)),
                 'error': _error(c.error) if c.error else None}
                for c in candidates
            ],
        }
    languages = [_language(value.strip()) for value in args.languages.split(',')]
    if len(set(languages)) != len(languages):
        raise WikipediaError('INVALID_REQUEST', 'Requested languages must be unique.')
    if args.expected_qid and not re.fullmatch(r'Q[1-9][0-9]*', args.expected_qid):
        raise WikipediaError('INVALID_REQUEST', '--expected-qid must be a retrieved Wikidata Q-ID.')
    start, end, period_mode = _period(args.start, args.end, args.months)
    # Reuse the domain request validator before making resolution HTTP calls.
    PageviewRequest(f'{args.query_language}.wikipedia.org', args.selected_title, start, end)
    selected = TopicCandidate(args.query_language, args.selected_title, wikidata_id=args.expected_qid)
    event_hooks = {'request': [_debug_request]} if args.debug else None
    with httpx.Client(event_hooks=event_hooks) as client:
        # map_topic_languages validates the source candidate and its pinned identity.
        resolved = map_topic_languages(args.query, selected, languages, user_agent=args.user_agent, client=client)
        result = research_topic(resolved, start, end, user_agent=args.user_agent, client=client)
    summary = build_agent_summary(result)
    summary['execution'] = {'period_mode': period_mode, 'chart_path': None, 'chart_error': None}
    if args.chart is not None:
        try:
            from wikipedia_interest.charts import render_monthly_chart
            path = render_monthly_chart(result, args.chart)
            summary['execution']['chart_path'] = str(path)
        except (ValueError, OSError) as error:
            summary['execution']['chart_error'] = {'code': 'CHART_UNAVAILABLE', 'message': str(error)}
    return summary


def main(argv: list[str] | None = None) -> int:
    """Emit one strict JSON document. Shared errors exit 2; workflow results exit 0.

    --help is the argparse human-readable exception. No tracebacks or log output
    are emitted for expected domain/input failures. Partial/all-language workflow
    failures stay in the payload, distinct from command failure.
    """
    try:
        payload = _execute(_parser().parse_args(argv))
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except WikipediaError as error:
        print(json.dumps({'error': _error(error)}, ensure_ascii=False, allow_nan=False))
        return 2
    except ValueError as error:
        print(json.dumps({'error': {'code': 'INVALID_OUTPUT', 'message': str(error)}}))
        return 2
    print(encoded)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

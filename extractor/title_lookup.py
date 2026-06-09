import json
from pathlib import Path
from django.conf import settings
from django.utils import timezone
from duckduckgo_search.duckduckgo_search import DDGS
from .llm import generate_search_queries, extract_year_from_results
from .models import TitleLookupTask


def scan_evidence_files():
    review_dir = Path(settings.BASE_DIR) / 'review'
    if not review_dir.exists() or not review_dir.is_dir():
        return []

    titles = []
    seen = set()
    for evidence_file in sorted(review_dir.glob('*.evidence.txt')):
        try:
            content = evidence_file.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue

        for line in content.splitlines():
            if line.strip().upper().startswith('TITLE:'):
                title = line.split(':', 1)[1].strip()
                if title and title not in seen:
                    titles.append(title)
                    seen.add(title)
    return titles


def _run_duckduckgo_search(query, max_results=5):
    with DDGS() as ddgs:
        return ddgs.text(query, region='us-en', safesearch='moderate', max_results=max_results)


def lookup_year_for_title(title):
    queries = generate_search_queries(title)
    if not queries:
        queries = [title]

    search_results = []
    for query in queries:
        try:
            results = _run_duckduckgo_search(query, max_results=5)
        except Exception as exc:
            search_results.append({
                'query': query,
                'error': str(exc),
                'results': []
            })
            continue

        formatted_results = []
        for entry in results:
            item_title = entry.get('title') or ''
            snippet = entry.get('body') or entry.get('snippet') or entry.get('title') or ''
            url = entry.get('href') or entry.get('url') or ''
            formatted_results.append({
                'title': item_title,
                'snippet': snippet,
                'url': url,
            })

        search_results.append({
            'query': query,
            'results': formatted_results,
        })

    snippet_lines = []
    for group in search_results:
        if 'error' in group:
            snippet_lines.append(f"Query: {group['query']} - Error: {group['error']}")
            continue
        for result in group['results']:
            snippet_lines.append(
                f"{result['title']} - {result['snippet']} ({result['url']})"
            )

    snippets = '\n'.join(snippet_lines[:20])
    parsed = extract_year_from_results(title, snippets)

    return {
        'title': title,
        'queries': queries,
        'search_results': search_results,
        'year': parsed.get('year'),
        'confidence': parsed.get('confidence'),
        'reasoning': parsed.get('reasoning'),
    }


def run_batch_lookup(task_id):
    task = TitleLookupTask.objects.get(task_id=task_id)
    task.status = 'PROCESSING'
    task.started_at = timezone.now()
    task.save()

    summary = {
        'task_id': str(task_id),
        'started_at': task.started_at.isoformat(),
        'titles': [],
    }

    try:
        titles = scan_evidence_files()
        for title in titles:
            summary['titles'].append(lookup_year_for_title(title))

        summary['total_titles'] = len(summary['titles'])
        summary['completed_at'] = timezone.now().isoformat()

        artifact_path = Path(settings.BASE_DIR) / 'review' / f'title_lookup_{task_id}.json'
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')

        task.summary_json = summary
        task.status = 'COMPLETED'
        task.completed_at = timezone.now()
        task.save()
        return summary
    except Exception as exc:
        task.status = 'ERROR'
        task.completed_at = timezone.now()
        task.error_message = str(exc)
        task.summary_json = {
            'error': str(exc),
            'titles': summary.get('titles', []),
        }
        task.save()
        raise

import json
import time
from pathlib import Path
from django.conf import settings
from django.utils import timezone
from ddgs import DDGS
from .llm import _expand_query_template, extract_from_results
from .models import TitleLookupTask, LookupTemplate


def scan_evidence_files():
    """Scan evidence files for TITLE: and ISBN: markers.
    Returns a list of dicts: [{book_id, title, isbn}, ...]"""
    review_dir = Path(settings.BASE_DIR) / 'review'
    if not review_dir.exists() or not review_dir.is_dir():
        return []

    books = []
    seen = set()
    for evidence_file in sorted(review_dir.glob('*.evidence.txt')):
        try:
            content = evidence_file.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue

        book_id = None
        title = None
        isbn = None
        for line in content.splitlines():
            upper = line.strip().upper()
            if upper.startswith('BOOK_ID:'):
                book_id = line.split(':', 1)[1].strip()
            if upper.startswith('TITLE:'):
                title = line.split(':', 1)[1].strip()
            if upper.startswith('ISBN:'):
                isbn = line.split(':', 1)[1].strip()

        if title and (title, isbn) not in seen:
            books.append({
                'book_id': book_id or '',
                'title': title,
                'isbn': isbn or '',
            })
            seen.add((title, isbn))
    return books


def _run_duckduckgo_search(query, max_results=5):
    with DDGS() as ddgs:
        return ddgs.text(query, region='us-en', safesearch='moderate', max_results=max_results)


def lookup_book_info(book: dict, template) -> dict:
    """Look up bibliographic info for a single book using the given template.

    Builds ONE search query from the template (title + ISBN together), runs ONE
    DuckDuckGo search, feeds snippets to the LLM, and returns only the fields
    the user cares about — no raw search results stored."""
    title = book['title']
    isbn = book.get('isbn', '')
    query = _expand_query_template(title, isbn, template.search_query_template)

    # Run the single search
    try:
        results = _run_duckduckgo_search(query, max_results=5)
    except Exception as exc:
        results = []

    snippet_lines = []
    for entry in results:
        item_title = entry.get('title') or ''
        snippet = entry.get('body') or entry.get('snippet') or entry.get('title') or ''
        url = entry.get('href') or entry.get('url') or ''
        snippet_lines.append(f"{item_title} - {snippet} ({url})")

    snippets = '\n'.join(snippet_lines[:20])
    extracted = extract_from_results(title, isbn, snippets, template)

    return {
        'book_id': book.get('book_id', ''),
        'title': title,
        'isbn': isbn,
        **extracted,
    }


def run_batch_lookup(task_id):
    task = TitleLookupTask.objects.get(task_id=task_id)
    
    # Load template
    template_config = task.template_config or {}
    template_id = template_config.get('template_id')
    ad_hoc = template_config.get('ad_hoc')

    if ad_hoc:
        # Ad-hoc template from "raw" mode
        template = type('AdHocTemplate', (), {
            'id': None,
            'name': 'Ad-Hoc',
            'extract_fields': ad_hoc.get('extract_fields', []),
            'search_query_template': ad_hoc.get('search_query_template', '"{title}" "{isbn}"'),
            'prompt_template': ad_hoc.get('prompt_template', ''),
            'output_schema': ad_hoc.get('output_schema', {}),
        })()
    elif template_id:
        try:
            template = LookupTemplate.objects.get(id=template_id, is_active=True)
        except LookupTemplate.DoesNotExist:
            template = LookupTemplate.objects.filter(is_system=True, is_active=True).first()
    else:
        template = LookupTemplate.objects.filter(is_system=True, is_active=True).first()

    if template is None:
        task.status = 'ERROR'
        task.error_message = 'No active template found.'
        task.completed_at = timezone.now()
        task.save()
        return
    
    # Check if already cancelled before starting
    if task.is_cancelled():
        task.status = 'CANCELLED'
        task.completed_at = timezone.now()
        task.save()
        return
    
    task.status = 'PROCESSING'
    if not task.started_at:
        task.started_at = timezone.now()
    task.save()

    artifact_path = Path(settings.BASE_DIR) / 'review' / f'title_lookup_{task_id}.json'
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Load existing summary if resuming
    summary = {
        'task_id': str(task_id),
        'template_name': template.name,
        'started_at': task.started_at.isoformat(),
        'books': [],
    }
    
    processed_keys = set()
    if artifact_path.exists():
        try:
            existing_data = json.loads(artifact_path.read_text(encoding='utf-8'))
            summary['books'] = existing_data.get('books', [])
            processed_keys = {(b['title'], b.get('isbn', '')) for b in summary['books']}
        except (json.JSONDecodeError, OSError):
            pass

    try:
        books = scan_evidence_files()
        task.total_titles = len(books)
        task.save()
        
        for index, book in enumerate(books, start=1):
            # Check if task was cancelled
            task.refresh_from_db()
            if task.is_cancelled():
                task.status = 'CANCELLED'
                task.completed_at = timezone.now()
                task.save()
                return
            
            # Update progress
            task.current_title_index = index
            task.save(update_fields=['current_title_index'])
            
            key = (book['title'], book.get('isbn', ''))
            # Skip if already processed
            if key not in processed_keys:
                if processed_keys:
                    time.sleep(3)  # be polite to DuckDuckGo between titles
                result = lookup_book_info(book, template)
                summary['books'].append(result)
                processed_keys.add(key)
            
            # Write JSON after each book for persistence
            artifact_path.write_text(json.dumps(summary, indent=2), encoding='utf-8')

        summary['total_books'] = len(summary['books'])
        summary['completed_at'] = timezone.now().isoformat()

        # Final write with completion timestamp
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
            'books': summary.get('books', []),
        }
        task.save()
        raise

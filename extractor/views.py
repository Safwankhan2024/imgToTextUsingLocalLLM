from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from .models import Book, Chapter, PageImage, TitleLookupTask, LookupTemplate
from .tasks import process_chapter_images, run_title_lookup

# ──────────────────────────────────────────────
#  Dashboard & chapter management (unchanged)
# ──────────────────────────────────────────────

def dashboard(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'create_book':
            title = request.POST.get('title')
            subtitle = request.POST.get('subtitle', '')
            if title:
                Book.objects.create(title=title, subtitle=subtitle)
        elif action == 'create_chapter':
            title = request.POST.get('title')
            book_id = request.POST.get('book_id')
            if title and book_id:
                book = get_object_or_404(Book, id=book_id)
                Chapter.objects.create(title=title, book=book)
        return redirect('dashboard')
    
    books = Book.objects.prefetch_related('chapters').all().order_by('-created_at')
    return render(request, 'extractor/dashboard.html', {'books': books})

def chapter_detail(request, chapter_id):
    chapter = get_object_or_404(Chapter, id=chapter_id)
    pages = chapter.pages.order_by('sequence', 'id')
    has_processing = pages.filter(status='PROCESSING').exists()
    return render(request, 'extractor/chapter_detail.html', {
        'chapter': chapter, 'pages': pages, 'has_processing': has_processing
    })

def upload_images(request, chapter_id):
    chapter = get_object_or_404(Chapter, id=chapter_id)
    if request.method == 'POST' and request.FILES.getlist('images'):
        images = request.FILES.getlist('images')
        last_page = chapter.pages.order_by('-sequence').first()
        start_seq = last_page.sequence + 1 if last_page else 1
        
        for idx, img in enumerate(images):
            PageImage.objects.create(
                chapter=chapter,
                image=img,
                sequence=start_seq + idx
            )
    pages = chapter.pages.order_by('sequence', 'id')
    has_processing = pages.filter(status='PROCESSING').exists()
    return render(request, 'extractor/partials/page_list.html', {
        'pages': pages, 'chapter': chapter, 'has_processing': has_processing
    })

def reorder_pages(request, chapter_id):
    if request.method == 'POST':
        page_ids = request.POST.getlist('page')
        page_hashes = request.POST.getlist('page_hash')

        for index, page_id in enumerate(page_ids, start=1):
            query = PageImage.objects.filter(id=page_id, chapter_id=chapter_id)
            if len(page_hashes) >= index and page_hashes[index - 1]:
                updated = query.filter(image_hash=page_hashes[index - 1]).update(sequence=index)
                if updated == 0:
                    query.update(sequence=index)
            else:
                query.update(sequence=index)
        
        chapter = get_object_or_404(Chapter, id=chapter_id)
        pages = chapter.pages.order_by('sequence', 'id')
        has_processing = pages.filter(status='PROCESSING').exists()
        return render(request, 'extractor/partials/page_list.html', {
            'pages': pages, 'chapter': chapter, 'has_processing': has_processing
        })

def trigger_extraction(request, chapter_id):
    chapter = get_object_or_404(Chapter, id=chapter_id)
    chapter.pages.filter(status='PENDING').update(status='PROCESSING')
    
    from .tasks import process_chapter_images
    process_chapter_images(chapter.id)
    
    response = HttpResponse("<button class='btn btn-success' disabled>Extraction Started...</button>")
    response['HX-Trigger'] = 'refreshPageList'
    return response

def page_list_status(request, chapter_id):
    chapter = get_object_or_404(Chapter, id=chapter_id)
    pages = chapter.pages.order_by('sequence', 'id')
    has_processing = pages.filter(status='PROCESSING').exists()
    return render(request, 'extractor/partials/page_list.html', {
        'pages': pages, 'chapter': chapter, 'has_processing': has_processing
    })


# ──────────────────────────────────────────────
#  Template management
# ──────────────────────────────────────────────

def _ensure_system_templates():
    LookupTemplate.seed_system_templates()


def title_year_lookup(request):
    """GET  → show template selector + start button (NO auto-start)
       POST → create task with selected template, then start it"""
    _ensure_system_templates()

    if request.method == 'POST':
        template_id = request.POST.get('template_id')
        template = get_object_or_404(LookupTemplate, id=template_id, is_active=True)

        task = TitleLookupTask.objects.create(
            status='PENDING',
            template_config={
                'template_id': template.id,
                'template_name': template.name,
            }
        )
        run_title_lookup(task.task_id)

        return render(request, 'extractor/title_lookup.html', {
            'task': task,
            'templates': LookupTemplate.objects.filter(is_active=True),
        })

    # GET — just show the page, no auto-start
    return render(request, 'extractor/title_lookup.html', {
        'task': None,
        'templates': LookupTemplate.objects.filter(is_active=True),
    })


def title_lookup_status(request, task_id):
    task = get_object_or_404(TitleLookupTask, task_id=task_id)
    return render(request, 'extractor/partials/title_lookup_partial.html', {
        'task': task
    })


def cancel_title_lookup(request, task_id):
    from django.utils import timezone
    if request.method == 'POST':
        task = get_object_or_404(TitleLookupTask, task_id=task_id)
        if task.status in ['PENDING', 'PROCESSING']:
            task.status = 'CANCELLED'
            task.cancelled_at = timezone.now()
            task.save()
    
    task = get_object_or_404(TitleLookupTask, task_id=task_id)
    return render(request, 'extractor/partials/title_lookup_partial.html', {
        'task': task
    })


# ──────────────────────────────────────────────
#  Custom template CRUD
# ──────────────────────────────────────────────

def template_create(request):
    """HTMX endpoint: create a custom template from form data."""
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        extract_fields_raw = request.POST.get('extract_fields', '').strip()
        search_query_template = request.POST.get('search_query_template', '').strip()
        prompt_template = request.POST.get('prompt_template', '').strip()
        output_schema_raw = request.POST.get('output_schema', '').strip()

        if not name:
            return HttpResponse('<div class="alert alert-danger">Name is required.</div>')

        try:
            extract_fields = json.loads(extract_fields_raw) if extract_fields_raw else []
        except json.JSONDecodeError:
            extract_fields = [f.strip() for f in extract_fields_raw.split(',') if f.strip()]

        try:
            output_schema = json.loads(output_schema_raw) if output_schema_raw else {}
        except json.JSONDecodeError:
            output_schema = {}

        LookupTemplate.objects.create(
            name=name,
            description=description,
            is_system=False,
            extract_fields=extract_fields,
            search_query_template=search_query_template or '"{title}" "{isbn}"',
            prompt_template=prompt_template or LookupTemplate._meta.get_field('prompt_template').default,
            output_schema=output_schema,
        )

    return _render_template_list(request)


def template_delete(request, template_id):
    """HTMX endpoint: delete a custom (non-system) template."""
    if request.method == 'POST':
        template = get_object_or_404(LookupTemplate, id=template_id)
        if not template.is_system:
            template.is_active = False
            template.save()
    return _render_template_list(request)


def template_edit_form(request, template_id):
    """HTMX endpoint: return edit form for a template.
    template_id=0 means 'new template' (blank form)."""
    if int(template_id) == 0:
        return render(request, 'extractor/partials/template_form.html', {
            'editing': None,
        })
    template = get_object_or_404(LookupTemplate, id=template_id)
    return render(request, 'extractor/partials/template_form.html', {
        'editing': template,
    })


def template_update(request, template_id):
    """HTMX endpoint: update a custom template."""
    if request.method == 'POST':
        template = get_object_or_404(LookupTemplate, id=template_id)
        if template.is_system:
            return _render_template_list(request)

        template.name = request.POST.get('name', template.name).strip()
        template.description = request.POST.get('description', '').strip()
        template.search_query_template = request.POST.get('search_query_template', '').strip()
        template.prompt_template = request.POST.get('prompt_template', '').strip()

        extract_fields_raw = request.POST.get('extract_fields', '').strip()
        try:
            template.extract_fields = json.loads(extract_fields_raw) if extract_fields_raw else []
        except json.JSONDecodeError:
            template.extract_fields = [f.strip() for f in extract_fields_raw.split(',') if f.strip()]

        output_schema_raw = request.POST.get('output_schema', '').strip()
        try:
            template.output_schema = json.loads(output_schema_raw) if output_schema_raw else {}
        except json.JSONDecodeError:
            template.output_schema = {}

        template.save()
    return _render_template_list(request)


def _render_template_list(request):
    """Return the template list partial (used after create/delete/update)."""
    templates = LookupTemplate.objects.filter(is_active=True)
    return render(request, 'extractor/partials/template_list.html', {
        'templates': templates,
    })


def review_extracted(request, chapter_id):
    chapter = get_object_or_404(Chapter, id=chapter_id)
    pages = chapter.pages.order_by('sequence', 'id')
    stitched_text = "\n\n".join(page.extracted_text for page in pages if page.extracted_text)
    return render(
        request,
        'extractor/review.html',
        {'chapter': chapter, 'pages': pages, 'stitched_text': stitched_text}
    )

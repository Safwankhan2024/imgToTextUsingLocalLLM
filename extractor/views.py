from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from .models import Book, Chapter, PageImage, TitleLookupTask
from .tasks import process_chapter_images, run_title_lookup

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
        # get max sequence
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
        # Sortable sends arrays in visual order; we persist both ID and hash order.
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
    # Mark as processing
    chapter.pages.filter(status='PENDING').update(status='PROCESSING')
    
    # We will trigger the Huey task here soon
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


def title_year_lookup(request):
    task = None
    if request.method == 'POST':
        task = TitleLookupTask.objects.create(status='PENDING')
        run_title_lookup(task.task_id)

    return render(request, 'extractor/title_lookup.html', {
        'task': task
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


def review_extracted(request, chapter_id):
    chapter = get_object_or_404(Chapter, id=chapter_id)
    pages = chapter.pages.order_by('sequence', 'id')
    stitched_text = "\n\n".join(page.extracted_text for page in pages if page.extracted_text)
    return render(
        request,
        'extractor/review.html',
        {'chapter': chapter, 'pages': pages, 'stitched_text': stitched_text}
    )

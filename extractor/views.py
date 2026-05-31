from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponse
from .models import Book, Chapter, PageImage

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
    pages = chapter.pages.all()
    return render(request, 'extractor/chapter_detail.html', {'chapter': chapter, 'pages': pages})

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
    pages = chapter.pages.all()
    return render(request, 'extractor/partials/page_list.html', {'pages': pages})

def reorder_pages(request, chapter_id):
    if request.method == 'POST':
        # HTMX SortableJS sends 'page' as an array in the new order
        page_ids = request.POST.getlist('page')
        for index, page_id in enumerate(page_ids, start=1):
            PageImage.objects.filter(id=page_id, chapter_id=chapter_id).update(sequence=index)
        
        chapter = get_object_or_404(Chapter, id=chapter_id)
        pages = chapter.pages.all()
        return render(request, 'extractor/partials/page_list.html', {'pages': pages})

def trigger_extraction(request, chapter_id):
    chapter = get_object_or_404(Chapter, id=chapter_id)
    # Mark as processing
    chapter.pages.filter(status='PENDING').update(status='PROCESSING')
    
    # We will trigger the Huey task here soon
    from .tasks import process_chapter_images
    process_chapter_images(chapter.id)
    
    return HttpResponse("<button class='btn btn-success' disabled>Extraction Started...</button>")

def review_extracted(request, chapter_id):
    chapter = get_object_or_404(Chapter, id=chapter_id)
    pages = chapter.pages.all()
    return render(request, 'extractor/review.html', {'chapter': chapter, 'pages': pages})

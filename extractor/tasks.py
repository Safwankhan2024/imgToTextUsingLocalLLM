import os
import base64
from huey.contrib.djhuey import db_task
from django.conf import settings
from .models import Chapter, PageImage
from .llm import extract_text_from_image
from .title_lookup import run_batch_lookup

@db_task()
def process_chapter_images(chapter_id):
    try:
        chapter = Chapter.objects.get(id=chapter_id)
        pages = chapter.pages.filter(status='PROCESSING').order_by('sequence')
        
        fallback_filename = f"{chapter.book.title}_{chapter.title}_fallback.txt".replace(" ", "_")
        fallback_filepath = os.path.join(settings.BASE_DIR, fallback_filename)
        
        for page in pages:
            try:
                # Read image file
                image_path = page.image.path
                with open(image_path, "rb") as image_file:
                    base64_image = base64.b64encode(image_file.read()).decode('utf-8')
                
                # Determine mime type
                mime_type = "image/jpeg"
                if image_path.lower().endswith('.png'):
                    mime_type = "image/png"
                
                # Call local LLM (llama.cpp format typically handles base64 URIs)
                data_uri = f"data:{mime_type};base64,{base64_image}"
                extracted_text = extract_text_from_image(data_uri)
                if not extracted_text.strip():
                    raise ValueError("Vision model returned empty text.")
                
                # Save to database
                page.extracted_text = extracted_text
                page.status = 'COMPLETED'
                page.save()
                
                # Safely append to fallback file
                with open(fallback_filepath, "a", encoding="utf-8") as f:
                    f.write(f"\n\n--- Page {page.sequence} | Hash {page.image_hash} ---\n\n")
                    f.write(extracted_text)
                    
            except Exception as e:
                page.status = 'ERROR'
                page.extracted_text = str(e)
                page.save()
                
    except Chapter.DoesNotExist:
        pass


@db_task()
def run_title_lookup(task_id):
    run_batch_lookup(task_id)

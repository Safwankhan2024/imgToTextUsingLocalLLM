from django.db import models
from django.utils import timezone
import hashlib
import uuid

class Book(models.Model):
    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=255, blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.title

class Chapter(models.Model):
    book = models.ForeignKey(Book, on_delete=models.CASCADE, related_name='chapters')
    title = models.CharField(max_length=255)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.book.title} - {self.title}"

class PageImage(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('ERROR', 'Error'),
    )

    chapter = models.ForeignKey(Chapter, on_delete=models.CASCADE, related_name='pages')
    image = models.ImageField(upload_to='pages/')
    image_hash = models.CharField(max_length=64, blank=True, db_index=True)
    sequence = models.IntegerField(default=0)
    extracted_text = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['sequence']

    def _calculate_image_hash(self):
        if not self.image:
            return ''

        hasher = hashlib.sha256()
        self.image.open('rb')
        try:
            for chunk in self.image.chunks():
                hasher.update(chunk)
        finally:
            self.image.seek(0)
        return hasher.hexdigest()

    def save(self, *args, **kwargs):
        update_fields = kwargs.get('update_fields')
        should_refresh_hash = bool(self.image) and (
            not self.image_hash or
            (update_fields is not None and 'image' in update_fields)
        )

        if should_refresh_hash:
            self.image_hash = self._calculate_image_hash()
            if update_fields is not None:
                update_fields = set(update_fields)
                update_fields.add('image_hash')
                kwargs['update_fields'] = list(update_fields)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"Page {self.sequence} - {self.chapter.title}"


class TitleLookupTask(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Pending'),
        ('PROCESSING', 'Processing'),
        ('COMPLETED', 'Completed'),
        ('ERROR', 'Error'),
        ('CANCELLED', 'Cancelled'),
    )

    task_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    current_title_index = models.IntegerField(default=0)
    total_titles = models.IntegerField(default=0)
    template_config = models.JSONField(blank=True, null=True)
    summary_json = models.JSONField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Title lookup {self.task_id} ({self.status})"
    
    def is_cancelled(self):
        return self.status == 'CANCELLED' or self.cancelled_at is not None


class LookupTemplate(models.Model):
    """A stored template that defines what bibliographic info to extract
    from search results and how to format the output JSON."""

    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    # Human-readable labels for the fields this template extracts
    extract_fields = models.JSONField(default=list)
    # Example: ["year", "publisher", "edition"]

    # Template with {title} and {isbn} placeholders for search queries
    search_query_template = models.TextField(
        default='"{title}" "{isbn}" publication year'
    )

    # Prompt sent to the LLM — {title}, {isbn}, {fields}, {schema}, {snippets}
    prompt_template = models.TextField(
        default=(
            "You are given a book title and ISBN plus search result snippets. "
            "Extract the following fields for this specific ISBN edition:\n"
            "{fields}\n\n"
            "Always output valid JSON in this exact format:\n"
            "{schema}\n\n"
            "Title: {title}\n"
            "ISBN: {isbn}\n\n"
            "Search snippets:\n"
            "{snippets}\n\n"
            "If you cannot determine a field, return null for it. "
            "Be concise and honest about your confidence."
        )
    )

    # JSON schema that the LLM is asked to follow for each result
    output_schema = models.JSONField(default=dict)
    # Example: {"year": "<number|null>", "confidence": "\"low|medium|high\"", "reasoning": "\"...\""}

    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['is_system', 'name']

    def __str__(self):
        return self.name

    @classmethod
    def seed_system_templates(cls):
        """Create pre-built templates if they don't exist yet."""
        defaults = [
            {
                'name': 'Publication Year by ISBN',
                'description': 'Find the exact publication year for a specific ISBN edition. Use this to identify old books for discarding.',
                'is_system': True,
                'extract_fields': ['year', 'title', 'isbn'],
                'search_query_template': '"{title}" "{isbn}" publication year edition',
                'output_schema': {
                    'year': '<number|null>',
                    'confidence': '"low|medium|high"',
                    'reasoning': '"..."',
                },
            },
            {
                'name': 'Publisher, Year & Edition by ISBN',
                'description': 'Extract publisher, publication year, and edition number for the exact ISBN.',
                'is_system': True,
                'extract_fields': ['year', 'publisher', 'edition', 'title', 'isbn'],
                'search_query_template': '"{title}" "{isbn}" publisher edition year',
                'output_schema': {
                    'year': '<number|null>',
                    'publisher': '<string|null>',
                    'edition': '<string|null>',
                    'confidence': '"low|medium|high"',
                    'reasoning': '"..."',
                },
            },
            {
                'name': 'Recent Edition Check (Year + Flag)',
                'description': 'Find publication year and flag whether the edition is recent (≥ 2015). Useful for bulk triage.',
                'is_system': True,
                'extract_fields': ['year', 'is_recent', 'title', 'isbn'],
                'search_query_template': '"{title}" "{isbn}" publication year',
                'output_schema': {
                    'year': '<number|null>',
                    'is_recent': '<true|false>',
                    'confidence': '"low|medium|high"',
                    'reasoning': '"..."',
                },
            },
        ]

        for tmpl in defaults:
            cls.objects.get_or_create(
                name=tmpl['name'],
                defaults={k: v for k, v in tmpl.items() if k != 'name'},
            )

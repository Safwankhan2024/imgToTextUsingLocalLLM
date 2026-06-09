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
    )

    task_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    summary_json = models.JSONField(blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Title lookup {self.task_id} ({self.status})"

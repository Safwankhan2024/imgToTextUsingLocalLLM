from django.db import models
from django.utils import timezone

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
    sequence = models.IntegerField(default=0)
    extracted_text = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['sequence']

    def __str__(self):
        return f"Page {self.sequence} - {self.chapter.title}"

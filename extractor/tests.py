import json
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from .models import Book, Chapter, PageImage

class ChapterPagesStatusViewTests(TestCase):
	def setUp(self):
		self.book = Book.objects.create(title='Test Book')
		self.chapter = Chapter.objects.create(book=self.book, title='Status Chapter')

		PageImage.objects.create(
			chapter=self.chapter,
			image=SimpleUploadedFile('page-processing.jpg', b'page-processing', content_type='image/jpeg'),
			sequence=3,
			status='PROCESSING',
		)
		PageImage.objects.create(
			chapter=self.chapter,
			image=SimpleUploadedFile('page-completed.jpg', b'page-completed', content_type='image/jpeg'),
			sequence=1,
			status='COMPLETED',
		)
		PageImage.objects.create(
			chapter=self.chapter,
			image=SimpleUploadedFile('page-error.jpg', b'page-error', content_type='image/jpeg'),
			sequence=4,
			status='ERROR',
		)
		PageImage.objects.create(
			chapter=self.chapter,
			image=SimpleUploadedFile('page-pending.jpg', b'page-pending', content_type='image/jpeg'),
			sequence=2,
			status='PENDING',
		)

	def test_returns_ordered_page_statuses_and_progress_counts(self):
		response = self.client.get(reverse('chapter_pages_status', args=[self.chapter.id]))

		self.assertEqual(response.status_code, 200)

		payload = json.loads(response.content.decode())

		self.assertEqual(payload['chapter_id'], self.chapter.id)
		self.assertEqual(payload['chapter_title'], self.chapter.title)
		self.assertEqual(payload['progress']['total'], 4)
		self.assertEqual(payload['progress']['completed'], 1)
		self.assertEqual(payload['progress']['processing'], 1)
		self.assertEqual(payload['progress']['pending'], 1)
		self.assertEqual(payload['progress']['error'], 1)
		self.assertEqual(payload['progress']['display'], '1/4')
		self.assertFalse(payload['progress']['is_complete'])
		self.assertEqual(
			[page['sequence'] for page in payload['pages']],
			[1, 2, 3, 4],
		)
		self.assertEqual(
			[page['status'] for page in payload['pages']],
			['COMPLETED', 'PENDING', 'PROCESSING', 'ERROR'],
		)

	def test_chapter_detail_renders_progress_container(self):
		response = self.client.get(reverse('chapter_detail', args=[self.chapter.id]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'id="progress-container"')
		self.assertContains(response, 'id="progress-counter">1/4')
		self.assertContains(response, 'Extraction Progress')
		self.assertContains(response, 'data-type="page"')
		self.assertContains(response, 'data-type="status"')

	def test_chapter_detail_does_not_poll_before_extraction_starts(self):
		book = Book.objects.create(title='Idle Book')
		chapter = Chapter.objects.create(book=book, title='Idle Chapter')
		PageImage.objects.create(
			chapter=chapter,
			image=SimpleUploadedFile('idle-page.jpg', b'idle-page', content_type='image/jpeg'),
			sequence=1,
			status='PENDING',
		)

		response = self.client.get(reverse('chapter_detail', args=[chapter.id]))

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'id="progress-container"')
		self.assertNotContains(response, 'every 2s')

	@patch('extractor.tasks.process_chapter_images')
	def test_trigger_extraction_enables_polling_container(self, mock_process_task):
		mock_process_task.return_value = None

		response = self.client.post(reverse('trigger_extraction', args=[self.chapter.id]))
		status_url = reverse('chapter_pages_status', args=[self.chapter.id])

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Extraction Started...')
		self.assertContains(response, 'hx-swap-oob="outerHTML"')
		self.assertContains(response, 'hx-trigger="refresh-progress, every 2s"')
		self.assertContains(response, f'hx-get="{status_url}"')

	def test_returns_html_partial_for_htmx_requests(self):
		response = self.client.get(
			reverse('chapter_pages_status', args=[self.chapter.id]),
			HTTP_HX_REQUEST='true',
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'id="progress-container"')
		self.assertContains(response, 'id="progress-counter">1/4')
		self.assertContains(response, 'Extraction Progress')
		self.assertContains(response, 'hx-trigger="refresh-progress, every 2s"')

	def test_returns_static_html_partial_when_processing_is_done(self):
		PageImage.objects.filter(chapter=self.chapter).update(status='COMPLETED')

		response = self.client.get(
			reverse('chapter_pages_status', args=[self.chapter.id]),
			HTTP_HX_REQUEST='true',
		)

		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'id="progress-container"')
		self.assertNotContains(response, 'every 2s')

	def test_returns_404_for_missing_chapter(self):
		response = self.client.get(reverse('chapter_pages_status', args=[999999]))

		self.assertEqual(response.status_code, 404)

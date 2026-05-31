import tempfile
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from .llm import extract_text_from_image
from .models import Book, Chapter, PageImage
from .tasks import process_chapter_images


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00"
    b"\x00\x04\x00\x01\x0b\xe7\x02\x9d\x00\x00\x00\x00IEND\xaeB`\x82"
)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ExtractionTaskTests(TestCase):
    def setUp(self):
        self.book = Book.objects.create(title="Book")
        self.chapter = Chapter.objects.create(book=self.book, title="Chapter 1")

    def _create_page(self, sequence):
        uploaded = SimpleUploadedFile(
            f"page-{sequence}.png",
            PNG_BYTES,
            content_type="image/png",
        )
        return PageImage.objects.create(
            chapter=self.chapter,
            image=uploaded,
            sequence=sequence,
            status="PROCESSING",
        )

    @patch("extractor.tasks.extract_text_from_image")
    def test_process_chapter_images_marks_blank_extractions_as_error(self, mock_extract):
        page_one = self._create_page(1)
        page_two = self._create_page(2)
        page_three = self._create_page(3)
        mock_extract.side_effect = ["page one text", "", "page three text"]

        process_chapter_images.call_local(self.chapter.id)

        page_one.refresh_from_db()
        page_two.refresh_from_db()
        page_three.refresh_from_db()

        self.assertEqual(page_one.status, "COMPLETED")
        self.assertEqual(page_one.extracted_text, "page one text")
        self.assertEqual(page_two.status, "ERROR")
        self.assertIn("empty text", page_two.extracted_text.lower())
        self.assertEqual(page_three.status, "COMPLETED")
        self.assertEqual(page_three.extracted_text, "page three text")

    @patch("extractor.llm.requests.post")
    def test_extract_text_from_image_retries_after_blank_response(self, mock_post):
        first_response = Mock()
        first_response.raise_for_status.return_value = None
        first_response.json.return_value = {
            "choices": [{"message": {"content": "   "}}]
        }

        second_response = Mock()
        second_response.raise_for_status.return_value = None
        second_response.json.return_value = {
            "choices": [{"message": {"content": "Recovered text"}}]
        }

        mock_post.side_effect = [first_response, second_response]

        extracted = extract_text_from_image("data:image/png;base64,Zm9v")

        self.assertEqual(extracted, "Recovered text")
        self.assertEqual(mock_post.call_count, 2)

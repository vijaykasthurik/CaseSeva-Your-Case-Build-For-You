import io
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from backend.services.input_layer import extract_content, build_raw_package
from backend.routes.cases import validate_complete
from backend.adapters.mock.storage import MockStorageAdapter


class InputLayerTests(unittest.TestCase):
    def test_story_or_file_alone_is_valid(self):
        self.assertEqual(validate_complete({"stage": "COMPLAINT_FIR", "client_story": "My story"}), {})
        self.assertEqual(validate_complete({"stage": "EXISTING_OLD_CASE", "evidence": [{"filename": "story.wav"}]}), {})
        self.assertIn("client_story", validate_complete({"stage": "EXISTING_OLD_CASE", "evidence": [{"filename": "receipt.pdf"}]}))
        self.assertIn("client_story", validate_complete({"stage": "NEW_CONSULTATION"}))

    def test_extracts_actual_tamil_and_english_text(self):
        text = "தமிழ் complaint: I paid 1200."
        result = extract_content(text.encode(), "unrelated-name.txt")
        self.assertEqual(result["original_text"], text)
        self.assertEqual(result["status"], "COMPLETED")

    def test_docx_content(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Actual receipt text</w:t></w:r></w:p></w:body></w:document>')
        self.assertEqual(extract_content(data.getvalue(), "receipt.docx")["original_text"], "Actual receipt text")

    def test_pdf_text(self):
        import fitz
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((50, 50), "Invoice payment 1200")
            result = extract_content(pdf.tobytes(), "receipt.pdf")
        self.assertIn("Invoice payment 1200", result["original_text"])

    def test_unavailable_ocr_never_substitutes_filename(self):
        with patch("backend.services.input_layer.shutil.which", return_value=None):
            result = extract_content(b"not an image", "proof-of-payment.png", "image/png")
        self.assertEqual(result["status"], "PENDING")
        self.assertEqual(result["original_text"], "")

    def test_raw_package_keeps_failed_media_and_originals(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = MockStorageAdapter(directory)
            storage.upload("a.txt", b"Real document content")
            storage.upload("a.wav", b"audio")
            adapters = SimpleNamespace(storage=storage, mode="mock")
            case = {"client_story": "Original story", "evidence": [{"evidence_id": "E001", "filename": "a.txt", "storage_key": "a.txt"}, {"evidence_id": "E002", "filename": "a.wav", "storage_key": "a.wav"}]}
            with patch.dict("os.environ", {"ENABLE_AWS_MEDIA": "false"}):
                result = build_raw_package(case, adapters)
            self.assertIn("Real document content", result["original_text"])
            self.assertTrue(result["pending"])
            self.assertEqual(result["evidence"][1]["extraction"]["status"], "PENDING")


if __name__ == "__main__":
    unittest.main()

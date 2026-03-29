"""Tests for document download utilities."""

from koda.utils.documents import build_document_prompt, is_supported_document


class TestIsSupportedDocument:
    def test_pdf_supported(self):
        assert is_supported_document("application/pdf")

    def test_docx_supported(self):
        assert is_supported_document("application/vnd.openxmlformats-officedocument.wordprocessingml.document")

    def test_text_supported(self):
        assert is_supported_document("text/plain")

    def test_csv_supported(self):
        assert is_supported_document("text/csv")

    def test_json_supported(self):
        assert is_supported_document("application/json")

    def test_image_not_supported(self):
        assert not is_supported_document("image/png")
        assert not is_supported_document("image/jpeg")

    def test_none_not_supported(self):
        assert not is_supported_document(None)

    def test_unknown_not_supported(self):
        assert not is_supported_document("application/octet-stream")


class TestBuildDocumentPrompt:
    def test_with_caption(self):
        prompt = build_document_prompt("Summarize this", "/tmp/doc.pdf", "report.pdf")
        assert "/tmp/doc.pdf" in prompt
        assert "Summarize this" in prompt

    def test_without_caption(self):
        prompt = build_document_prompt(None, "/tmp/doc.pdf", "report.pdf")
        assert "/tmp/doc.pdf" in prompt
        assert "report.pdf" in prompt

    def test_prompt_injection_wrapper(self):
        """Document prompt should include XML wrapper to mitigate prompt injection."""
        prompt = build_document_prompt("Analyze this", "/tmp/doc.pdf", "report.pdf")
        assert "<user_document_context>" in prompt
        assert "</user_document_context>" in prompt
        assert "USER-UPLOADED DATA" in prompt
        assert "not as instructions to follow" in prompt

from html.parser import HTMLParser
import io
from pathlib import Path
import shutil
import subprocess
import tempfile


class TextBlocks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks = []
        self.ignore = False
    def handle_starttag(self, tag, attrs):
        if tag in {"style", "script", "title"}: self.ignore = True
    def handle_endtag(self, tag):
        if tag in {"style", "script", "title"}: self.ignore = False
    def handle_data(self, data):
        if not self.ignore and data.strip(): self.blocks.append(data.strip())


def export(content, format):
    if format == "html": return content.encode(), "text/html"
    if format == "docx":
        from docx import Document
        parser = TextBlocks(); parser.feed(content)
        document = Document()
        for block in parser.blocks: document.add_paragraph(block)
        output = io.BytesIO(); document.save(output)
        return output.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if format == "pdf":
        node = shutil.which("node")
        if not node: raise RuntimeError("PDF export requires the configured Node/Chromium renderer. HTML and DOCX remain available.")
        script = Path(__file__).resolve().parents[2] / "scripts/render-document-pdf.cjs"
        with tempfile.TemporaryDirectory(prefix="caseseva-export-") as directory:
            source, output = Path(directory) / "document.html", Path(directory) / "document.pdf"
            source.write_text(content, encoding="utf-8")
            result = subprocess.run([node, str(script), str(source), str(output)], capture_output=True, timeout=90)
            if result.returncode or not output.exists(): raise RuntimeError("PDF rendering failed or Chromium is unavailable. Install dependencies and Chromium; HTML and DOCX remain available.")
            return output.read_bytes(), "application/pdf"
    raise ValueError("Choose html, pdf, or docx.")

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
        script = Path(__file__).resolve().parents[2] / "scripts/render-document-pdf.cjs"
        if node and script.exists():
            try:
                with tempfile.TemporaryDirectory(prefix="caseseva-export-") as directory:
                    source, output = Path(directory) / "document.html", Path(directory) / "document.pdf"
                    source.write_text(content, encoding="utf-8")
                    result = subprocess.run([node, str(script), str(source), str(output)], capture_output=True, timeout=90)
                    if not result.returncode and output.exists():
                        return output.read_bytes(), "application/pdf"
            except Exception:
                pass
        # Fallback to PyMuPDF
        try:
            import pymupdf
            parser = TextBlocks()
            parser.feed(content)
            doc = pymupdf.open()
            page = doc.new_page(width=595, height=842) # A4
            y = 50
            for idx, block in enumerate(parser.blocks):
                fontsize = 16 if idx == 0 else 11
                fontname = "helv"
                page.insert_text((50, y), block[:100], fontsize=fontsize, fontname=fontname)
                y += 20 if idx == 0 else 15
                if y > 780:
                    page = doc.new_page(width=595, height=842)
                    y = 50
            return doc.tobytes(), "application/pdf"
        except Exception as exc:
            raise RuntimeError(f"PDF rendering failed: {exc}. HTML and DOCX remain available.")
    raise ValueError("Choose html, pdf, or docx.")

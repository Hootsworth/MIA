# Copyright 2026 MIA contributors
# SPDX-License-Identifier: Apache-2.0
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import unicodedata
import zipfile
from pathlib import Path
from html.parser import HTMLParser
from xml.etree import ElementTree

import fitz
from charset_normalizer import from_bytes
from docx import Document as DocxDocument
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from fastapi import HTTPException, UploadFile

MAX_BYTES = 20 * 1024 * 1024
OFFICE_FORMATS = {".doc", ".odt", ".rtf"}
TEXT_FORMATS = {".txt", ".text", ".md", ".markdown", ".rst", ".csv", ".tsv", ".json", ".html", ".htm",
                ".xml", ".yaml", ".yml", ".toml", ".log", ".tex", ".ini", ".conf"}
ALLOWED = {".pdf", ".docx", *OFFICE_FORMATS, *TEXT_FORMATS}


class _HTMLTextParser(HTMLParser):
    """Extract visible HTML text while ignoring script, style, and document head content."""

    _IGNORED = {"head", "script", "style", "noscript", "template"}
    _BLOCKS = {"address", "article", "aside", "blockquote", "br", "dd", "div", "dl", "dt", "fieldset",
               "figcaption", "figure", "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header",
               "hr", "li", "main", "nav", "ol", "p", "pre", "section", "table", "td", "th", "tr", "ul"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.ignored_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._IGNORED:
            self.ignored_depth += 1
        elif not self.ignored_depth and tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._IGNORED and self.ignored_depth:
            self.ignored_depth -= 1
        elif not self.ignored_depth and tag in self._BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.ignored_depth:
            self.parts.append(data)

    def text(self) -> str:
        return "\n".join(line.strip() for line in "".join(self.parts).splitlines() if line.strip())


def safe_filename(filename: str) -> str:
    name = Path(filename or "upload").name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("._")
    if not name or name in {".", ".."}:
        raise HTTPException(400, "Filename is empty or unsafe")
    return name[:180]


def check_type(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(415, "Supported formats are PDF, DOC/DOCX, ODT, RTF, HTML, XML, common structured text, and TXT")
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(415, "File content does not match PDF format")
    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "[Content_Types].xml" not in archive.namelist() or "word/document.xml" not in archive.namelist():
                    raise ValueError
        except (zipfile.BadZipFile, ValueError):
            raise HTTPException(415, "File content is not a valid DOCX document")
    if ext == ".doc" and not data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        raise HTTPException(415, "File content does not match legacy Word DOC format")
    if ext == ".odt":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if archive.read("mimetype").decode("ascii") != "application/vnd.oasis.opendocument.text":
                    raise ValueError
        except (zipfile.BadZipFile, KeyError, UnicodeDecodeError, ValueError):
            raise HTTPException(415, "File content is not a valid OpenDocument text file")
    if ext == ".rtf" and not data.lstrip().startswith(b"{\\rtf"):
        raise HTTPException(415, "File content does not match RTF format")
    if ext in TEXT_FORMATS and (b"\x00" in data or data.startswith((b"%PDF-", b"PK\x03\x04")) or sum(byte < 9 or 13 < byte < 32 for byte in data) > max(1, len(data) // 100)):
        raise HTTPException(415, "File content does not match a supported text format")
    return ext


def _office_text(ext: str, data: bytes) -> str:
    executable = shutil.which("soffice")
    if not executable:
        raise HTTPException(503, f"{ext[1:].upper()} parsing requires LibreOffice. Install LibreOffice or convert the file to DOCX/TXT.")
    try:
        with tempfile.TemporaryDirectory(prefix="mia-office-") as temporary:
            root = Path(temporary)
            source = root / f"source{ext}"
            output = root / "output"
            profile = root / "profile"
            output.mkdir()
            source.write_bytes(data)
            command = [executable, "--headless", "--nologo", "--nodefault", "--nolockcheck", "--norestore",
                       f"-env:UserInstallation={profile.as_uri()}", "--convert-to", "txt:Text", "--outdir", str(output), str(source)]
            converted = subprocess.run(command, check=False, capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
            text_path = output / "source.txt"
            if converted.returncode or not text_path.is_file():
                detail = converted.stderr.decode("utf-8", "replace").strip() or converted.stdout.decode("utf-8", "replace").strip()
                raise HTTPException(422, f"LibreOffice could not extract text from {ext[1:].upper()}: {detail or 'conversion failed'}")
            return text_path.read_text(encoding="utf-8", errors="strict")
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(422, f"{ext[1:].upper()} extraction timed out after 30 seconds") from exc
    except UnicodeDecodeError as exc:
        raise HTTPException(422, f"LibreOffice produced unreadable UTF-8 text for {ext[1:].upper()}") from exc


def extract(ext: str, data: bytes):
    pages: list[dict] = []
    flags: list[dict] = []
    if ext == ".pdf":
        try:
            pdf = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:
            raise HTTPException(422, f"Corrupt or unreadable PDF: {exc}") from exc
        if len(pdf) == 0:
            raise HTTPException(422, "PDF contains no pages")
        if pdf.needs_pass:
            raise HTTPException(422, "Password-protected PDFs are not supported")
        image_pages = 0
        multi_column_pages = []
        for number, page in enumerate(pdf, start=1):
            text = page.get_text("text", sort=True).strip()
            if page.get_images(full=True):
                image_pages += 1
            pages.append({"page": number, "text": text})
            words_on_page = page.get_text("words")
            left_words = [word for word in words_on_page if word[0] < page.rect.width * .45]
            right_words = [word for word in words_on_page if word[0] > page.rect.width * .52]
            left_rows = {round(word[1] / 8) for word in left_words}
            right_rows = {round(word[1] / 8) for word in right_words}
            if len(left_words) >= 12 and len(right_words) >= 12 and len(left_rows & right_rows) >= 3:
                multi_column_pages.append(number)
        if multi_column_pages:
            flags.append({"code": "possible_multi_column",
                          "message": f"Possible multi-column reading order on {len(multi_column_pages)} page(s).",
                          "pages": multi_column_pages})
        text = "\n\n".join(p["text"] for p in pages)
        if image_pages and len(text.split()) < max(10, len(pdf) * 5):
            raise HTTPException(422, "PDF appears scanned with no usable text layer; OCR is not supported")
        if not text.strip():
            raise HTTPException(422, "PDF contains no extractable text")
        if len(pages) > 1:
            normalized_lines = [set(line.strip() for line in p["text"].splitlines() if len(line.strip()) > 2) for p in pages]
            common = set.intersection(*normalized_lines) if normalized_lines else set()
            if common:
                flags.append({"code": "repeated_page_text", "message": "Text repeats across pages and may be a header or footer.", "lines": sorted(common)[:12]})
    elif ext == ".docx":
        try:
            doc = DocxDocument(io.BytesIO(data))
        except Exception as exc:
            raise HTTPException(422, f"Unreadable DOCX: {exc}") from exc
        chunks = []
        for block in doc.element.body.iterchildren():
            if isinstance(block, CT_P):
                paragraph = Paragraph(block, doc)
                if paragraph.text.strip():
                    chunks.append(paragraph.text)
            elif isinstance(block, CT_Tbl):
                table = Table(block, doc)
                chunks.extend("\t".join(cell.text.strip() for cell in row.cells) for row in table.rows)
        text = "\n\n".join(chunks)
        if not text.strip():
            raise HTTPException(422, "DOCX contains no extractable text")
        pages = [{"page": None, "text": text}]
        flags.append({"code": "pagination_unavailable", "message": "DOCX pagination is not available; text is preserved by paragraph."})
    elif ext in OFFICE_FORMATS:
        text = _office_text(ext, data)
        if not text.strip():
            raise HTTPException(422, f"{ext[1:].upper()} contains no extractable text")
        pages = [{"page": None, "text": text}]
        flags.append({"code": "converted_with_libreoffice", "message": f"Text extracted using local LibreOffice from {ext[1:].upper()}; pagination is unavailable."})
    else:
        detected = from_bytes(data)
        match = detected.best()
        if match is None:
            raise HTTPException(422, "Text encoding could not be detected")
        # Short Western-language samples can score a Baltic code page above
        # Windows-1252 even when that reading turns ordinary accents into
        # unrelated characters. Prefer the Western candidate when it yields
        # more common Latin diacritics and avoids C1 control bytes.
        western = next((candidate for candidate in detected if candidate.encoding == "cp1252"), None)
        if western is not None:
            western_text = str(western)
            best_text = str(match)
            accents = set("áàâäãåæçéèêëíìîïñóòôöõøúùûüýÿ")
            if sum(char.lower() in accents for char in western_text) > sum(char.lower() in accents for char in best_text):
                match = western
        encoding = match.encoding or "unknown"
        try:
            text = str(match)
        except Exception as exc:
            raise HTTPException(422, f"Text could not be decoded ({encoding})") from exc
        if "�" in text:
            raise HTTPException(422, f"Text decode produced replacement characters ({encoding}); refusing silent mojibake")
        if ext in {".html", ".htm"}:
            parser = _HTMLTextParser()
            try:
                parser.feed(text)
                parser.close()
            except Exception as exc:
                raise HTTPException(422, f"HTML parsing failed: {exc}") from exc
            text = parser.text()
        elif ext == ".xml":
            try:
                root = ElementTree.fromstring(text)
                text = "\n".join(value.strip() for value in root.itertext() if value.strip())
            except ElementTree.ParseError as exc:
                raise HTTPException(422, f"Malformed XML document: {exc}") from exc
        if not text.strip():
            raise HTTPException(422, "Text file is empty")
        pages = [{"page": None, "text": text}]
        if encoding.lower().replace("_", "-") not in {"utf-8", "ascii"}:
            flags.append({"code": "non_utf8_encoding", "message": f"Decoded text using detected encoding {encoding}.", "encoding": encoding})
    normalized = unicodedata.normalize("NFKC", text)
    words = len(normalized.split())
    if words == 0:
        raise HTTPException(422, "Document has no extractable words")
    return pages, text, words, flags


def shingle_set(text: str, size: int = 5) -> set[tuple[str, ...]]:
    words = unicodedata.normalize("NFKC", text).lower().split()
    if not words:
        return set()
    if len(words) < size:
        return {tuple(words)}
    return {tuple(words[i:i + size]) for i in range(len(words) - size + 1)}

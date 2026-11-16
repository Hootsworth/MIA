import hashlib
import io
import json
import re
import unicodedata
import zipfile
from pathlib import Path

import fitz
from charset_normalizer import from_bytes
from docx import Document as DocxDocument
from fastapi import HTTPException, UploadFile

MAX_BYTES = 20 * 1024 * 1024
ALLOWED = {".pdf", ".docx", ".txt"}


def safe_filename(filename: str) -> str:
    name = Path(filename or "upload").name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("._")
    if not name or name in {".", ".."}:
        raise HTTPException(400, "Filename is empty or unsafe")
    return name[:180]


def check_type(filename: str, data: bytes) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(415, "Supported formats are PDF, DOCX, and TXT")
    if ext == ".pdf" and not data.startswith(b"%PDF-"):
        raise HTTPException(415, "File content does not match PDF format")
    if ext == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "[Content_Types].xml" not in archive.namelist() or "word/document.xml" not in archive.namelist():
                    raise ValueError
        except (zipfile.BadZipFile, ValueError):
            raise HTTPException(415, "File content is not a valid DOCX document")
    if ext == ".txt" and (b"\x00" in data or data.startswith((b"%PDF-", b"PK\x03\x04")) or sum(byte < 9 or 13 < byte < 32 for byte in data) > max(1, len(data) // 100)):
        raise HTTPException(415, "File content does not match plain text format")
    return ext


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
                flags.append({"code": "possible_multi_column", "message": f"Page {number} may have multi-column reading order."})
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
        text = "\n\n".join(paragraph.text for paragraph in doc.paragraphs if paragraph.text.strip())
        if not text.strip():
            raise HTTPException(422, "DOCX contains no extractable text")
        pages = [{"page": None, "text": text}]
        flags.append({"code": "pagination_unavailable", "message": "DOCX pagination is not available; text is preserved by paragraph."})
    else:
        match = from_bytes(data).best()
        if match is None:
            raise HTTPException(422, "Text encoding could not be detected")
        encoding = match.encoding or "unknown"
        try:
            text = str(match)
        except Exception as exc:
            raise HTTPException(422, f"Text could not be decoded ({encoding})") from exc
        if "�" in text:
            raise HTTPException(422, f"Text decode produced replacement characters ({encoding}); refusing silent mojibake")
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

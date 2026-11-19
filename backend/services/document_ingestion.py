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


def _latex_text(source: str) -> str:
    """Turn common LaTeX structure into readable text without discarding math/table contents."""
    source = re.sub(r"(?<!\\)%[^\n]*", "", source)
    source = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"(\1)/(\2)", source)
    source = re.sub(r"\\sqrt\{([^{}]*)\}", r"√(\1)", source)
    symbols = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "theta": "θ",
               "lambda": "λ", "mu": "μ", "pi": "π", "sigma": "σ", "omega": "ω",
               "times": "×", "cdot": "·", "leq": "≤", "geq": "≥", "neq": "≠", "infty": "∞"}
    source = re.sub(r"\\(" + "|".join(symbols) + r")\b", lambda match: symbols[match.group(1)], source)
    # Keep the content of common semantic environments while removing their wrappers.
    source = re.sub(r"\\begin\{(?:document|abstract|quote|quotation|itemize|enumerate|description|center|flushleft|flushright|figure\*?|table\*?|equation\*?|align\*?|gather\*?|multline\*?)\}(?:\[[^]]*\])?", "\n", source)
    source = re.sub(r"\\end\{[^}]+\}", "\n", source)
    source = re.sub(r"\\(?:\\|newline|par|linebreak)(?![A-Za-z])", "\n", source)
    source = re.sub(r"\\(?:hline|toprule|midrule|bottomrule|centering|maketitle|small|large|Large|footnotesize)\b", "\n", source)
    source = re.sub(r"\\(?:section|subsection|subsubsection|chapter|paragraph|title|author|caption|textbf|textit|emph|underline|mathrm|mathbf|operatorname)\*?(?:\[[^]]*\])?\{([^{}]*)\}", r"\1", source)
    source = re.sub(r"\\href\*?(?:\[[^]]*\])?\{[^{}]*\}\{([^{}]*)\}", r"\1", source)
    source = re.sub(r"\\(?:label|ref|eqref|cite|citep|citet|bibliography|bibliographystyle|usepackage|documentclass|input|include|includegraphics|url)\*?(?:\[[^]]*\])?\{[^{}]*\}", " ", source)
    source = re.sub(r"\\begin\{(?:tabular|tabularx|longtable|array)\}(?:\{[^{}]*\})?", "\n", source)
    # Table cells and list items are separated so their words are not concatenated.
    source = re.sub(r"(?<!\\)&", "\t", source)
    source = re.sub(r"\\\\(?:\[[^]]*\])?", "\n", source)
    source = re.sub(r"\\item(?:\[[^]]*\])?", "\n• ", source)
    # Remove remaining command names but keep following brace contents.
    source = re.sub(r"\\[A-Za-z@]+\*?", " ", source)
    source = source.replace("\\{", "{").replace("\\}", "}").replace("\\%", "%").replace("\\_", "_").replace("\\&", "&")
    source = re.sub(r"\$\$?", " ", source)
    source = re.sub(r"\\\[|\\\]|\\\(|\\\)", " ", source)
    source = re.sub(r"[{}]", " ", source)
    source = re.sub(r" *\t *", "\t", source)
    source = re.sub(r" +", " ", source)
    source = re.sub(r" *\n *", "\n", source)
    return "\n".join(line.strip() for line in source.splitlines() if line.strip())


def _docx_block_text(block, doc) -> list[str]:
    """Read paragraphs and nested tables in their original XML order."""
    if isinstance(block, CT_P):
        value = Paragraph(block, doc).text.strip()
        return [value] if value else []
    if isinstance(block, CT_Tbl):
        table = Table(block, doc)
        rows = []
        for row in table.rows:
            cells = []
            for cell in row.cells:
                cell_parts = []
                for child in cell._tc.iterchildren():
                    if isinstance(child, (CT_P, CT_Tbl)):
                        cell_parts.extend(_docx_block_text(child, doc))
                cell_text = " ".join(part.strip() for part in cell_parts if part.strip())
                if not cells or cell_text != cells[-1]:  # merged cells appear more than once in python-docx
                    cells.append(cell_text)
            if any(cells):
                rows.append("\t".join(cells))
        return rows
    return []


def _pdf_page_text(page) -> tuple[str, bool]:
    """Extract PDF text in layout order, replacing detected table areas with cell rows."""
    tables = []
    try:
        found = page.find_tables()
        for table in found.tables:
            rows = table.extract()
            if rows:
                rows_text = ["\t".join((cell or "").replace("\n", " ").strip() for cell in row) for row in rows]
                tables.append((table.bbox, "\n".join(rows_text)))
    except Exception:
        # Some vector artwork resembles a table; normal text extraction remains available.
        pass
    blocks = []
    for block in page.get_text("blocks", sort=True):
        x0, y0, x1, y1, value = block[:5]
        if not str(value).strip():
            continue
        covered = any(x0 >= bbox[0] and y0 >= bbox[1] and x1 <= bbox[2] and y1 <= bbox[3] for bbox, _ in tables)
        if not covered:
            blocks.append((y0, x0, str(value).strip()))
    blocks.extend((bbox[1], bbox[0], value) for bbox, value in tables)
    blocks.sort(key=lambda item: (round(item[0], 1), item[1]))
    return "\n".join(item[2] for item in blocks).strip(), bool(tables)


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
        ocr_pages = []
        table_pages = []
        multi_column_pages = []
        for number, page in enumerate(pdf, start=1):
            text, has_tables = _pdf_page_text(page)
            if has_tables:
                table_pages.append(number)
            has_images = bool(page.get_images(full=True))
            if has_images:
                image_pages += 1
            # Use PyMuPDF's Tesseract bridge only for image-heavy pages with almost no text.
            if has_images and len(text.split()) < 8 and shutil.which("tesseract"):
                try:
                    ocr_page = page.get_textpage_ocr(language="eng", dpi=200, full=True)
                    ocr_text = page.get_text("text", textpage=ocr_page, sort=True).strip()
                    if len(ocr_text.split()) > len(text.split()):
                        text = ocr_text
                        ocr_pages.append(number)
                except Exception:
                    # OCR is a best-effort fallback; the normal quality checks below report no text.
                    pass
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
        if ocr_pages:
            flags.append({"code": "ocr_applied", "message": f"Tesseract OCR was used on {len(ocr_pages)} low-text image page(s); verify recognition carefully.", "pages": ocr_pages})
        if table_pages:
            flags.append({"code": "pdf_tables_detected", "message": f"Table cell text was reconstructed on {len(table_pages)} PDF page(s); verify complex or merged cells.", "pages": table_pages})
        if image_pages and len(text.split()) < max(10, len(pdf) * 5):
            if not shutil.which("tesseract"):
                raise HTTPException(422, "PDF appears scanned with no usable text layer; install Tesseract OCR and its language data")
            raise HTTPException(422, "PDF appears scanned and OCR found no usable text")
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
            chunks.extend(_docx_block_text(block, doc))
        # Headers and footers often contain meaningful titles/notes; include each distinct value once.
        seen = set(chunks)
        for section in doc.sections:
            for part in (section.header, section.footer):
                for paragraph in part.paragraphs:
                    value = paragraph.text.strip()
                    if value and value not in seen:
                        chunks.append(value); seen.add(value)
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
        elif ext == ".tex":
            text = _latex_text(text)
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

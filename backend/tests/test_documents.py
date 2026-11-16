import csv
import hashlib
import io
import json
import shutil

import fitz
import pytest
from docx import Document as Docx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.api import documents as document_api
from backend.core.database import Base
from backend.main import app
from backend.models import AuditEvent, Document


@pytest.fixture
def isolated_client(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'documents.db'}")
    from sqlalchemy import event
    @event.listens_for(engine, "connect")
    def enable_fk(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(document_api, "SessionLocal", sessions)
    monkeypatch.setattr(document_api, "STORAGE", tmp_path / "storage" / "documents")
    monkeypatch.setattr(document_api, "ROOT", tmp_path)
    with TestClient(app) as client:
        yield client, sessions, tmp_path
    engine.dispose()


def declared(**overrides):
    result = {"provenance": "HUMAN", "language": "en", "author_language_background": "UNKNOWN", "source": "fixture", "license": "CC0"}
    result.update(overrides)
    return result


def pdf(text="A realistic text paragraph with a number of words for extraction and stable review.", pages=1):
    out = fitz.open()
    for _ in range(pages):
        page = out.new_page()
        if text:
            page.insert_text((72, 72), text)
    data = out.tobytes()
    out.close()
    return data


def post(client, name, data, metadata=None):
    return client.post("/api/documents", files={"file": (name, data)}, data={"metadata": json.dumps(metadata or declared())})


def test_upload_txt_extract_hash_and_safe_storage(isolated_client):
    client, sessions, root = isolated_client
    data = "A short document with original source and useful words.".encode()
    response = post(client, "../../sample.txt", data)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["filename"] == "sample.txt"
    assert body["sha256"] == hashlib.sha256(data).hexdigest()
    stored = list((root / "storage" / "documents").glob("*/original.txt"))[0]
    assert stored.read_bytes() == data
    assert body["word_count"] == 9


def test_duplicate_link_and_near_duplicate_flag(isolated_client):
    client, _, _ = isolated_client
    words = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty".encode()
    original = post(client, "one.txt", words)
    assert original.status_code == 201
    duplicate = post(client, "copy.txt", words)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["existing_document_id"] == original.json()["id"]
    near_text = words.replace(b"ten", b"ten-ish")
    near = post(client, "near.txt", near_text)
    assert near.status_code == 201
    assert near.json()["duplicate_flags"]


def test_declared_metadata_rules_reject_missing_human_source(isolated_client):
    client, _, _ = isolated_client
    response = post(client, "text.txt", b"A valid document with some words", {"provenance": "HUMAN", "language": "en", "author_language_background": "UNKNOWN"})
    assert response.status_code == 422


def test_ai_generated_requires_model_version_and_prompt(isolated_client):
    client, _, _ = isolated_client
    response = post(client, "text.txt", b"A valid document with some words", {"provenance": "AI_GENERATED", "language": "en", "author_language_background": "UNKNOWN", "generator_model": "Model"})
    assert response.status_code == 422
    good = declared(provenance="AI_GENERATED", generator_model="Model", generator_version="1", prompt_reference="prompt:fixture")
    assert post(client, "good.txt", b"Another valid document with enough words", good).status_code == 201


def test_ai_assisted_requires_editing_history(isolated_client):
    client, _, _ = isolated_client
    missing_history = declared(provenance="AI_ASSISTED", generator_model="Model", generator_version="1")
    rejected = post(client, "assisted-missing.txt", b"A valid document with enough words to check assisted metadata.", missing_history)
    assert rejected.status_code == 422
    complete = {**missing_history, "editing_history": "Author revised generated sentences."}
    accepted = post(client, "assisted-valid.txt", b"A second valid document with enough words to check assisted metadata.", complete)
    assert accepted.status_code == 201, accepted.text


def test_txt_latin1_decoded_and_flagged(isolated_client):
    client, _, _ = isolated_client
    response = post(client, "latin.txt", "café naïve résumé plus several words".encode("latin-1"))
    assert response.status_code == 201, response.text
    flag = response.json()["quality_flags"][0]
    assert flag["code"] == "non_utf8_encoding"
    details = client.get(f"/api/documents/{response.json()['id']}").json()
    assert "café" in details["pages"][0]["text"]


def test_latin1_ambiguous_charset_is_not_mojibake(isolated_client):
    client, _, _ = isolated_client
    text = "café naïve résumé plus enough ordinary words for encoding detection."
    response = post(client, "western.txt", text.encode("latin-1"))
    assert response.status_code == 201, response.text
    details = client.get(f"/api/documents/{response.json()['id']}").json()
    assert text in details["pages"][0]["text"]


def test_docx_paragraphs_and_audit_update_delete(isolated_client):
    client, sessions, _ = isolated_client
    docx = Docx(); docx.add_paragraph("First paragraph stays intact."); docx.add_paragraph("Second paragraph follows.")
    output = io.BytesIO(); docx.save(output)
    response = post(client, "essay.docx", output.getvalue())
    assert response.status_code == 201, response.text
    doc_id = response.json()["id"]
    extracted = client.get(f"/api/documents/{doc_id}").json()["pages"][0]["text"]
    assert "First paragraph" in extracted and "Second paragraph" in extracted
    updated = declared(genre="essay")
    assert client.patch(f"/api/documents/{doc_id}", json=updated).status_code == 200
    assert client.delete(f"/api/documents/{doc_id}").json()["deleted"] is True
    with sessions() as db:
        assert [event.event_type for event in db.scalars(select(AuditEvent)).all()] == ["DOCUMENT_CREATED", "DOCUMENT_UPDATED", "DOCUMENT_DELETED"]
    assert [event["event_type"] for event in client.get(f"/api/documents/{doc_id}/audit").json()] == ["DOCUMENT_CREATED", "DOCUMENT_UPDATED", "DOCUMENT_DELETED"]


def test_docx_table_text_is_extracted_in_document_order(isolated_client):
    client, _, _ = isolated_client
    docx = Docx()
    docx.add_paragraph("Before the table, this prose contains enough words to pass extraction.")
    table = docx.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "first table cell"
    table.cell(0, 1).text = "second table cell"
    output = io.BytesIO(); docx.save(output)
    response = post(client, "table.docx", output.getvalue())
    assert response.status_code == 201, response.text
    text = client.get(f"/api/documents/{response.json()['id']}").json()["pages"][0]["text"]
    assert text.index("Before the table") < text.index("first table cell") < text.index("second table cell")


def test_html_visible_text_xml_and_markdown_formats(isolated_client):
    client, _, _ = isolated_client
    html = b"<html><head><title>ignored metadata</title></head><body><h1>Readable heading</h1><p>Visible prose has enough words for useful detector input here.</p><script>hidden invented words stay excluded</script></body></html>"
    response = post(client, "paper.html", html)
    assert response.status_code == 201, response.text
    html_text = client.get(f"/api/documents/{response.json()['id']}").json()["pages"][0]["text"]
    assert "Readable heading" in html_text and "Visible prose" in html_text
    assert "hidden invented words" not in html_text and "ignored metadata" not in html_text

    xml = b"<article><title>Structured title</title><body>XML body text contains enough words to pass extraction and be checked.</body></article>"
    xml_response = post(client, "paper.xml", xml)
    assert xml_response.status_code == 201, xml_response.text
    xml_text = client.get(f"/api/documents/{xml_response.json()['id']}").json()["pages"][0]["text"]
    assert "Structured title" in xml_text and "XML body text" in xml_text and "<article>" not in xml_text

    markdown = b"# Heading\n\nMarkdown body contains enough words to pass extraction and remain readable."
    md_response = post(client, "paper.md", markdown)
    assert md_response.status_code == 201, md_response.text
    assert "# Heading" in client.get(f"/api/documents/{md_response.json()['id']}").json()["pages"][0]["text"]


def test_rtf_extracts_with_libreoffice_when_available(isolated_client):
    import shutil
    from backend.services.document_ingestion import extract

    if shutil.which("soffice") is None:
        pytest.skip("LibreOffice is optional for legacy Office/RTF extraction")
    rtf = br"{\rtf1\ansi A readable RTF document has enough words for real detector input and careful review.}"
    _, text, count, flags = extract(".rtf", rtf)
    assert "readable RTF document" in text and count >= 10
    assert flags[0]["code"] == "converted_with_libreoffice"


def test_pdf_extracts_each_page_and_flags_repeated_headers(isolated_client):
    client, _, _ = isolated_client
    response = post(client, "header.pdf", pdf("Repeated Journal Header\nA page has distinct prose and enough useful words for this extraction test.", pages=2))
    assert response.status_code == 201, response.text
    result = response.json()
    assert any(flag["code"] == "repeated_page_text" for flag in result["quality_flags"])
    assert len(client.get(f"/api/documents/{result['id']}").json()["pages"]) == 2


def test_pdf_empty_corrupt_password_and_scanned_rejected(isolated_client):
    client, _, _ = isolated_client
    assert post(client, "empty.pdf", pdf(text="")).status_code == 422
    assert post(client, "broken.pdf", b"%PDF-this is truncated").status_code == 422
    encrypted = fitz.open(); encrypted.new_page(); protected = encrypted.tobytes(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user"); encrypted.close()
    assert post(client, "locked.pdf", protected).status_code == 422
    scanned = fitz.open(); page = scanned.new_page(); pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 100), 0); pix.clear_with(240); page.insert_image(page.rect, pixmap=pix); scanned_bytes = scanned.tobytes(); scanned.close()
    scanned_response = post(client, "scan.pdf", scanned_bytes)
    assert scanned_response.status_code == 422 and "scanned" in scanned_response.text.lower()


def test_extension_mime_and_size_validation(isolated_client):
    client, _, _ = isolated_client
    assert post(client, "bad.pdf", b"Not a PDF").status_code == 415
    assert post(client, "bad.exe", b"x").status_code == 415
    assert post(client, "oversize.txt", b"x" * (20 * 1024 * 1024 + 1)).status_code == 413


def test_manifest_export_then_import_restores_database(isolated_client):
    client, sessions, _ = isolated_client
    created = post(client, "manifest.txt", b"Manifest test has sufficient words for a sound import export round trip.")
    assert created.status_code == 201, created.text
    manifest = client.get("/api/documents/manifest.csv")
    assert manifest.status_code == 200
    row_count = len(list(csv.DictReader(io.StringIO(manifest.text))))
    with sessions() as db:
        db.query(Document).delete(); db.commit()
    imported = client.post("/api/documents/manifest.csv", files={"file": ("manifest.csv", manifest.content, "text/csv")})
    assert imported.status_code == 200, imported.text
    assert imported.json() == {"imported": row_count, "rows": row_count}
    assert len(client.get("/api/documents").json()) == row_count


def test_pdf_multi_column_layout_gets_warning(isolated_client):
    client, _, _ = isolated_client
    source = fitz.open(); page = source.new_page()
    for y in range(70, 450, 35):
        page.insert_text((40, y), "Left column paragraph preserves ordinary readable text.")
        page.insert_text((320, y), "Right column paragraph contains another useful passage.")
    data = source.tobytes(); source.close()
    response = post(client, "columns.pdf", data)
    assert response.status_code == 201, response.text
    assert any(flag["code"] == "possible_multi_column" for flag in response.json()["quality_flags"])

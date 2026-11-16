# Methods

## Milestone 2 document handling

MIA stores the uploaded original unchanged at `storage/documents/<uuid>/original.<ext>`. It computes SHA-256 from the original bytes before extraction. Extracted text is a separate UTF-8 JSON sidecar containing raw page text and page references; it is never written back over the original. The word count is the number of whitespace-separated tokens after Unicode NFKC normalization. NFKC is used only for counting and duplicate comparison; raw extracted text remains separately preserved.

PDF pages are read with PyMuPDF in page order with block sorting. DOCX keeps paragraph boundaries, as its page layout depends on rendering and cannot reliably be recovered from the file. TXT encoding is detected with charset-normalizer; non-UTF-8 decoding is explicitly flagged. PDF image pages with very little text are rejected as likely scans. MIA v1 does not perform OCR. Repeated nontrivial lines across PDF pages produce a possible header/footer warning. The multi-column warning uses text block x positions and is heuristic; reading order is not guaranteed for complex layouts.

Exact duplicates are rejected by original-file SHA-256 and include the existing document identity. Near duplicates use five-word shingles and Jaccard similarity; scores at or above 0.50 are recorded as flags. This intentionally simple screen is not a plagiarism decision and can miss paraphrases or flag common formulaic prose. It does not infer authorship.

Provenance and language background are declared in metadata. HUMAN records require source and a license or consent record. AI_GENERATED records require model, version, and prompt reference. AI_ASSISTED records require model, version, and editing history. Invalid declarations are rejected. Document create, metadata update, archive, and manifest import are recorded in audit events.

CSV manifest export records the document ID, filename, original hash, and metadata/storage manifest. Import validates the metadata and confines referenced file paths to the document storage root, checks the original's SHA-256, and checks the extraction sidecar before restoring missing rows. The manifest does not embed document contents.

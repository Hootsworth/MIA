# Limitations

## Milestone 2

- PDF layout extraction is heuristic. Multi-column reading order can interleave; MIA flags some likely columns but does not guarantee correct ordering.
- Scanned PDFs are unsupported and rejected; there is no OCR.
- DOCX pagination is not available from the source format and is represented as one text section with paragraph boundaries.
- Encoding detection is best-effort. Unusual encodings may be rejected rather than decoded silently.
- Word count means whitespace-separated tokens after NFKC normalization, not a linguistic tokenizer.
- Near-duplicate Jaccard screening uses five-word shingles and a 0.50 threshold. It is a triage flag, not an authorship or plagiarism judgment.
- CSV manifests reference original and extracted files already present in local storage; the CSV itself is not a content archive.
- The v1 document table stores M2 fields in its JSON metadata column; adding normalized SQL columns would require a later schema migration.

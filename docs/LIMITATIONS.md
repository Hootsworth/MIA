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

## Milestone 3 detector

- This model was trained to distinguish GPT-2 1.5B outputs from WebText. It predates current chat models and must not be treated as a reliable classifier of modern AI writing.
- English-only, minimum 50 whitespace-separated words. Chunk-wise averaging can conceal variation between portions of a long document; raw per-chunk scores are retained.
- The softmax score is not calibrated against a representative contemporary dataset. It is not evidence or proof of authorship.
- The health check confirms that real inference works on one unlabeled diagnostic passage; it does not establish accuracy.
- Meaningful performance evaluation requires a documented, licensed, labeled dataset and is not part of Milestone 3.

## Milestone 4 similarity

- Winnowing matches exact normalized word sequences. Synonym changes, reordered text, and paraphrases can produce little or no overlap. This is expected and does not indicate absence of copied ideas.
- Punctuation, capitalization, compatibility characters, and whitespace differences are normalized away. Highlight spans include original punctuation only when it falls between the first and last matched word; differences in punctuation may therefore appear inside otherwise matched ranges.
- A shared normalized run of eight or more words is guaranteed to share a fingerprint with defaults `k=5,w=4`. Shorter matches can be missed by design; isolated/common repeated phrases may create incidental matches.
- Overlap percentages measure matched query-word coverage against the indexed corpus. They are not probabilities, plagiarism findings, or proof of authorship. A zero score means only that no indexed fingerprints matched.
- Results depend on reference-corpus coverage and licensing. Wikipedia pages are not a balanced or comprehensive corpus. Reuse requires attribution and ShareAlike compliance; MIA keeps collected page text and its derived index local and uncommitted.
- No boilerplate filter, semantic matching layer, corpus-level false-positive study, or evaluation metrics are included in this milestone.

# Limitations

## Milestone 2

- PDF layout extraction is heuristic. Multi-column reading order can interleave; MIA flags some likely columns but does not guarantee correct ordering. Ruled tables are reconstructed when detected; borderless tables, merged cells, dense math, and text embedded in diagrams may be incomplete or out of order.
- Scanned PDF pages use optional local Tesseract OCR when available. OCR is English by default and can misread text, formulas, columns, and tables; results carry an OCR warning and need review. Other languages require matching Tesseract language data, which MIA does not configure automatically.
- DOCX pagination is not available from the source format and is represented as one text section with paragraph boundaries. Body nested tables and paragraph-only header/footer text are extracted, but floating text boxes, drawing text, and some footnotes/endnotes may be missed.
- LaTeX extraction handles common commands and environments but does not compile TeX or expand project-specific macros, external inputs, bibliography databases, or image content. Complex nested math and custom table structures may not be faithfully rendered.
- Legacy DOC, ODT, and RTF extraction requires LibreOffice on the backend; DOCX does not require it.
- HTML and XML extraction keeps visible/text-node content only. CSS layout, images, embedded documents, and OCR are not interpreted.
- The detector supports English only and needs at least 50 words. Other uploaded documents can be stored but the model will refuse prediction.
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

## Milestone 5 experiments

- A declared classification rule is required and frozen, but MIA does not interpret it or compute classifications or metrics yet.
- The runner is one-job-at-a-time inside a single backend process. SQLite persists results and restart state, but this is not a distributed task queue.
- Cancellation is checked between document-detector pairs; an inference already in progress may finish and be stored before cancellation takes effect.
- A per-item failure is recorded with no score and leaves the experiment partially completed. Resume retries failed pairs and updates that pair's existing result row; successful pairs are not recomputed.
- Protocol snapshots verify extracted text has not changed since draft creation. If local document storage is missing or changed, that pair records an error and requires storage repair before resume.
- `conditions.transformations` is recorded as a protocol hook only. Perturbations are not applied in this milestone.

## Milestone 6 statistics

- Statistics require a structured `m6.1` rule. Existing M5 free-text protocols remain readable but cannot be analyzed until duplicated/updated as an M6 structured protocol.
- Metrics use declared provenance, which is not independently verified. The current local database has one HUMAN document and no AI-labeled documents, so the live dataset cannot estimate binary performance; one-class results correctly leave AUROC/AUPRC unavailable.
- Bootstrap intervals are percentile intervals over observed documents, or paired documents in detector comparisons. This release does not provide cluster-resampling intervals through the analysis endpoint, multiplicity adjustments, or threshold tuning. The grouped leakage helper is available for study splits, but the current analysis endpoint does not create splits.
- Subgroup summaries report sample counts and low-n flags but do not claim inferential subgroup differences. Calibration is available only for scores explicitly marked as probabilities; the current RoBERTa probability is not necessarily calibrated.
- Censored and missing score states are counted separately and excluded. No censoring-aware estimator is implemented.

## Milestone 7 Turnitin reports

- The importer is implemented for manually supplied, institution-authorised report files only. Institutional approval has not been documented in this repository, so no research documents have been submitted and no real Turnitin reports have been imported or verified.
- MIA does not verify report contents with Turnitin, parse passages from the PDF/image, or provide API access. Researchers transcribe displayed values and passage annotations, then confirm the document association.
- Eligible word-count tolerance is researcher supplied and stored. An overly permissive tolerance weakens the association safeguard.
- Censored scores remain typed observations with raw display strings and optional upper bounds. MIA does not yet implement censoring-aware statistical estimators.

## Milestone 8 reporting

- Markdown reports can only be generated for completed experiments using structured M6 protocols. Legacy M5 free-text protocols cannot provide a reproducible statistical report.
- Report estimates match the analysis endpoint at generation time; a later code change may alter recalculated statistics. Reports include the generating commit SHA so this distinction is visible.
- Tiny subgroup cells are marked unreliable and do not receive bootstrap intervals. Their point estimates are descriptive only.
- CSV is an export of individual stored detector outputs (including errors and manual Turnitin observations); it does not embed original documents or report files.

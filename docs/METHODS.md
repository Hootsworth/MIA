# Methods

## Milestone 2 document handling

MIA stores the uploaded original unchanged at `storage/documents/<uuid>/original.<ext>`. It computes SHA-256 from the original bytes before extraction. Extracted text is a separate UTF-8 JSON sidecar containing raw page text and page references; it is never written back over the original. The word count is the number of whitespace-separated tokens after Unicode NFKC normalization. NFKC is used only for counting and duplicate comparison; raw extracted text remains separately preserved.

PDF pages are read with PyMuPDF in page order with block sorting. DOCX keeps paragraph boundaries, as its page layout depends on rendering and cannot reliably be recovered from the file. TXT encoding is detected with charset-normalizer; non-UTF-8 decoding is explicitly flagged. For short ambiguous Western-language samples, a Windows-1252 candidate is preferred only when it yields more common Latin diacritics than the top candidate, avoiding a tested mojibake case. PDF image pages with very little text are rejected as likely scans. MIA v1 does not perform OCR. Repeated nontrivial lines across PDF pages produce a possible header/footer warning. The multi-column warning uses text block x positions and is heuristic; reading order is not guaranteed for complex layouts.

Exact duplicates are rejected by original-file SHA-256 and include the existing document identity. Near duplicates use five-word shingles and Jaccard similarity; scores at or above 0.50 are recorded as flags. This intentionally simple screen is not a plagiarism decision and can miss paraphrases or flag common formulaic prose. It does not infer authorship.

Provenance and language background are declared in metadata. HUMAN records require source and a license or consent record. AI_GENERATED records require model, version, and prompt reference. AI_ASSISTED records require model, version, and editing history. Invalid declarations are rejected. Document create, metadata update, archive, and manifest import are recorded in audit events.

CSV manifest export records the document ID, filename, original hash, and metadata/storage manifest. Import validates the metadata and confines referenced file paths to the document storage root, checks the original's SHA-256, and checks the extraction sidecar before restoring missing rows. The manifest does not embed document contents.

## Milestone 3 detector inference

The `roberta-openai` adapter pins `openai-community/roberta-base-openai-detector` to revision `6cba99c003b711c7fe94f8a3aa2be35a792cb6fa`. It loads the model and fast tokenizer lazily, uses MPS when available and CPU otherwise, and retries on CPU if MPS inference fails. The start script sets `PYTORCH_ENABLE_MPS_FALLBACK=1`. Hugging Face files are cached under `MIA_MODEL_CACHE` (default `storage/models`) and are not committed.

The model's labels are `Fake` and `Real`. MIA reports the Fake-class softmax output as a model probability, not as a calibrated probability of AI authorship. Text shorter than 50 whitespace-separated words or whose declared language is not English is rejected. Longer texts are split into consecutive non-overlapping token windows within the 512-token sequence limit. The displayed score and final label use the unweighted mean of the per-window softmax probabilities; raw probabilities for each chunk are retained in the result JSON. Each prediction is persisted with the document's declared provenance, model revision, device, duration, configuration, and raw output. Failures persist an error result with no score; failures before an inference record can be created return a specific HTTP error.

Each single-document M3 inference creates a minimal technical experiment row to satisfy the result foreign key. It has no classification rule and produces no aggregate metrics or authorship conclusion. Milestone 5 adds frozen, multi-document experiment protocols separately.

## Milestone 4 winnowing similarity

`mia-detect.similarity` has no runtime dependency beyond Python's standard library. It applies Unicode NFKC, case folding, and word tokenization based on Unicode letters, combining marks, and numbers. Punctuation and whitespace separate tokens and do not enter a fingerprint. Token offsets point back to the original text so returned ranges can be highlighted without rewriting stored documents.

The default configuration uses `k=5` words per shingle and `w=4` consecutive shingle hashes per winnowing window. A full window selects its minimum 64-bit BLAKE2b hash; ties select the rightmost minimum. The threshold guarantee is `t = w + k - 1 = 8` words: any identical normalized run of at least eight words contains a selected fingerprint in both texts. Expected fingerprint density for ordinary text is approximately `2/(w+1)`; actual density depends on repeated hashes and text content. Hash matches are checked against the full normalized shingle to guard against a hash collision.

The inverted index is SQLite with foreign keys enabled and a B-tree index on fingerprint hash. Each entry retains source ID, token position, original character offsets, and the shingle. Re-indexing a source ID replaces its old rows. The database records the selected `k` and `w`; opening it with different parameters fails explicitly. Source title, URL, and license are retained for attribution.

Every matching fingerprint is expanded across adjacent identical normalized words and aligned query/source ranges are merged. Per-source overlap is distinct query-word positions covered by exact normalized matches divided by query word count. Overall overlap is the union of query-word positions covered by any source divided by query word count. Both are percentages, not probabilities, plagiarism decisions, or authorship labels. Use `exclude_source_ids` in the library or `--exclude-source` in the CLI when a query is also present in the index.

The corpus helper downloads page extracts through Wikipedia's MediaWiki API and records permanent revision links, page IDs, hashes, and the declared CC BY-SA 4.0 license in `corpus-manifest.json`. Wikipedia attribution is provided through the per-page revision URL; text is retained only in ignored local storage. The generated index is also local and rebuildable. See `docs/DATASETS.md` for reuse terms and data handling.

## Milestone 5 experiment protocols and execution

An experiment protocol records its research question, hypothesis, explicit classification rule, planned metrics, seed, version, conditions and declared transformations. It snapshots each selected document's ID, original SHA-256, extraction text hash, filename, declared provenance and research metadata, plus detector keys, database IDs, model revisions and score semantics. Once queued, this JSON protocol is immutable. Duplicating a run creates a new draft with the same snapshot.

The runner processes the Cartesian product of snapshot documents and detectors one pair at a time. Inference runs in a worker thread so API requests can still cancel the experiment. Every result, including a per-item failure with no score, is committed before advancing progress. Cancellation takes effect between pairs; an in-flight pair is allowed to finish. Successful pairs are retained during resume, while failed pairs are retried in place and their attempt count is recorded. A backend restart marks active snapshot-based runs partial and schedules work that was queued but had not begun. Legacy single-document inference rows are excluded from this recovery path.

The classification rule and metrics list are protocol declarations only. Milestone 5 does not convert scores to classes, compute binary metrics, apply perturbations, or produce aggregate conclusions. Those are later research and statistics work.

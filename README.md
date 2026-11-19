# MIA

**MIA (Maybe It’s AI)** is an open-source research toolkit for examining how AI-writing and text-similarity detectors perform, where they fail, and how reliable their scores are. The name expansion is background; the app uses **MIA**.

The project has two parts:

- **`mia-detect`** — a small, standalone Python package for clean-room implementations of methods described in public research and documentation.
- **MIA Lab** — a research application for managing declared research data, running reproducible evaluations, and reporting results.

MIA is designed to measure detector behavior, not to help people evade detection. Commercial detector results, including Turnitin, may only be included through reports submitted and imported manually by an authorized researcher.

## Current status

Milestones 1–8 are implemented. The overview supports direct document upload and real inference with the pinned RoBERTa detector. The research lab includes document, detector, experiment, analysis, Turnitin-import, and generated-report views. Analysis charts and tables read persisted experiment results, while generated reports include reproducible Markdown and raw CSV with hashes. The standalone `mia-detect` package provides a winnowing-based exact-overlap index and CLI. Turnitin imports remain manual, require explicit document confirmation and matching hashes, preserve censored values, and may only be used after institutional authorization.

## Quick start

Requirements:

- Python 3.12 or newer
- Node.js 20 or newer

Start both services from the repository root:

```sh
./start.sh
```

If `python3` on your machine points to an older Python, select the installed interpreter explicitly:

```sh
PYTHON=python3.12 ./start.sh
```

The first start creates a virtual environment, installs backend and frontend dependencies (including PyTorch and Transformers), creates the SQLite schema, and installs `mia-detect`. Model weights download from Hugging Face the first time you run the detector health check; allow network access and several hundred megabytes of disk space. Press **Ctrl+C** in the start terminal or run `./stop.sh` to stop the services.

| Service | Address |
| --- | --- |
| MIA Lab | http://localhost:3000 |
| API | http://localhost:8000 |
| API documentation | http://localhost:8000/docs |
| Health endpoint | http://localhost:8000/api/health |
| Standalone open-model detector | http://localhost:3001 |

## Standalone open-model detector

The separate detector application at port 3001 accepts documents using the same local extraction backend, then runs two pinned public checkpoints independently: Tropa Mini (four classes: human, AI, AI-edited, humanized) and ModernBERT fine-tuned on MAGE. It shows each model's raw class output and score separately. It does not calculate a combined verdict or claim that a score proves authorship. Both checkpoints are English-only in this integration and require at least 50 extracted words.

Download the exact checkpoint revisions before analyzing documents:

```sh
make detector-models
```

The downloads are about 2.3 GB in total and are stored under `storage/models/`; they are not committed. The detector app displays a clear unavailable state when weights are absent. Tropa Mini's published reference threshold comes from its publisher's validation set and is not calibrated for your writing population. ModernBERT output is also uncalibrated. Both can make confident errors, especially on historical prose, edited text, and generators unlike their training data. Treat the results as model outputs for exploration, not evidence for consequential decisions. See each linked Hugging Face model card in the app's source metadata and review its license before redistribution.

The database lives at `data/mia.db`. Set `MIA_DATABASE_URL` to use another SQLAlchemy database URL. Set `NEXT_PUBLIC_API_URL` to change the frontend’s API address. `MIA_MODEL_CACHE` selects the Hugging Face cache directory (default `storage/models`). Defaults are in `.env.example`.

## Tests

Run the backend and standalone package tests with:

```sh
.venv/bin/python -m pytest
```

The current tests cover API health, schema creation and constraints, detector availability, similarity normalization and winnowing guarantees, source attribution and match spans, experiment protocol freezing, real similarity runs, cancellation, resume/restart behavior, and installation/import of `mia-detect` without application dependencies.

## Use `mia-detect` on its own

The detector package has no web, database-server, or runtime dependencies beyond Python's standard library. Install it from this repository:

```sh
python -m pip install ./packages/mia-detect
```

Then import the package:

```python
import mia_detect

print(mia_detect.__version__)
```

The package implements deterministic exact normalized-word overlap with SQLite from Python's standard library. The web app's RoBERTa model is separate from `mia-detect` and has no effect on that standalone package's dependency requirements.

## Research and privacy principles

- Implement methods from public papers and documentation; never copy proprietary code, weights, or datasets.
- Treat authorship as declared provenance. Never infer it from detector output or writing style.
- Use public-licensed or consented research documents, and keep identity separate from experiment identifiers.
- Do not automate or scrape commercial detectors. Import their reports manually only when authorized.
- Never fabricate detector output or metrics. Failures and unavailable models must remain visible as failures.
- Do not build paraphrasing, humanizing, or detector-bypass features.

See [SPEC.md](SPEC.md) for the requirements and hard boundaries, and [docs/ROADMAP.md](docs/ROADMAP.md) for milestones, verification steps, and failure handling. Dataset planning and current limitations are documented in [docs/DATASETS.md](docs/DATASETS.md) and [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Project layout

```text
backend/                 FastAPI, SQLAlchemy models, tests
frontend/                Next.js App Router UI
packages/mia-detect/     Standalone Python package
data/                    SQLite database and dataset manifests
storage/                 Local documents, reports, exports, and logs
docs/                    Methods, dataset policy, limitations, roadmap
```

## License

MIA is distributed under the Apache License 2.0. See [LICENSE](LICENSE).

## Documents (Milestone 2)

Run the app with `./start.sh` and open `http://localhost:3000`. Choose a supported text document and MIA stores the original, extracts its text, checks the actual detector health, and runs the pinned AI detector. Declare provenance and language; MIA never infers who wrote the text. The model currently accepts English documents with at least 50 words. The document library retains full metadata and extraction details. Exact duplicate hashes are rejected with the existing record linked; near duplicates are flagged with a five-word shingle Jaccard score.

PDF extraction uses PyMuPDF; DOCX uses python-docx with paragraph and table extraction; HTML and XML use structured parsers; text encoding uses charset-normalizer. Legacy DOC, ODT, and RTF use local LibreOffice conversion when installed. Scanned PDFs are rejected because MIA does not include OCR. CSV manifests can be exported from `/api/documents/manifest.csv` and re-imported while referenced files remain in local document storage. See [`docs/METHODS.md`](docs/METHODS.md) and [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) for definitions and caveats.

## Detectors (Milestone 3)

Open `/detectors` to inspect availability and run the model's real inference health check. Once operational, select a stored English document of at least 50 words to produce a persistent result. The first health check downloads the pinned `openai-community/roberta-base-openai-detector` weights. The model was trained on GPT-2 outputs and WebText; its chunk-averaged Fake-class softmax score is not calibrated and cannot establish authorship. Every result retains the model revision, device, duration, raw per-chunk probabilities, and declared provenance. No evaluation metrics are produced in this milestone. Read [`docs/METHODS.md`](docs/METHODS.md) and [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) before interpreting outputs.

## Similarity (Milestone 4)

The registry also exposes `MIA Similarity · Winnowing`. It is operational only when a local reference index exists and its real self-match health check passes. Collect an attributed development reference set and build the default SQLite index with:

```sh
.venv/bin/python scripts/fetch_wikipedia_corpus.py --count 1000 --output storage/reference-corpus/wikipedia-en
.venv/bin/python -m mia_detect index storage/reference-corpus/wikipedia-en --database storage/similarity/index.sqlite3
```

Then run the health check at `/detectors`. The collector stores article introductions locally and writes a revision-linked source manifest; the corpus and index are git-ignored. Commit only `data/manifests/` metadata. Defaults are five-word shingles and a four-shingle winnowing window, giving an eight-word exact-match threshold guarantee. The CLI can also index your own UTF-8 `.txt` directory and compare a text file: `mia-detect index <directory> --database <index>` then `mia-detect check <file> --database <index>`. Returned overlap percentages are query-word coverage, not probability or a plagiarism finding. See [`docs/DATASETS.md`](docs/DATASETS.md) for licensing and attribution rules.

## Experiments (Milestones 5–6)

Open `/experiments` to create a draft from stored documents and registered detectors. Declare the research question, hypothesis, classification rule, planned metrics, and random seed before queueing. MIA freezes the document IDs and hashes, extracted-text hashes, detector IDs and revisions, conditions, and protocol version. Queued protocols cannot be edited; duplicate an experiment to create a new draft.

Runs persist one result per document-detector pair, including errors, and update progress after each pair. Cancel stops new pairs after the current in-flight pair. Failed pairs can be retried when resuming a partial run; successful pairs remain unchanged. On restart, running experiments with frozen snapshots become resumable partial runs.

Milestone 6 adds the read-only endpoint `/api/analysis/experiments/{id}` and a results view on `/experiments`. New experiments freeze an `m6.1` structured rule: positive/negative declared provenance, per-detector score direction and threshold, plus selected metrics. Estimates include n, class counts, deterministic 95% bootstrap intervals (2,000 resamples by default), subgroup counts/low-n flags, and paired detector comparisons when applicable. Binary metrics cannot run without thresholds. Calibration/ECE require detector score semantics `probability`; percentage and ordinal scores are never treated as probabilities. Missing and censored results are counted but excluded from estimates. Legacy M5 text protocols stay intact and need duplication or update before they can be analyzed.

The current local database has one HUMAN document and no AI-labeled documents, which is insufficient to estimate binary performance. MIA returns estimability details rather than inventing scores. See [`docs/METHODS.md`](docs/METHODS.md) and [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

## Analysis and reports (Milestone 8)

Open `/analysis` to select a completed or partially completed experiment with a structured M6 protocol. Metric estimates, confidence intervals, ROC coordinates, score-distribution bins, document scores, subgroup counts, and subgroup intervals come from the analysis API. The page visualizes these returned values; it does not calculate or tune detector metrics in the browser. Empty, one-class, missing-score, censored-score, and small-subgroup states are reported explicitly.

Open `/reports` to generate a Markdown research report and raw-result CSV from a completed analyzable experiment. The report records the frozen question, protocol, dataset hashes and declared-provenance counts, detector revisions and score semantics, estimates with n and intervals, subgroup limitations, random seed, and generating commit. Files and SHA-256 hashes are stored in the local `generated_reports` table and `storage/reports/generated/`; they are not uploaded to a third-party service. `CITATION.cff` gives the software citation and [`CONTRIBUTING.md`](CONTRIBUTING.md) describes project boundaries and contribution expectations.

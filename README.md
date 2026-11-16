# MIA

**MIA (Maybe It’s AI)** is an open-source research toolkit for examining how AI-writing and text-similarity detectors perform, where they fail, and how reliable their scores are. The name expansion is background; the app uses **MIA**.

The project has two parts:

- **`mia-detect`** — a small, standalone Python package for clean-room implementations of methods described in public research and documentation.
- **MIA Lab** — a research application for managing declared research data, running reproducible evaluations, and reporting results.

MIA is designed to measure detector behavior, not to help people evade detection. Commercial detector results, including Turnitin, may only be included through reports submitted and imported manually by an authorized researcher.

## Current status

Milestones 1–3 provide the foundation, document ingestion, and the first real detector baseline. MIA Lab includes FastAPI with SQLite, a Next.js interface, declared-provenance document handling, and a pinned RoBERTa OpenAI detector with persistent inference results. The separate `mia-detect` package remains dependency-light and installable without the web application.

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

The database lives at `data/mia.db`. Set `MIA_DATABASE_URL` to use another SQLAlchemy database URL. Set `NEXT_PUBLIC_API_URL` to change the frontend’s API address. `MIA_MODEL_CACHE` selects the Hugging Face cache directory (default `storage/models`). Defaults are in `.env.example`.

## Tests

Run the backend and standalone package tests with:

```sh
.venv/bin/python -m pytest
```

The current tests cover API health, schema creation, SQLite foreign keys and uniqueness, detector validation and unavailable states, and installation/import of `mia-detect` without application dependencies.

## Use `mia-detect` on its own

The detector package has no web, database, or runtime dependencies. Install it from this repository:

```sh
python -m pip install ./packages/mia-detect
```

Then import the package:

```python
import mia_detect

print(mia_detect.__version__)
```

The package currently provides its module structure; the v1 similarity implementation is still a later milestone. The web app's RoBERTa model is separate from `mia-detect` and has no effect on that standalone package's dependency requirements.

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

Run the app with `./start.sh` and open `http://localhost:3000/documents`. Upload TXT, DOCX, or PDF files up to 20 MB. Declare provenance, language, and author language background; the API validates required provenance records and stores originals unchanged under `storage/documents/`. The document detail view shows extracted page text, warnings, hashes, and metadata editing. Exact duplicate hashes are rejected with the existing record linked; near duplicates are flagged with a five-word shingle Jaccard score.

PDF extraction uses PyMuPDF, DOCX extraction uses python-docx, and text encoding is detected with charset-normalizer. Scanned PDFs are rejected because this milestone does not include OCR. CSV manifests can be exported from `/api/documents/manifest.csv` and re-imported at that endpoint while their referenced files remain in local document storage. See [`docs/METHODS.md`](docs/METHODS.md) and [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) for definitions and caveats.

## Detectors (Milestone 3)

Open `/detectors` to inspect availability and run the model's real inference health check. Once operational, select a stored English document of at least 50 words to produce a persistent result. The first health check downloads the pinned `openai-community/roberta-base-openai-detector` weights. The model was trained on GPT-2 outputs and WebText; its chunk-averaged Fake-class softmax score is not calibrated and cannot establish authorship. Every result retains the model revision, device, duration, raw per-chunk probabilities, and declared provenance. No evaluation metrics are produced in this milestone. Read [`docs/METHODS.md`](docs/METHODS.md) and [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) before interpreting outputs.

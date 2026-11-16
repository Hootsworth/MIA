# MIA: Open Detector Toolkit and Evaluation Lab

> Save this file as `SPEC.md` in the repo root. To the coding agent: read this whole file, then follow the **Working Agreement** (section 9). Implement **one milestone per session** and stop.

## 1. Mission

MIA is an open-source project that makes plagiarism and AI-writing detection **transparent and measurable**. It has two parts:

1. **`mia-detect`**: a clean-room Python library implementing publicly documented detection methods (text similarity and AI-text detection). This is the part people read, fork, and cite.
2. **`mia-lab`**: a research harness (API, database, UI) that evaluates detectors against labeled ground truth, including commercial tools such as Turnitin through **manually imported reports only**.

The goal is understanding: how well do these detectors work, for whom, and where do they fail. It is **not** to copy proprietary systems and **not** to help anyone evade detection.

## 2. Hard Boundaries (non-negotiable)

- **Clean-room only.** Implement from published papers and documentation. Never decompile, scrape, probe, or automate any commercial detector. Never include proprietary code, weights, or data.
- **Turnitin is a black box reached only by a human.** The researcher submits documents through their institution's authorised access and then manually uploads or enters the resulting report. No automated submission, no credential storage, no scraping.
- **No evasion features.** Do not build paraphrasers, humanizers, or "bypass" tools. Adversarial robustness *evaluation* is allowed only on research datasets using documented, standard perturbations (see 6.4), and results are reported as detector failure modes.
- **No fabricated results.** Never simulate detector output, seed fake metrics, or show a success state when an operation failed. If a detector cannot run, record the exact reason and show it as unavailable.
- **Provenance is declared, never inferred.** Authorship labels come from documented metadata, never from a detector or from linguistic guesses.
- **Consent and privacy.** Only use public-licensed corpora or documents with recorded author consent. Keep author identity separate from experiment identifiers.

## 3. Research Questions

The platform exists to answer these. Every table, field, and experiment must serve at least one.

- **RQ1. Accuracy and calibration.** How accurately do open-source AI-text detectors separate human and AI-generated text, and are their scores calibrated?
- **RQ2. Fairness.** Do false-positive rates differ for non-native English writers versus native writers on human-written text?
- **RQ3. Length sensitivity.** How do detector scores and error rates change with document length?
- **RQ4. Cross-detector agreement.** Where open detectors and Turnitin disagree on the same documents, what do the disagreements look like?
- **RQ5. Robustness.** How much do standard text perturbations (light editing, translation round-trip, mixed human and AI text) change detector outputs?

RQ4 involves Turnitin, so its sample will be small. Report it descriptively with intervals, and say plainly when it is underpowered.

## 4. Scope

### v1 (build this)
- Document ingestion (TXT, DOCX, PDF) with provenance metadata and extraction-quality checks
- Detector adapter framework with **two** working detectors: the RoBERTa OpenAI detector and a winnowing-based similarity checker
- Experiments with persistent state and reproducible recorded protocols
- Statistics engine (metrics with bootstrap CIs, grouped analysis)
- Manual Turnitin report import with association safeguards
- Minimal UI: upload, label, run experiment, view results, import report
- Exportable research report (Markdown, plus CSV of raw results)

### v2 (do not build until v1 is verified)
Binoculars, Fast-DetectGPT, multi-user auth and roles, Playwright E2E suite, Alembic migrations, advanced dashboards, additional languages.

## 5. Architecture

```
mia/
├── packages/
│   └── mia-detect/        # publishable library, no web/DB dependencies
│       ├── similarity/        # normalize, shingle, winnow, index, match
│       ├── ai_text/           # detector implementations
│       └── tests/
├── backend/                   # FastAPI + SQLAlchemy + SQLite (data/mia.db)
│   ├── api/ core/ models/ schemas/ services/ analytics/ reports/ tests/
├── frontend/                  # Next.js (App Router), TypeScript, Tailwind
├── data/                      # SQLite + dataset manifests (not raw corpora)
├── storage/                   # documents/ reports/ exports/ logs/
├── docs/                      # METHODS.md, DATASETS.md, LIMITATIONS.md
├── scripts/  Makefile  start.sh  stop.sh  .env.example  LICENSE  README.md
```

Rules:
- `mia-detect` must be installable and usable **without** the backend or frontend. Keep it dependency-light and well documented, because it is the deliverable people study.
- Every detector implements one adapter interface (`metadata`, `validate`, `predict`, `health_check`) and returns a typed result (section 6.2).
- Native macOS on Apple Silicon: use MPS when supported, CPU fallback otherwise. `./start.sh` checks prerequisites, sets up environments, runs migrations (or `create_all` in v1), starts backend and frontend, and prints URLs. `./stop.sh` shuts down cleanly.
- SQLite at `data/mia.db`, UUID primary keys, foreign keys enforced, timestamps on all rows, JSON columns for variable metadata.

Core tables (v1): `documents`, `datasets`, `dataset_documents`, `detectors`, `detector_versions`, `experiments`, `experiment_documents`, `results`, `turnitin_reports`, `highlighted_passages`, `audit_events`, `generated_reports`.

## 6. Functional Requirements

### 6.1 Documents and datasets
Each document stores: UUID, filename, SHA-256 of the original file, **declared provenance** (`HUMAN`, `AI_GENERATED`, `AI_ASSISTED`), academic domain, genre, language, **author-language-background** (`NATIVE`, `NON_NATIVE`, `UNKNOWN`, required for RQ2), word count, source and license, consent record, generating model and version (if AI), editing history (if assisted), created-at.

- Preserve the original file untouched; store extracted text separately with page references.
- Detect duplicates by hash and near-duplicates by similarity; flag, do not silently drop.
- PDF extraction (PyMuPDF): per-page text, paragraph preservation where possible, empty/malformed/scanned detection, repeated-page detection, extraction-quality warnings. Never process an unreadable file silently.
- Support dataset manifests (CSV/JSON) for bulk import and export.

### 6.2 Detector framework
```python
class DetectorAdapter:
    def metadata(self) -> DetectorMetadata: ...
    def validate(self, document) -> ValidationResult: ...   # length, language, encoding limits
    def predict(self, document) -> DetectionResult: ...     # real inference only
    def health_check(self) -> HealthStatus: ...             # actually runs a tiny inference
```
`DetectionResult` records: document ID, detector ID and version, model identifier and revision hash, configuration, raw output, label (if the detector emits one), numeric score (if any), score semantics (`probability` | `logit` | `percentage` | `distance` | `unknown`), duration, timestamp, error details. **Never treat a score as a probability unless the detector documents it as one and calibration is verified.**

v1 detectors:
- **RoBERTa OpenAI detector** (Hugging Face). Document its known limits (trained on GPT-2 outputs, dated).
- **Similarity checker** (`mia-detect.similarity`): text normalization, k-word shingling, hashing, winnowing fingerprints, inverted index over an open reference corpus, match spans with source attribution, per-source overlap score.

A detector is "operational" only after a real inference passes `health_check`. If weights are missing or hardware is unsupported, show the exact reason.

### 6.3 Turnitin report import (manual, institution-authorised)
Flow: select document, export the exact submitted file, submit it through the institutional interface, then import the report.

Capture: submission reference, report timestamp, similarity percentage (if shown), AI-writing percentage as displayed, flagged-passage annotations (if shown), eligible word count, detector version if disclosed, the original report file, ingestion timestamp.

Safeguards:
- Require the report's file hash / submitted-file hash or an explicit human confirmation that the report matches the document; refuse association on a mismatch.
- Store the raw displayed value verbatim. Turnitin may suppress or censor low scores (for example showing an asterisk or no number below a threshold). Model this as a **censored** value, never as zero and never as missing-at-random.
- Validate ranges and required fields; reject malformed imports with a specific error.
- Never claim API access. Keep the adapter interface ready for future authorised integrations.

### 6.4 Experiments
Each experiment records: UUID, name, research question (linked to RQ1 to RQ5), hypothesis, dataset snapshot (document IDs and hashes), detectors and versions, conditions, **classification rule**, metrics, protocol version, seed, start and end timestamps, status.

States: `DRAFT`, `QUEUED`, `RUNNING`, `COMPLETED`, `PARTIALLY_COMPLETED`, `FAILED`, `CANCELLED`. Long runs persist progress, survive restarts (resume or mark interrupted), and support cancellation. Configuration is immutable once run; "duplicate" creates a new draft.

Allowed perturbation conditions for RQ5 (documented, standard, applied to research data only): truncation to fixed lengths, sentence shuffling controls, light typo/whitespace noise, translation round-trip, human+AI mixing at known ratios. Record every transformation applied.

### 6.5 Statistics
Use pandas, NumPy, SciPy, scikit-learn.

- **Classification rule must be explicit before any binary metric.** For score-based detectors, report threshold-free metrics (AUROC, AUPRC) and threshold-based metrics at declared thresholds. For Turnitin, the displayed percentage is an ordinal score, not a calibrated probability. Pre-register the threshold(s) (for example, "flagged if at or above 20%") in the experiment before looking at results.
- Metrics: accuracy, precision, recall, specificity, F1, FPR, FNR, AUROC, AUPRC, Cohen's kappa, confusion matrices, calibration curves and ECE where applicable.
- **Bootstrap confidence intervals** (document-level; cluster bootstrap by author or source where multiple documents share one).
- Subgroup analysis by domain, genre, language background, length bin, provenance. Always show **n** next to every estimate; mark estimates with small n as unreliable.
- Detector agreement (kappa, Spearman) and paired comparisons (McNemar, DeLong or bootstrap for AUROC differences).
- Splits: when any fitting or threshold tuning occurs, use author-grouped and source-grouped splits and prove no leakage with a test.
- Missing is not zero. Censored is not missing. Keep these distinct in data types and in every chart.

### 6.6 UI (minimal for v1)
Pages: Overview, Documents, Experiments, Detectors, Turnitin Reports, Analysis, Reports. Every number on screen comes from stored data; empty states are meaningful. Clear failure states. Visual direction: minimal editorial, neutral backgrounds, restrained accent, excellent chart readability. Avoid generic admin-dashboard styling.

### 6.7 Reports
Generate a Markdown research report from a completed experiment: question, protocol, dataset summary with provenance counts, detector versions, results with CIs and n, subgroup tables, limitations (auto-populated: small samples, score-semantics caveats, censored values), and a reproducibility block (seed, hashes, versions, commit SHA).

## 7. Data Plan

Document in `docs/DATASETS.md`, and **verify each license before use**.

- **Human text**: openly licensed essays, Wikipedia, arXiv abstracts or full text with permissive licenses, and consented student writing.
- **AI text**: public AI-detection benchmarks (for example HC3, M4, RAID; check terms), plus text you generate yourself with recorded model, version, prompt, and settings.
- **Non-native English (RQ2)**: needs a corpus whose license permits this use; some well-known learner corpora are restricted, so confirm access terms first. If no suitable corpus is available, say so and scope RQ2 down rather than guessing labels.
- **Similarity reference corpus**: open sources only (Wikipedia dumps, arXiv, PAN plagiarism corpora).
- Commit **manifests**, not raw data. Record source, license, collection date, and consent for every dataset.

## 8. Testing and Quality Gates

- **Unit**: extraction, word count, hashing, provenance validation, DB constraints, adapter contract, every metric against hand-computed fixtures, CI coverage, missing and censored handling, report generation.
- **Integration**: real PDF upload, then extraction, then dataset, then experiment, then **real model inference (no mocks for inference tests)**, then persistence, then metrics, then report. Turnitin import with valid and mismatched documents.
- **Failure**: missing weights, missing deps, corrupt or empty PDF, duplicate document, unsupported length or language, failed inference, malformed Turnitin report, interrupted experiment, low disk.
- **Scientific tests**: leakage test for grouped splits; a test that fails if any metric is computed without a declared classification rule; a test that censored values never become zero.
- The app must never show success after a failed operation.

## 9. Working Agreement (for the coding agent)

1. Work on **one milestone only** per session. Read this spec, plan briefly, implement, test, document, stop.
2. After each milestone: run the full test suite, fix failures, update `README.md` and `docs/`, and report using the template below.
3. Do not start a later milestone or any v2 item without being told.
4. Never mark something complete unless it was run and verified. Say "not verified" when that is the case.
5. If a requirement conflicts with the Hard Boundaries, stop and ask.
6. Prefer simple, readable code in `mia-detect`. Others will study it.

**Milestone report template**
```
Milestone: <n, name>
Implemented: <list>
Verified (commands + results): <list>
Not working / not verified: <list, with exact reasons>
Deviations from spec: <list>
Known limitations: <list>
Next milestone prerequisites: <list>
```

## 10. Milestones

| # | Name | Exit criteria |
|---|------|---------------|
| 1 | Foundation | Repo layout, `./start.sh` runs both servers, SQLite schema created, health endpoint, `mia-detect` installable, LICENSE and README present |
| 2 | Documents | Upload TXT/DOCX/PDF, PyMuPDF extraction with quality warnings, provenance and language-background metadata, duplicate detection, document explorer |
| 3 | Detectors | Adapter interface; RoBERTa detector runs real inference on MPS or CPU; results persisted; `health_check` works; unavailable-detector reasons shown |
| 4 | Similarity | Winnowing similarity checker in `mia-detect`, indexed over an open corpus, with tests on known-overlap fixtures |
| 5 | Experiments | Create, run, cancel, resume; persistent progress; immutable protocol; classification rule required |
| 6 | Statistics | All metrics with bootstrap CIs, subgroup analysis, n reporting, leakage and censoring tests passing |
| 7 | Turnitin import | Manual import with mismatch safeguards, censored-value handling, report storage |
| 8 | UI and reports | Minimal pages, charts from real data, Markdown and CSV exports, clean-install verification, `docs/LIMITATIONS.md` |

## 11. Definition of Done (v1)

- `./start.sh` works on a clean Apple Silicon Mac following the README.
- A real PDF can be uploaded, extracted, labeled, and run through at least one real detector, with stored results.
- Metrics and CIs are computed from real labeled data, with sample sizes shown.
- A Turnitin report can be imported, validated, and associated without mismatches.
- A research report is generated with reproducibility metadata.
- All critical tests pass; failures surface honestly.
- `mia-detect` can be installed and used standalone.
- No fabricated results exist anywhere in the codebase or UI.
- `docs/LIMITATIONS.md` states what the platform can and cannot establish.

## 12. First Prompt to the Agent

> Read `SPEC.md` fully. Implement **Milestone 1 (Foundation)** only. Follow the Working Agreement and Hard Boundaries. When done, run all tests and reply using the milestone report template. Do not begin Milestone 2.
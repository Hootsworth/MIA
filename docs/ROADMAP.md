# MIA Roadmap: Milestones, Expected Results, and Decision Trees

Companion to `SPEC.md`. Put this at `docs/ROADMAP.md`. The spec says **what** to build; this says **in what order, what you should see, and what to do when you don't**.

---

## 0. How to use this document

**Per-milestone loop (never skip steps):**
1. Start a git branch `m<N>-<name>`.
2. Give the agent the prompt template (section 10).
3. Read the agent's report skeptically. Anything listed under "not verified" is **your** job to verify.
4. Run the **Verification checklist** yourself, by hand, in a terminal and a browser.
5. Compare against **Expected results**. If something differs, use the **If / Then** table. Do not move on with an unexplained deviation.
6. Merge to `main`, tag `v0.<N>`, and move on only after the **Exit gate** is fully met.

**Severity tags used below**
- 🔴 **Blocker**: stop; do not start the next milestone.
- 🟠 **Fix now**: fix before the milestone is tagged, but it's not a design problem.
- 🟡 **Log and continue**: record in `docs/LIMITATIONS.md` and move on.
- 🔵 **Science finding**: not a bug. It is a result. Record it faithfully; never "fix" it by tuning until the number looks good.

**Rule of thumb for scientific surprises:** a result that looks *too good* (AUROC above 0.97 on a hard task, zero false positives, perfect agreement) is **more** suspicious than one that looks bad. Check for leakage, length confounds, formatting artifacts, and duplicated documents before believing it.

**Rough time budget (solo, part-time, with an agent):** M0 half a day; M2 and M3 about 2 to 4 days each; M4 2 to 3 days; M5 2 to 3 days; M6 3 to 5 days; M7 1 to 2 days (plus waiting on Turnitin access); M8 3 to 4 days; study phase 2 to 4 weeks, mostly data collection.

---

## Stage 0: Close out Milestone 1 (Foundation)

**Goal:** the foundation actually runs end to end on your machine.

**Tasks**
1. Install Python 3.12 (`brew install python@3.12` or `uv python install 3.12`). Recreate the venv with it.
2. Change the Node check in `start.sh` to "major version >= 20" instead of checking for an LTS marker.
3. Run `./start.sh`; open `http://localhost:3000` and `http://localhost:8000/docs`.
4. Press Ctrl+C; run `lsof -i :3000 -i :8000` to confirm nothing lingers. Start again and run `./stop.sh`.
5. Run `pytest` on Python 3.12. Pin `httpx` and `starlette` versions if the deprecation warning bothers you.
6. `git init`, commit, tag `v0.1`.

**Expected results**
- Backend returns `{"status":"ok", ...}` at `/api/health`; the frontend page shows "backend: ok".
- The DB file exists at `data/mia.db`; `sqlite3 data/mia.db ".tables"` lists all 12 tables.
- Tests: 5 or more passing, no failures.
- Cold start to both URLs live: usually under about 60 seconds after dependencies are installed.

**If / Then**

| Observation | Meaning | Action |
|---|---|---|
| `start.sh` still says Python too old | venv or PATH uses 3.9 | 🔴 `which -a python3`; point the script at `python3.12` explicitly; recreate `.venv` |
| Frontend `npm install` fails on Node 26 | a dependency doesn't support new Node yet | 🟠 install Node 22 LTS via `nvm`/`fnm`, add an `.nvmrc`; keep the check at >=20 |
| Port 3000 or 8000 already in use | leftover process or other app | 🟠 have `start.sh` detect and print the PID, or make ports configurable in `.env` |
| Frontend loads but shows "backend unreachable" | CORS or wrong API URL | 🟠 check `NEXT_PUBLIC_API_URL` and CORS origins in FastAPI |
| Ctrl+C leaves orphan processes | script doesn't trap signals / kill process group | 🟠 add `trap` and kill child PIDs; verify with `lsof` |
| Tests pass on 3.11 but fail on 3.12 | version-specific dependency | 🟠 pin versions; 3.12 is the target, so fix there |

**Exit gate:** `./start.sh` and `./stop.sh` both verified by you; tests green on 3.12; tag `v0.1`.

---

## Milestone 2: Documents (ingestion and provenance)

**Objective:** real documents go in with trustworthy labels, and extraction problems are visible, never silent.

**Prerequisites:** M1 tagged. Collect a **test fixture set** (10 to 15 files): normal text PDF, multi-column PDF, PDF with headers/footers on every page, scanned image-only PDF, empty PDF, corrupt PDF (truncate a real one with `head -c 2000`), password-protected PDF, a DOCX, a TXT in UTF-8 and one in Latin-1, a duplicate of one file, a near-duplicate (same text, one paragraph changed).

**Tasks (in order)**
1. Upload endpoint with extension and MIME-sniffing validation, max size (suggest 20 MB), safe filenames, storage under `storage/documents/<uuid>/original.<ext>`.
2. SHA-256 of the original; reject exact duplicates with a clear message that links to the existing document.
3. Extractors: PyMuPDF (per-page text, paragraph preservation), python-docx, plain text with encoding detection.
4. Quality checks: word count, empty-text detection, scanned-PDF heuristic (pages with images but near-zero text), repeated-page detection, extraction-quality warnings stored in a `quality_flags` JSON field.
5. Metadata model and validation: provenance (`HUMAN` | `AI_GENERATED` | `AI_ASSISTED`), domain, genre, language, `author_language_background`, source, license, consent, generator model/version (required when AI), editing history (required when assisted).
6. **Provenance rule:** `HUMAN` requires a non-empty source and consent/license; `AI_GENERATED` requires model + version + prompt reference. Violations are rejected, not warned.
7. Near-duplicate flagging using a simple shingle Jaccard score (keep it basic here; M4 builds the real engine).
8. CSV manifest import/export.
9. UI: document list with filters, detail page with extracted text per page, metadata editor, warnings visibly displayed.
10. Audit event on every create/edit/delete.

**Expected results**

| Fixture | Expected outcome |
|---|---|
| Normal PDF | Text extracted, plausible word count (compare to a manual count: within about 2 to 3%) |
| Multi-column PDF | Extracted but reading order may interleave columns → 🟡 warning flagged, not silent |
| Header/footer PDF | Repeated-page-text flag raised |
| Scanned PDF | Flagged "likely scanned; no text layer"; **not** accepted as 0-word text document |
| Empty / corrupt / password PDF | Rejected or quarantined with a specific error message |
| Exact duplicate | Rejected, linked to original |
| Near-duplicate | Accepted but flagged with similarity score |
| Latin-1 TXT | Decoded correctly or flagged, no mojibake accepted silently |

**Verification checklist**
- Upload each fixture through the **UI**, not only the API.
- Open the original file from storage and confirm its hash equals the stored hash (originals are untouched).
- Edit metadata and confirm an audit event appears.
- Export a manifest CSV, wipe the DB, re-import, and confirm identical data.
- Try creating a `HUMAN` document with no source and confirm it is rejected.

**If / Then**

| Observation | Meaning | Action |
|---|---|---|
| Extracted text has odd ligatures ("ﬁ"), hyphenation splits, or joined words | normal PDF extraction noise | 🟡 normalize (NFKC, de-hyphenate) in a *separate derived field*; keep raw extraction; document in `METHODS.md` |
| Word counts differ >5% from manual count | tokenizer or extraction issue | 🟠 define "word" precisely (whitespace-split after normalization) and test it |
| Scanned PDFs are common in your data | OCR needed | 🟡 do **not** add OCR now; mark them unsupported in v1; log as a v2 item |
| Many near-duplicates appear | corpus has repeated sources | 🟠 add a "duplicate group" concept now, because later author/source-grouped splits depend on it |
| Agent "auto-fills" provenance or language from text content | violates "provenance is declared, never inferred" | 🔴 remove it; this breaks the scientific premise |
| Agent stores uploaded files in the DB blob | harms size and integrity | 🟠 keep files on disk, paths in DB |
| Large file upload hangs the UI | synchronous processing | 🟠 process extraction in a background task with a status field |

**Pitfalls to check the agent didn't make:** silently truncating long text; trusting file extensions; losing page references; deleting the original after extraction; treating "0 words" as valid.

**Exit gate:** all fixtures behave as in the table; manifest round-trip works; provenance rules enforced; tag `v0.2`.

---

## Milestone 3: Detectors (adapter framework and the first real detector)

**Objective:** one real detector performs genuine inference and results persist honestly.

**Prerequisites:** about 2 GB free disk; internet for the first model download; a handful of known texts (3 human-written paragraphs from before 2020, 3 pasted LLM outputs).

**Tasks**
1. Adapter interface (`metadata`, `validate`, `predict`, `health_check`) and a registry that loads adapters lazily.
2. RoBERTa OpenAI detector adapter (Hugging Face `roberta-base-openai-detector`, optionally `-large`). Pin the model **revision hash**. Record labels exactly as the model emits them.
3. Device selection: MPS if available, else CPU; set `PYTORCH_ENABLE_MPS_FALLBACK=1`; log which device ran.
4. Input handling: the model has a 512-token limit. Implement a **documented** strategy (for example chunk into windows and aggregate by mean of the fake-probability) and store the chunk-level outputs in `raw_output`.
5. `health_check` runs an actual tiny inference and reports success only if it returns.
6. Result persistence per the schema: score, **score semantics** (`probability`), label, duration, device, revision, errors.
7. Detector Registry page: status, version, device, last health check, and exact failure reason when unavailable.
8. Failure paths: missing weights, no network on first download, unsupported length (too short), non-English.

**Expected results**
- First run downloads weights (roughly 500 MB for base, over 1 GB for large); later runs load from cache in seconds.
- Inference per 512-token chunk: tens to a few hundred milliseconds on Apple Silicon.
- On your sanity texts: **do not expect clean separation.** This detector was trained on GPT-2 outputs. On ChatGPT-era text it is often unreliable; on short texts and non-native English writing it may misfire.
- Scores are valid probabilities of "fake" **under that model**, not calibrated truth.

**Verification checklist**
- `health_check` passes with weights present; **delete the cached weights** and confirm the UI shows the exact failure with no fake result.
- Run the same document twice; scores should be identical (deterministic eval mode; if not, find out why).
- Confirm a result row exists with revision hash, device, and duration.
- Submit a 20-word text; confirm `validate` returns a clear "too short" rather than a confident score.

**If / Then**

| Observation | Meaning | Action |
|---|---|---|
| MPS errors or NaNs | unsupported op on MPS | 🟠 enable fallback; if persistent, force CPU and log the reason |
| Inference is very slow (many seconds per chunk) | running on CPU, or large model | 🟡 use base model for v1; batch chunks |
| Scores are all near 0 or all near 1 regardless of text | label mapping flipped, or input not truncated/tokenized properly | 🔴 check the label order (`Real` vs `Fake`) against the model card on known texts |
| Human text scored "fake" often | typical for this old detector | 🔵 record it; this is RQ1 data, not a bug |
| Same input gives different outputs | dropout still on / `model.eval()` missing | 🟠 call `eval()` and `torch.no_grad()` |
| Model download blocked | network or HF rate limit | 🟠 document an offline procedure; allow a local weights path in `.env` |
| Agent returns a placeholder score when the model fails | violates the no-fabrication rule | 🔴 remove; failure must surface as an error state |

**Exit gate:** real inference verified by you; failure paths honest; results persisted with full metadata; tag `v0.3`.

---

## Milestone 4: Similarity checker (the clean-room core)

**Objective:** a readable, correct winnowing-based similarity engine in `mia-detect`, usable standalone.

**Prerequisites:** a small open reference corpus (for example a few thousand Wikipedia articles or a PAN plagiarism subset, license verified).

**Tasks**
1. Normalization: lowercase, Unicode NFKC, strip punctuation/whitespace noise (document exactly what is removed).
2. k-gram (word shingle) generation; choose and document **k** (try 5 words for prose) and winnowing window **w**. Guarantee threshold `t = w + k - 1`; density is about `2/(w+1)`.
3. Rolling or stable hash (for example a 64-bit hash of the shingle), with fingerprint positions retained for match spans.
4. Inverted index (hash → document + positions) in SQLite or a simple on-disk structure; keep it behind an interface so it can be swapped.
5. Matching: for a query document, collect matching fingerprints per source, merge adjacent matches into spans, compute overlap score per source (and overall).
6. Output: ranked sources, matched spans in both query and source (character offsets), overlap percentages.
7. CLI: `mia-detect index <dir>`, `mia-detect check <file>`.
8. Wire it into the detector adapter framework as a second detector (score semantics: `percentage` overlap, not a probability).
9. `docs/METHODS.md` section explaining normalization, k, w, tradeoffs, and limits.

**Expected results (test fixtures, hand-built)**

| Fixture | Expected |
|---|---|
| Query copied verbatim from an indexed doc | Near 100% overlap; the source ranked #1 |
| Copy with a few words changed per sentence | Overlap drops substantially but stays well above unrelated text |
| Heavy paraphrase (same ideas, different words) | Low overlap: **exact-match fingerprinting cannot catch this**; this is correct behavior |
| Unrelated text | Near 0%; occasional stray matches from common phrases |
| Common boilerplate ("In this paper we propose…") | Some matches; consider a stop-phrase filter (document it) |

Winnowing guarantee test: any shared substring of at least `t` words must produce at least one matching fingerprint. Test this directly with random texts.

**Verification checklist**
- Run the guarantee test over many random inserts of lengths below and above `t`.
- Index 1,000 documents, record time and index size; query time per document should be well under a second for modest corpora.
- Compare your overlap on a known pair to a simple difflib baseline.
- Check that match spans, when highlighted in the UI, really show identical text.

**If / Then**

| Observation | Meaning | Action |
|---|---|---|
| High false matches on unrelated documents | k too small or no boilerplate handling | 🟠 raise k, filter very common fingerprints, document the choice |
| Misses obvious light edits | k too large | 🟠 lower k (try 4 to 5); report a sensitivity analysis of k |
| Index becomes huge | storing all fingerprints with positions | 🟡 winnowing already thins them; consider storing positions only for top candidates |
| Slow queries | no index on hash | 🟠 add DB index on the hash column; batch lookups |
| Paraphrase not detected | expected | 🔵 note in `LIMITATIONS.md`; an embedding-based semantic layer is a v2 item |
| Self-matches against the same document in the corpus | query doc also indexed | 🟠 exclude by document ID |

**Exit gate:** guarantee test passes; fixtures behave as expected; CLI works standalone (no backend); methods doc written; tag `v0.4`.

---

## Milestone 5: Experiments (reproducible runs)

**Objective:** an experiment is a frozen, replayable protocol with persistent state.

**Tasks**
1. Experiment model with research-question link (RQ1 to RQ5), hypothesis, dataset **snapshot** (document IDs and content hashes), detector IDs and versions, conditions, seed, protocol version, **classification rule** (required), metrics list.
2. Immutability: once `QUEUED`, the protocol cannot change; "duplicate" creates a new draft.
3. Runner: asyncio worker that processes (document × detector) pairs, writes each result immediately, updates progress counters, honors cancellation between items.
4. Restart behavior: on backend startup, any `RUNNING` experiment is marked `PARTIALLY_COMPLETED`/interrupted, with a "resume" action that only runs missing pairs.
5. Failure handling: per-item errors stored; a run with some failures becomes `PARTIALLY_COMPLETED`, never `COMPLETED`.
6. Document-level perturbation conditions (for RQ5) deferred; implement only the hook and record transformations.
7. UI: create, run, watch progress, cancel, view per-item results and errors.

**Expected results**
- A 50-document × 2-detector run completes with a persisted result per pair; progress increments smoothly.
- Re-running an identical protocol (same seed, same data, same detector revision) yields **identical** scores.
- Killing the backend mid-run, then restarting, produces an interrupted state, never a stuck "RUNNING".

**Verification checklist**
- Cancel mid-run: no new results written afterward; state `CANCELLED`.
- Kill -9 the backend mid-run; restart; resume; the final results equal an uninterrupted run.
- Try to edit a queued experiment's config via API; must be refused.
- Try to run without a classification rule; must be refused.
- Force one document to fail (corrupt text); the experiment ends `PARTIALLY_COMPLETED` with the error visible.

**If / Then**

| Observation | Meaning | Action |
|---|---|---|
| Re-run gives different scores | nondeterminism (dropout, threads, seed) | 🟠 fix before M6, because statistics on irreproducible data are meaningless |
| Job lost on backend restart | in-memory state only | 🟠 persist state in DB; mark interrupted at startup |
| Progress UI freezes | blocking inference in the event loop | 🟠 run inference in a thread/process executor |
| Memory grows over a long run | model reloaded per document | 🟠 cache the loaded model in the adapter |
| Agent marks run COMPLETED with failed items | violates honesty rules | 🔴 fix state logic and add a test |
| Two experiments run at once and fight over MPS | no concurrency limit | 🟡 add a simple one-job-at-a-time queue for v1 |

**Exit gate:** reproducibility test passes; interruption and cancellation verified by you; tag `v0.5`.

---

## Milestone 6: Statistics (the credibility milestone)

**Objective:** every number is correct, qualified with a CI and n, and impossible to compute without a stated rule.

**Prerequisites:** a **labeled evaluation dataset** with at least about 100 documents per class for meaningful results (more is better; see "Study phase"). If you don't have it yet, use a public benchmark subset for development and clearly mark it as such.

**Tasks**
1. Metrics module: accuracy, precision, recall, specificity, F1, FPR, FNR, AUROC, AUPRC, Cohen's kappa, confusion matrix, calibration curve and ECE.
2. Classification rules: fixed threshold, threshold chosen on a **separate** validation split (grouped by author/source), or Youden/other; the rule is recorded in the experiment.
3. Bootstrap CIs: resample documents (B at least 2000; use 10000 for final reports); **cluster bootstrap** by author/source if documents share authors.
4. Subgroup analysis: domain, genre, language background, length bin, provenance. Always show n; flag n below a configurable floor (suggest 30 per cell) as "unreliable".
5. Detector comparison: agreement (kappa, Spearman), paired tests (McNemar for decisions; bootstrap difference for AUROC).
6. Censoring/missing: separate types for `value`, `censored(<=x or "below display")`, `missing`; metrics must define how they treat each.
7. Leakage guard: tests that grouped splits never share authors or duplicate groups across train/val/test.
8. API endpoints and a results table; charts come later (M8).

**Expected results (validate your code against references)**
- For small hand-computed confusion matrices, every metric matches to 6 decimal places.
- AUROC matches `sklearn.metrics.roc_auc_score` exactly; bootstrap CI widths shrink as n grows. For orientation, with about 100 documents per class, an AUROC CI is typically several points wide (on the order of ±0.05 to ±0.08), and much wider for subgroups.
- A random-scores baseline gives AUROC about 0.5 with a CI containing 0.5. If it doesn't, there's a bug or leakage.
- A perfect-score fixture gives AUROC 1.0; an inverted one gives 0.0.

**Verification checklist**
- Unit-test every metric on tiny fixtures and on randomized data against scikit-learn/SciPy.
- Shuffle labels randomly: AUROC must collapse to about 0.5 (a *permutation sanity test*).
- Run the leakage test deliberately with a leaky split; it must fail.
- Try to compute a binary metric without a classification rule; must be refused.
- Check a censored value never contributes as 0 to means or thresholds.

**If / Then**

| Observation | Meaning | Action |
|---|---|---|
| AUROC suspiciously high (above 0.97) on a hard task | leakage, length confound, formatting artifact, or duplicate docs | 🔴 audit: check length distributions by class, strip headers/boilerplate, deduplicate, rerun with grouped split |
| AUROC near 0.5 for a detector | detector is weak on this data | 🔵 report it; check the label mapping once, then accept it |
| AUROC below 0.5 | score direction flipped, or detector systematically wrong on this domain | 🟠 verify direction; if the direction is right, 🔵 it's a finding |
| CI extremely wide | small n | 🟡 report as inconclusive; do not draw conclusions |
| Subgroup n very small | too few samples | 🟡 mark unreliable; merge bins only with a documented rule set **before** looking at results |
| Precision/recall wildly different from expectation | class imbalance | 🟠 report prevalence; use AUPRC and balanced accuracy alongside |
| Calibration curve far from diagonal | scores not probabilities | 🔵 report ECE; recommend not interpreting scores as probabilities |
| Agent computes a metric from an uncalibrated percentage as a probability | violates the spec | 🔴 fix and add a test |

**Pitfalls:** tuning the threshold on the test set; reporting only the best subgroup; changing bins after seeing results (this is p-hacking, so pre-register them).

**Exit gate:** all metric tests pass vs references; permutation and leakage tests exist and pass; rule-required enforcement verified; tag `v0.6`.

---

## Milestone 7: Turnitin report import

**Objective:** attach black-box results to the correct documents without corrupting the data.

**Prerequisites (non-technical, do these first)**
- Confirm with your institution (library or academic-integrity office) that submitting your **own consented research documents** for this purpose is allowed, and in what way. Get that in writing if possible.
- Use a submission method that does not add the documents to a student repository in a way that could create integrity problems later (ask your administrator about repository settings).
- Prepare the exact files you'll submit (the same bytes you store), named by document UUID.

**Tasks**
1. Import form: select document, enter or upload: submission reference, report timestamp, similarity percentage (if shown), AI-writing figure **exactly as displayed**, passage annotations (if shown), eligible word count, detector version if disclosed, original report file.
2. Association safeguards: record the submitted-file hash; require the researcher to confirm the document UUID matches the report's file name/reference; refuse if the hash or word count (eligible words vs your count, within a tolerance) is inconsistent.
3. Censored-value model: store the raw string (for example an asterisk, "no score", or a percentage); parse into a typed value (`value`, `censored_low`, `not_displayed`).
4. Validation: ranges 0 to 100; required fields; helpful rejection messages.
5. Store the original report file under `storage/reports/` with hash.
6. Results view: Turnitin rows next to other detectors for the same document.

**Expected results**
- Import of valid data works, appears on the document page and in experiment results as a detector `turnitin` with score semantics `percentage`.
- Mismatched report is refused with an explanation.
- For short or heavily low-scoring documents, expect the AI figure to be hidden or shown in a limited way; those must appear as censored, not 0.

**Verification checklist**
- Import 3 to 5 real reports by hand; compare each stored value against the original screenshot/PDF.
- Attach a report to the wrong document deliberately; it must be refused or flagged.
- Confirm censored values appear as "censored" in tables and are excluded or handled per M6 rules.
- Confirm raw displayed strings are stored verbatim.

**If / Then**

| Observation | Meaning | Action |
|---|---|---|
| Report format differs from what the spec assumed | vendor UI changed | 🟠 make the form flexible; store raw strings and parse separately; update `METHODS.md` |
| Most AI scores are censored/hidden | typical for low-AI or short documents | 🔵 report the censoring rate; analyze with censoring-aware methods (for example treat "below displayed threshold" as an ordered category) |
| Eligible word count differs a lot from yours | Turnitin excludes quotes, bibliography, etc. | 🟡 store both; use theirs for length-bin analysis of Turnitin results |
| Sample is tiny (below about 30) | access/time limits | 🟡 report descriptive stats and exact intervals only (for example Clopper–Pearson); no strong claims |
| Institution says no | policy | 🔴 stop this milestone; keep the importer built but unused and proceed with open detectors only, which still answers RQ1 to RQ3 and RQ5 |
| Same document scored differently when submitted twice | non-determinism or version change | 🔵 valuable finding; record versions and timestamps, and submit duplicates on purpose later as a consistency experiment |

**Exit gate:** import and refusal paths verified; censored values correct; written institutional permission on file (or milestone explicitly skipped); tag `v0.7`.

---

## Milestone 8: UI, reports, and clean-install verification

**Objective:** a researcher can go from raw files to a reproducible report, and a stranger can install it.

**Tasks**
1. Pages: Overview, Documents, Experiments, Detectors, Turnitin Reports, Analysis, Reports. Charts (Recharts): ROC curves, score distributions by provenance, confusion matrices, subgroup bars with CI whiskers and n labels, length vs score scatter.
2. Every chart uses stored data; empty states for no data; a visible "n too small" marker.
3. Report generator (Markdown + CSV): question, protocol, dataset summary, detector versions, metrics with CIs and n, subgroup tables, auto-generated limitations (small n, score semantics, censoring), reproducibility block (seed, hashes, versions, git commit).
4. `docs/LIMITATIONS.md`, `docs/DATASETS.md`, `docs/METHODS.md` complete.
5. Clean-install test: new clone, fresh user or fresh directory, follow the README only.
6. License headers, `CITATION.cff`, `CONTRIBUTING.md`.

**Expected results**
- Generating a report from a finished experiment takes seconds and reproduces the same numbers as the Analysis page.
- Re-running the experiment's protocol and regenerating yields the same metrics (within bootstrap Monte Carlo error; fix the seed to get identical results).
- Clean install works following README steps with no undocumented knowledge.

**Verification checklist**
- Click through every page with an empty DB (no crashes, helpful empty states) and with real data.
- Compare three numbers on screen to a manual scikit-learn computation.
- Run the clean install on a different machine or a new macOS user account.
- Run a link and secret scan: no `.env`, API keys, or personal data committed.

**If / Then**

| Observation | Meaning | Action |
|---|---|---|
| Charts show numbers that differ from the API | frontend recomputes | 🔴 charts must render API values only |
| A chart looks great but n is tiny | misleading visualization | 🟠 add n labels and CI whiskers; gray out unreliable cells |
| Clean install fails | hidden assumptions | 🟠 fix the README/scripts; repeat until it works unaided |
| Report numbers shift between runs | bootstrap not seeded | 🟠 record and reuse the seed |
| Dashboard has hard-coded or placeholder values | spec violation | 🔴 remove |

**Exit gate:** clean install works unaided; report reproducible; docs complete; tag `v1.0.0`.

---

## Study phase (after v1): produce actual findings

This is where the project becomes research rather than software.

### S1. Build the dataset (the long pole; start early, in parallel with M5 to M7)
- **Human text:** pre-2020 or openly licensed essays and articles; consented student writing (with written consent and anonymization).
- **AI text:** generate with at least two or three different current models and record the model, version, prompt, and temperature. Use **matched prompts** (same topic/genre/length target as the human texts).
- **Non-native English:** needed for RQ2; obtain a corpus whose license allows it, or collect consented samples. If you can't, **narrow RQ2 honestly** instead of guessing labels.
- **Balance and control:** match length distributions across classes as best you can, or stratify; otherwise length becomes a confound.
- **Document everything** in `DATASETS.md`; commit manifests, not the raw data.

Target sizes: at least 100 per class for headline RQ1 results; 50 or more per subgroup cell for subgroup claims. Smaller means descriptive only.

### S2. Pre-register (one page, committed to git *before* running)
Write down: research question, hypotheses, thresholds, length bins, subgroup definitions, primary metric, and what counts as a meaningful difference. Commit it. This is your protection against fooling yourself.

### S3. Run RQ1 to RQ3 on open detectors, then RQ4 on the Turnitin subset

**Interpreting RQ1 (accuracy):**

| Result | Interpretation | Next step |
|---|---|---|
| AUROC about 0.5 to 0.65 | detector barely beats chance on modern text | 🔵 headline finding; check it isn't a label-mapping bug using older-model text where it should work better |
| AUROC 0.7 to 0.9 with wide CI | moderate; limited by n | report with CI; increase n |
| AUROC above 0.95 | verify leakage and confounds first (see M6 table) | re-run with length-matched and deduplicated data |
| High AUROC but poor accuracy at the default threshold | threshold miscalibrated | report threshold-free metrics; show accuracy at several pre-declared thresholds |

**Interpreting RQ2 (fairness):** compare FPR on **human-written** text, native vs non-native, with bootstrap CIs on the *difference*.
- Difference clearly above zero (CI excludes 0): 🔵 evidence of bias; report effect size and n; discuss possible causes (lower perplexity in constrained vocabulary) without over-claiming.
- CI includes 0 with wide width: **inconclusive, not evidence of no bias**; say so.
- Never tune thresholds separately per group in the headline analysis; you may add that as a clearly labeled exploratory analysis.

**Interpreting RQ3 (length):** plot score and error rates vs length bins. Expect error rates to be worse on short texts. If not, check that length bins aren't confounded with domain.

**Interpreting RQ4 (open detectors vs Turnitin):** with small n, report a 2×2 agreement table with exact (Clopper–Pearson) intervals, a list of disagreement cases for qualitative inspection (document features such as length, genre, and provenance), and no strong generalizations.

### S4. RQ5 robustness (only on research data, standard perturbations)
Apply documented transformations (truncation, noise, translation round-trip, mixing ratios) and measure score shift. Report as **detector failure modes**. Do not publish or build workflows aimed at maximizing evasion.

### S5. Write up
- Short paper or technical report: intro, related work (MOSS/winnowing, GPT-2 output detector, Binoculars, Fast-DetectGPT, published evaluations of detector bias), methods, results with CIs and n, limitations, ethics.
- Release: repo public with `LICENSE`, `CITATION.cff`, dataset manifests, pre-registration, and a reproducibility script (`make reproduce`).
- Venue ideas: arXiv, a workshop on NLP/education integrity, or a student research showcase.

---

## v2 backlog (only after S3 produces findings)

| Item | Trigger to start |
|---|---|
| Binoculars | RoBERTa is too weak to be a useful baseline; you have a machine with enough memory for two LLMs |
| Fast-DetectGPT | want a sampling-free curvature baseline |
| Embedding-based semantic similarity | paraphrase blind spot matters for your findings |
| Auth and roles | other people will use a shared instance |
| Playwright E2E tests | the UI stabilizes |
| Alembic migrations | the schema starts changing across versions with data you care about |
| OCR for scanned PDFs | scanned documents form a meaningful share of your data |
| Other languages | you have labeled non-English data |

---

## Cross-cutting rules (apply at every stage)

**Agent overclaim checks.** Before accepting a report: (1) run the commands yourself; (2) open the app and click the feature; (3) grep for suspicious literals (`grep -rn "TODO\|placeholder\|mock\|fake\|random.uniform" backend frontend packages`); (4) check that test counts increased and none were deleted or skipped; (5) confirm the agent didn't weaken a test to make it pass (`git diff` on tests).

**Git hygiene.** Branch per milestone; tag on exit; never let the agent rewrite history; keep `data/` and `storage/` out of git (commit only manifests).

**Failure triage ladder (when stuck for more than an hour).** 1) Reproduce in the smallest case. 2) Add a failing test. 3) Ask the agent to explain the root cause **before** fixing. 4) If it proposes disabling a check, refuse. 5) If a design is wrong, update `SPEC.md` first, then code.

**Scientific integrity.** Pre-register, report n and CIs, publish negative results, never tune on test data, never present an uncalibrated score as a probability, and describe commercial-tool results strictly as observations of that tool's behavior on your data.

**Ethics and legal.** Consent for any human-authored student data; anonymize; follow institutional rules for any Turnitin use; no scraping, no automated submission, no evasion tooling; verify every dataset and model license before redistribution.

---

## Quick reference: prompt template for any milestone

```
Read SPEC.md and docs/ROADMAP.md fully. Milestones 1 through <N-1> are complete, committed, and tagged. First run ./start.sh and the full test suite and fix any regressions. Then implement Milestone <N> (<name>) ONLY. Follow the Tasks list in ROADMAP.md, the Working Agreement, and the Hard Boundaries in SPEC.md. Run every verification step yourself and show real output. If an observation matches an If/Then row, tell me which row and what you did. Report using the milestone template, then stop and wait.
```

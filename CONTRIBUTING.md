+# Contributing to MIA
+
+Thanks for helping improve MIA. Contributions should make detector behavior easier to inspect and measure while preserving the project's research and privacy boundaries.
+
+## Before proposing a change
+
+- Read [`SPEC.md`](SPEC.md), especially Hard Boundaries and Working Agreement, and review [`docs/ROADMAP.md`](docs/ROADMAP.md).
+- Keep detector implementations clean-room and grounded in public papers or documentation. Do not add proprietary code, weights, data, scraping, or automated commercial-detector submissions.
+- Never add paraphrasing, humanizing, or detector-bypass features.
+- Use only public-licensed data or consented data. Verify licenses and commit manifests rather than raw corpora or private documents.
+- Do not infer authorship. Keep declared provenance distinct from detector outputs.
+
+## Development
+
+1. Create a focused branch and describe the change and its research motivation.
+2. Keep `mia-detect` independent of the web app and database, and keep its implementation simple enough to study.
+3. Add or update tests for behavior and failure paths. Do not weaken tests to make a change pass.
+4. Run the relevant tests, then the complete Python test suite and frontend build for cross-cutting changes.
+5. Update `README.md` and the relevant methods, dataset, or limitation documentation.
+6. Include real command output in the pull request summary. Identify anything not verified and avoid claims beyond the data.
+
+## Pull requests
+
+Use small, reviewable pull requests. Explain the behavior change, test commands and results, data or model provenance, and any limitations. Never include `.env`, credentials, original research documents, model caches, generated SQLite indexes, or other private/local storage. Follow the existing Apache-2.0 license for contributions.

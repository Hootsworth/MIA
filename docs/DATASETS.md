# Datasets

No research data is bundled in the repository. Before any dataset is used, record its source, license, collection date, provenance, and consent status; verify that its license permits the intended research use. Commit manifests, not raw corpora.

## Milestone 4 reference corpus

The similarity development corpus uses English Wikipedia namespace-0 article introductions collected through the official MediaWiki API. Wikimedia Foundation guidance says most Wikipedia text is available under CC BY-SA 4.0 and GFDL; the collector declares CC BY-SA 4.0, preserves a permanent link to each page revision for attribution, and records the page and revision IDs, collection timestamp, UTF-8 content hash, and word count. Individual page notices must be respected; remove any page whose notice indicates incompatible terms before using it. Keep introductions in ignored `storage/reference-corpus/` and the SQLite index in ignored `storage/similarity/`. Only the per-page manifest under `data/manifests/` is committed. Do not redistribute the corpus or index unless ShareAlike and attribution obligations have been reviewed.

Rebuild a local 1,000-page sample (internet required):

```sh
.venv/bin/python scripts/fetch_wikipedia_corpus.py --count 1000 --output storage/reference-corpus/wikipedia-en
.venv/bin/python -m mia_detect index storage/reference-corpus/wikipedia-en --database storage/similarity/index.sqlite3
```

The random selection is a development reference corpus, not a representative sample for performance claims. The committed manifest records the exact revisions selected in one collection run.

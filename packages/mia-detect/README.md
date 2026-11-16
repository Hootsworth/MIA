# mia-detect

Standalone Python package for studying documented detection methods. The package has no runtime dependencies outside the Python standard library and has no web or database-server dependency.

## Install

```sh
python -m pip install .
```

## Similarity CLI

Index UTF-8 `.txt` references from a directory. The command creates a local SQLite inverted index (default `.mia-index.sqlite3` in the current directory). Keep reference text and index files local; commit their source manifest only.

```sh
mia-detect index path/to/references --database path/to/references.sqlite3
mia-detect check path/to/query.txt --database path/to/references.sqlite3
```

The default configuration uses five-word shingles (`k=5`) and four shingle hashes per winnowing window (`w=4`), guaranteeing a shared fingerprint for an identical run of at least eight words. The check output contains source-ranked exact-match spans and query-word overlap percentages. These percentages are not probabilities, plagiarism findings, or authorship labels.

Reference files can be accompanied by `corpus-manifest.json` with a `documents` array containing each file's relative `path`, `title`, `source_url`, and `license`. The CLI carries this attribution into indexed matches.

Read [`../../docs/METHODS.md`](../../docs/METHODS.md) and [`../../docs/LIMITATIONS.md`](../../docs/LIMITATIONS.md) for algorithm details and boundaries.

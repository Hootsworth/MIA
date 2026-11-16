from __future__ import annotations

"""Command line interface for building and querying a local similarity index."""

import argparse
import json
from pathlib import Path
import sys

from .index import SQLiteFingerprintIndex
from .matching import check_text, index_directory
from .winnowing import DEFAULT_K, DEFAULT_W


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mia-detect", description="Index and compare text using winnowing fingerprints.")
    commands = parser.add_subparsers(dest="command", required=True)

    index_command = commands.add_parser("index", help="index UTF-8 .txt files in a corpus directory")
    index_command.add_argument("directory", type=Path)
    index_command.add_argument("--database", type=Path, default=Path(".mia-index.sqlite3"))
    index_command.add_argument("--manifest", type=Path, help="JSON metadata manifest (defaults to corpus-manifest.json in the directory)")
    index_command.add_argument("--k", type=int, default=DEFAULT_K, help=f"words per shingle (default {DEFAULT_K})")
    index_command.add_argument("--w", type=int, default=DEFAULT_W, help=f"k-grams per winnowing window (default {DEFAULT_W})")

    check_command = commands.add_parser("check", help="compare a UTF-8 text file to an existing index")
    check_command.add_argument("file", type=Path)
    check_command.add_argument("--database", type=Path, default=Path(".mia-index.sqlite3"))
    check_command.add_argument("--limit", type=int, default=20, help="maximum ranked sources to print")
    check_command.add_argument("--exclude-source", action="append", default=[],
                               help="source ID to exclude (repeat for multiple IDs)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "index":
            manifest_path = args.manifest or args.directory / "corpus-manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else None
            index = SQLiteFingerprintIndex(args.database, k=args.k, w=args.w)
            count = index_directory(args.directory, index, manifest)
            print(json.dumps({"indexed_files": count, "documents_in_index": index.document_count(),
                              "database": str(args.database), "k": args.k, "w": args.w,
                              "guaranteed_shared_words": args.k + args.w - 1}, indent=2))
            return 0

        index = SQLiteFingerprintIndex(args.database)
        text = args.file.read_text(encoding="utf-8")
        print(json.dumps(check_text(text, index, limit=args.limit,
                                   exclude_source_ids=set(args.exclude_source)).to_dict(),
                          ensure_ascii=False, indent=2))
        return 0
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(f"mia-detect: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

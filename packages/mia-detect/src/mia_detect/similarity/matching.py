from __future__ import annotations

"""Exact-fingerprint matching, merged text spans, and overlap summaries."""

from dataclasses import asdict, dataclass
from pathlib import Path

from .index import SQLiteFingerprintIndex
from .normalize import NormalizedText, Token, normalize_text
from .winnowing import DEFAULT_K, DEFAULT_W, Fingerprint, fingerprint_text


@dataclass(frozen=True)
class MatchSpan:
    query_char_start: int
    query_char_end: int
    source_char_start: int
    source_char_end: int
    query_text: str
    source_text: str


@dataclass(frozen=True)
class SourceMatch:
    source_id: str
    title: str
    source_url: str
    license_name: str
    matched_query_tokens: int
    overlap_percentage: float
    spans: tuple[MatchSpan, ...]

    def to_dict(self) -> dict:
        result = asdict(self)
        result["spans"] = [asdict(span) for span in self.spans]
        return result


@dataclass(frozen=True)
class MatchReport:
    query_token_count: int
    overall_matched_tokens: int
    overall_overlap_percentage: float
    sources: tuple[SourceMatch, ...]
    k: int
    w: int
    threshold_words: int

    def to_dict(self) -> dict:
        result = asdict(self)
        result["sources"] = [source.to_dict() for source in self.sources]
        return result


def _word_span(tokens: tuple[Token, ...], start: int, end: int) -> tuple[int, int]:
    return tokens[start].start, tokens[end - 1].end


def _expand_seed(query: NormalizedText, source: NormalizedText, q_position: int,
                 s_position: int, k: int) -> tuple[int, int, int, int]:
    q_start, s_start = q_position, s_position
    q_end, s_end = q_position + k, s_position + k
    while q_start > 0 and s_start > 0 and query.tokens[q_start - 1].text == source.tokens[s_start - 1].text:
        q_start -= 1
        s_start -= 1
    while q_end < len(query.tokens) and s_end < len(source.tokens) and query.tokens[q_end].text == source.tokens[s_end].text:
        q_end += 1
        s_end += 1
    return q_start, q_end, s_start, s_end


def _merge_segments(segments: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    # One offset difference preserves alignment when repeated phrases occur.
    groups: dict[int, list[tuple[int, int, int, int]]] = {}
    for segment in segments:
        groups.setdefault(segment[0] - segment[2], []).append(segment)
    merged: list[tuple[int, int, int, int]] = []
    for group in groups.values():
        group.sort()
        current = list(group[0])
        for segment in group[1:]:
            if segment[0] <= current[1] and segment[2] <= current[3]:
                current[1] = max(current[1], segment[1])
                current[3] = max(current[3], segment[3])
            else:
                merged.append(tuple(current))
                current = list(segment)
        merged.append(tuple(current))
    return sorted(merged)


def check_text(text: str, index: SQLiteFingerprintIndex, *, k: int = DEFAULT_K,
               w: int = DEFAULT_W, limit: int | None = None,
               exclude_source_ids: set[str] | None = None) -> MatchReport:
    """Check text against an index and return merged, source-attributed spans.

    Overlap percentages use the number of distinct query words covered by an
    exact normalized match divided by the query's word count. They are not
    probabilities or plagiarism findings.
    """
    if k < 1 or w < 1:
        raise ValueError("k and w must be at least 1")
    query = normalize_text(text)
    query_fingerprints = fingerprint_text(query, k=k, w=w)
    candidates = index.candidates(query_fingerprints)
    by_source: dict[str, list[tuple[int, int]]] = {}
    for candidate in candidates:
        by_source.setdefault(candidate["source_id"], []).append(
            (candidate["query_position"], candidate["source_position"])
        )

    query_covered: set[int] = set()
    results: list[SourceMatch] = []
    for source_id, seeds in by_source.items():
        if source_id in (exclude_source_ids or set()):
            continue
        document = index.get_document(source_id)
        if not document:
            continue
        source_text = document["text"]
        source = normalize_text(source_text)
        segments = {
            _expand_seed(query, source, q_position, s_position, k)
            for q_position, s_position in seeds
        }
        merged = _merge_segments(list(segments))
        source_covered: set[int] = set()
        spans: list[MatchSpan] = []
        for q_start, q_end, s_start, s_end in merged:
            source_covered.update(range(q_start, q_end))
            query_covered.update(range(q_start, q_end))
            q_char_start, q_char_end = _word_span(query.tokens, q_start, q_end)
            s_char_start, s_char_end = _word_span(source.tokens, s_start, s_end)
            spans.append(MatchSpan(
                query_char_start=q_char_start,
                query_char_end=q_char_end,
                source_char_start=s_char_start,
                source_char_end=s_char_end,
                query_text=text[q_char_start:q_char_end],
                source_text=source_text[s_char_start:s_char_end],
            ))
        query_count = len(query.tokens)
        overlap = (100.0 * len(source_covered) / query_count) if query_count else 0.0
        results.append(SourceMatch(
            source_id=source_id,
            title=document["title"],
            source_url=document["source_url"],
            license_name=document["license_name"],
            matched_query_tokens=len(source_covered),
            overlap_percentage=overlap,
            spans=tuple(spans),
        ))

    results.sort(key=lambda match: (-match.overlap_percentage, match.source_id))
    if limit is not None:
        if limit < 0:
            raise ValueError("limit must not be negative")
        results = results[:limit]
    query_count = len(query.tokens)
    overall = (100.0 * len(query_covered) / query_count) if query_count else 0.0
    return MatchReport(query_token_count=query_count,
                       overall_matched_tokens=len(query_covered),
                       overall_overlap_percentage=overall,
                       sources=tuple(results), k=k, w=w,
                       threshold_words=k + w - 1)


def index_directory(directory: str | Path, index: SQLiteFingerprintIndex,
                    manifest: dict | None = None) -> int:
    """Index UTF-8 .txt files recursively and return the number of files read."""
    root = Path(directory)
    if not root.is_dir():
        raise FileNotFoundError(f"Corpus directory does not exist: {root}")
    metadata = {item["path"]: item for item in (manifest or {}).get("documents", [])}
    count = 0
    for path in sorted(root.rglob("*.txt")):
        relative = path.relative_to(root).as_posix()
        details = metadata.get(relative, {})
        text = path.read_text(encoding="utf-8")
        index.add_document(
            relative,
            details.get("title", relative),
            text,
            source_url=details.get("source_url", ""),
            license_name=details.get("license", ""),
        )
        count += 1
    return count

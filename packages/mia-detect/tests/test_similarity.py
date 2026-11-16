import random
import sqlite3

import pytest

from mia_detect.similarity import (
    DEFAULT_K,
    DEFAULT_W,
    SQLiteFingerprintIndex,
    check_text,
    fingerprint_text,
    make_shingles,
    normalize_text,
    stable_hash,
)


REFERENCE = (
    "In a quiet observatory, researchers compare the paths of distant stars. "
    "Careful measurements reveal how gravity shapes each orbit over many years. "
    "The team publishes its method and data so other astronomers can repeat the study. "
    "Clear records help distinguish a real signal from an instrument error."
)


def test_normalization_nfkc_casefold_punctuation_and_raw_offsets():
    raw = "  ＦＵＬＬ-width, CAFÉ! ﬁsh's  "
    normalized = normalize_text(raw)
    assert normalized.words == ("full", "width", "café", "fish", "s")
    assert raw[normalized.tokens[0].start:normalized.tokens[0].end] == "ＦＵＬＬ"
    assert raw[normalized.tokens[2].start:normalized.tokens[2].end] == "CAFÉ"
    assert raw[normalized.tokens[3].start:normalized.tokens[3].end] == "ﬁsh"


def test_shingle_and_winnowing_parameters_are_validated():
    with pytest.raises(ValueError, match="k must"):
        make_shingles("some words", k=0)
    with pytest.raises(ValueError, match="w must"):
        fingerprint_text("some words here", w=0)
    assert (DEFAULT_K, DEFAULT_W, DEFAULT_K + DEFAULT_W - 1) == (5, 4, 8)
    assert stable_hash("one two three four five") == stable_hash("one two three four five")


def test_winnowing_guarantee_for_deterministic_random_inserts():
    rng = random.Random(104729)
    vocabulary = [f"word{i}" for i in range(80)]
    threshold = DEFAULT_K + DEFAULT_W - 1
    for _ in range(250):
        length = rng.randint(threshold, threshold + 40)
        shared = [rng.choice(vocabulary) for _ in range(length)]
        left = [rng.choice(vocabulary) for _ in range(rng.randint(0, 12))] + shared + [rng.choice(vocabulary) for _ in range(rng.randint(0, 12))]
        right = [rng.choice(vocabulary) for _ in range(rng.randint(0, 12))] + shared + [rng.choice(vocabulary) for _ in range(rng.randint(0, 12))]
        left_hashes = {item.value for item in fingerprint_text(" ".join(left))}
        right_hashes = {item.value for item in fingerprint_text(" ".join(right))}
        assert left_hashes & right_hashes, f"missed shared run of {length} words"


def test_verbatim_copy_ranks_source_and_returns_identical_spans(tmp_path):
    index = SQLiteFingerprintIndex(tmp_path / "refs.sqlite3")
    index.add_document("astro/page-1", "Orbit observations", REFERENCE,
                       source_url="https://example.org/orbit", license_name="CC BY-SA 4.0")
    result = check_text(REFERENCE, index)
    assert result.sources[0].source_id == "astro/page-1"
    assert result.overall_overlap_percentage == 100.0
    assert result.sources[0].overlap_percentage == 100.0
    assert result.sources[0].spans[0].query_text == result.sources[0].spans[0].source_text
    assert result.sources[0].source_url == "https://example.org/orbit"
    assert result.sources[0].license_name == "CC BY-SA 4.0"
    assert check_text(REFERENCE, index, exclude_source_ids={"astro/page-1"}).sources == ()


def test_light_edits_keep_matches_but_unrelated_and_paraphrase_do_not(tmp_path):
    index = SQLiteFingerprintIndex(tmp_path / "refs.sqlite3")
    index.add_document("astro/page-1", "Orbit observations", REFERENCE)
    edited = REFERENCE.replace("Careful measurements reveal", "Accurate measurements reveal")
    edit_result = check_text(edited, index)
    assert edit_result.sources[0].overlap_percentage > 50

    unrelated = "".join(f"Cooking recipe ingredients use basil and tomatoes for dinner {i}. " for i in range(10))
    assert check_text(unrelated, index).overall_overlap_percentage == 0.0

    paraphrase = (
        "Observers in a scientific station track celestial motion. "
        "Calculations describe attraction and circular movement through decades. "
        "Scientists disclose their process and observations for reproduction by peers. "
        "Documentation lets investigators separate authentic findings from equipment faults."
    )
    assert check_text(paraphrase, index).overall_overlap_percentage == 0.0


def test_sqlite_index_enables_foreign_keys_and_reindexes_idempotently(tmp_path):
    database = tmp_path / "refs.sqlite3"
    index = SQLiteFingerprintIndex(database)
    index.add_document("one", "First", REFERENCE)
    original = check_text(REFERENCE, index).overall_overlap_percentage
    index.add_document("one", "First revision", REFERENCE + " Additional words clarify the telescope calibration.")
    assert index.document_count() == 1
    assert check_text(REFERENCE, index).overall_overlap_percentage == original
    with index._connect() as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("INSERT INTO fingerprints VALUES ('missing',0,'x','x',0,1)")

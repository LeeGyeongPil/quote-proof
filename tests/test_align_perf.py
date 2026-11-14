"""AC-5: candidate narrowing equals the full window scan, large sources stay fast, autojunk stays off."""
from __future__ import annotations

import random
import time

import _qp_align as align
from _qp_sources import SourceText

VOCAB = ("alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron pi rho sigma tau upsilon "
         "phi chi psi omega").split()


def make_words(rng: random.Random, n: int, vocab=None) -> list:
    pool = vocab or [f"w{k}{rng.choice('abcdefgh')}" for k in range(4000)]
    return [rng.choice(pool) for _ in range(n)]


def test_narrowing_matches_full_scan_on_random_cases():
    rng = random.Random(20261114)
    for case in range(50):
        words = make_words(rng, rng.randint(3000, 6000), vocab=None if case % 2 else VOCAB * 4)
        src = SourceText("big.txt", " ".join(words))
        start = rng.randint(0, len(words) - 40)
        n = rng.randint(8, 30)
        q = words[start:start + n]
        for _ in range(rng.randint(1, max(1, n // 8))):         # a few edits keep the ratio above 0.8
            q[rng.randrange(n)] = "zzedit"
        quote = " ".join(q)
        narrow, nr = align.find_approximate(quote, src, 0.8)
        full, fr = align.find_approximate(quote, src, 0.8, full_scan=True)
        assert (narrow is None) == (full is None), case
        if full is not None:
            assert (narrow.start, narrow.end, narrow.ratio) == (full.start, full.end, full.ratio), case
            assert nr == fr


def test_narrowing_is_really_used_on_large_sources(monkeypatch):
    rng = random.Random(1)
    words = make_words(rng, 5000)
    src = SourceText("big.txt", " ".join(words))
    quote = " ".join(words[100:120][:10] + ["zzedit"] + words[121:130])
    scanned = []
    real = align.window_ratios
    monkeypatch.setattr(align, "window_ratios", lambda q, u, starts: (scanned.append(len(starts)), real(q, u, starts))[1])
    align.find_approximate(quote, src, 0.8)
    assert scanned and scanned[0] <= align.MAX_CANDIDATE_WINDOWS < len(words)


def test_small_sources_are_scanned_in_full(monkeypatch):
    scanned = []
    real = align.window_ratios
    monkeypatch.setattr(align, "window_ratios", lambda q, u, starts: (scanned.append(len(starts)), real(q, u, starts))[1])
    src = SourceText("s.txt", " ".join(VOCAB * 3))
    align.find_approximate("alpha beta gamma delta zzedit zeta eta theta", src, 0.5)
    assert scanned == [len(VOCAB) * 3 - 8 + 1]


def test_twenty_quotes_against_a_100k_word_source_under_three_seconds(cli, tree, tmp_path):
    rng = random.Random(7)
    words = make_words(rng, 100_000)
    root = tree({"big.txt": " ".join(words)})
    paras = []
    for k in range(20):
        s = 4000 + k * 4500
        q = words[s:s + 12]
        if k % 2:
            q[5] = "zzedit"           # approximate
        if k % 5 == 4:
            q[2], q[9] = "zzone", "zztwo"
        paras.append('Quote %d: "%s" (big.txt).' % (k, " ".join(q)))
    rep = tmp_path / "r.md"
    rep.write_text("\n\n".join(paras) + "\n")
    started = time.perf_counter()
    res = cli("verify", str(rep), "--root", str(root), "--json")
    elapsed = time.perf_counter() - started
    assert elapsed < 3.0, elapsed
    summary = res.json()["summary"]
    # even quotes are untouched (8 after the two with two edits), the rest differ by one to three words
    assert summary["exact"] + summary["normalized"] == 8
    assert summary["approximate"] >= 8 and summary["not_found"] <= 2
    assert summary["source_missing"] == 0


def test_every_sequence_matcher_uses_autojunk_false(monkeypatch):
    calls = []
    real = align.SequenceMatcher

    def spy(*args, **kwargs):
        calls.append(kwargs.get("autojunk"))
        return real(*args, **kwargs)

    monkeypatch.setattr(align, "SequenceMatcher", spy)
    src = SourceText("s.txt", "one two three four five six seven eight nine ten " * 40)
    align.find_approximate("one two three four five zzedit seven eight nine ten", src, 0.5)
    assert calls and all(c is False for c in calls)


def test_autojunk_would_change_the_result_on_long_repetitive_input():
    window = ["a", "go"] * 125            # 250 tokens, one of them very frequent
    quote = ["go", "a"] * 125
    from difflib import SequenceMatcher
    # with autojunk on, the frequent tokens are ignored and almost nothing matches
    assert SequenceMatcher(None, window, quote, autojunk=True).ratio() == 0.0
    ratio, start = align.window_ratios(quote, window, [0])
    assert round(ratio, 3) == 0.996 and start == 0

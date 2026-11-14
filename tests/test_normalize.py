"""AC-1: normalization steps, recorded steps and the map back to the original text."""
from __future__ import annotations

import pytest

from _qp_align import find_approximate, find_exact, find_normalized
from _qp_normalize import line_of, line_starts, normalize, split_ellipsis, step_names
from _qp_sources import SourceText


def src(text: str) -> SourceText:
    return SourceText("a.md", text)


def norm_steps(quote: str, text: str):
    ms = find_normalized(quote, src(text))
    assert ms, f"{quote!r} should match {text!r}"
    return ms[0].steps


# ---------- each step works ----------

def test_nfkc_ligature_and_fullwidth():
    assert norm_steps("the final offer", "the ﬁnal offer") == ["nfkc"]
    assert norm_steps("ABC 123", "ＡＢＣ １２３") == ["nfkc", "case"]


def test_quotes_step():
    assert norm_steps("don't say \"no\" now", "don’t say “no” now") == ["quotes"]


def test_dashes_step():
    assert norm_steps("a - b", "a — b") == ["dashes"]
    assert norm_steps("2020-2021", "2020–2021") == ["dashes"]


def test_whitespace_step():
    assert norm_steps("one two three", "one\n  two three") == ["whitespace"]
    assert norm_steps("one two", "one\ttwo") == ["whitespace"]


def test_case_step():
    assert norm_steps("the cache is stale", "The Cache is STALE") == ["case"]
    assert norm_steps("The Cache", "the cache") == ["case"]


def test_same_capitalisation_does_not_report_case():
    # both sides capitalise the same words; only the line break differs
    assert norm_steps("The Cache holds", "The Cache\nholds") == ["whitespace"]


def test_md_markup_step():
    assert norm_steps("run the **migration** script", "run the migration script") == ["md_markup"]
    assert norm_steps("run the migration script", "run the **migration** `script`") == ["md_markup"]
    assert norm_steps("first line second line", "> first line\n> second line") == ["whitespace", "md_markup"]


def test_markup_present_on_both_sides_is_not_reported():
    assert find_exact("run **migration** now", src("then run **migration** now")) != []


def test_dehyphen_joined_records_only_dehyphen():
    assert norm_steps("ten minutes", "ten min-\nutes") == ["dehyphen"]


def test_dehyphen_kept_for_real_hyphenated_words():
    # the quote has the real hyphen; the source broke the line right after it
    assert norm_steps("a well-known fact", "a well-\nknown fact") == ["dehyphen"]
    # the quote has the joined word
    assert norm_steps("a wellknown fact", "a well-\nknown fact") == ["dehyphen"]


def test_dehyphen_soft_hyphen():
    assert norm_steps("information", "infor­mation") == ["dehyphen"]


def test_ellipsis_step_fragments_in_order():
    s = src("alpha beta gamma delta epsilon zeta eta theta")
    assert find_normalized("alpha beta [...] delta epsilon", s)[0].steps == ["ellipsis"]
    assert find_normalized("alpha beta … theta", s)[0].steps == ["ellipsis"]
    assert find_normalized("delta epsilon [...] alpha beta", s) == []     # order matters


def test_cjk_spacing_step():
    ms = find_normalized("유지할 수있다 라고", src("유지할 수 있다 라고 적는다"))
    assert ms and ms[0].steps == ["cjk_spacing"]
    ms = find_normalized("Python으로 만든다", src("Python 으로 만든다"))
    assert ms and ms[0].steps == ["cjk_spacing"]


def test_steps_recorded_only_inside_the_matched_span():
    # the source has a hyphen break and curly quotes elsewhere, the matched span has neither
    text = "intro with min-\nutes and “quotes”.\nThe real sentence is right here."
    assert norm_steps("the real sentence is right here", text) == ["case"]


def test_step_names_follow_the_documented_order():
    assert step_names(0b11111111, ellipsis=True) == ["nfkc", "quotes", "dashes", "whitespace", "dehyphen", "case",
                                                     "md_markup", "ellipsis", "cjk_spacing"]


# ---------- different wording never passes as normalized ----------

def test_before_vs_after_is_not_normalized():
    s = src("Always run the migration script before restarting the service")
    assert find_normalized("Always run the migration script after restarting the service", s) == []
    assert find_exact("Always run the migration script after restarting the service", s) == []
    match, ratio = find_approximate("Always run the migration script after restarting the service", s, 0.8)
    assert match is not None and match.verdict == "approximate" and match.ratio == 0.889 and match.changed_units == 1


def test_different_word_forms_do_not_match():
    assert find_normalized("the caches hold", src("the cache holds")) == []


# ---------- index_map ----------

def test_index_map_after_nfkc_length_change():
    text = "a ﬁx and ＡＢ end"   # ligature fi (1 char -> 2), fullwidth letters
    n = normalize(text)
    assert n.text == "a fix and ab end"
    i = n.text.index("fix")
    s, e = n.span(i, i + 3)
    assert text[s:e] == "ﬁx"            # both normalized letters map back to the one ligature
    j = n.text.index("ab")
    s, e = n.span(j, j + 2)
    assert text[s:e] == "ＡＢ"


def test_index_map_after_dehyphenation_and_whitespace_folding():
    text = "first line\n\n   ten min-\nutes later\twe stop"
    n = normalize(text)
    assert n.text == "first line ten minutes later we stop"
    i = n.text.index("minutes")
    s, e = n.span(i, i + len("minutes"))
    assert text[s:e] == "min-\nutes"
    k = n.text.index("later")
    s, e = n.span(k, k + 5)
    assert text[s:e] == "later"
    assert n.index_map[k] == text.index("later")


def test_span_text_and_line_numbers_of_a_match():
    text = "line one\nline two with ten min-\nutes inside\nline four\n"
    m = find_normalized("two with ten minutes inside", src(text))[0]
    assert text[m.start:m.end] == "two with ten min-\nutes inside"
    assert (m.line_start, m.line_end) == (2, 3)
    assert m.text == "two with ten min-\nutes inside"


def test_line_numbers_of_helpers():
    starts = line_starts("a\nbb\n\nccc")
    assert [line_of(starts, o) for o in (0, 1, 2, 4, 5, 6)] == [1, 1, 2, 2, 3, 4]


def test_split_ellipsis_variants():
    assert split_ellipsis("a b [...] c d") == ["a b", "c d"]
    assert split_ellipsis("a b […] c d") == ["a b", "c d"]
    assert split_ellipsis("a b ... c d") == ["a b", "c d"]
    assert split_ellipsis("a b c") == ["a b c"]


@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_normalize_handles_blank_text(text):
    assert normalize(text).trim()[0] == normalize(text).trim()[1]
